"""User *data* storage, as opposed to user *settings*.

Settings (the sliders, toggles, selected language) stay in `QSettings` - small scalar
config values are exactly what it is for, and a per-user `HKCU` key is the normal,
Qt-sanctioned mechanism for them.

Data (session history, custom beat patterns, custom phrase file references, the last-used
media folders) is different: it is user-authored and it accumulates. Stuffed into single
registry string values it had to be artificially capped to keep the registry from growing
without limit. It lives in plain JSON files under QStandardPaths' AppLocalDataLocation
instead - inspectable, trivially backed up, and uncapped by the storage mechanism.

The media folder paths belong here for a second reason: they point straight into the
user's collection, and a portable .exe has no uninstaller to clean HKCU afterwards. Data
the user might want gone has to live somewhere they can actually delete.

Existing installs are migrated lazily: the first load of a given key copies it out of
QSettings into a file and only then drops the registry value.
"""

import json
import os
import shutil
from pathlib import Path

from PyQt6.QtCore import QStandardPaths

from src.applog import get_logger

log = get_logger(__name__)

# Registry keys no production code reads any more. Removed once, on the next launch.
# TTSHandler/* is left over from the text-to-speech feature that was reverted (Windows 11
# Natural voices turned out to be Narrator-exclusive); GoonerApp/loudness was superseded
# by GoonerApp/vid_loudness.
LEGACY_DEAD_KEYS = (
    # Replaced by the session plan: segment length is now drawn outright, and the climax
    # is placed as a time into the session rather than rolled at every beat change.
    "BeatHandler/beat_change_chance",
    "ClimaxHandler/climax_chance",
    "TTSHandler",
    "GoonerApp/loudness",
)


class UserDataStore:
    """Reads and writes the app's JSON data files, and migrates them out of QSettings.

    base_dir is injectable for the same reason QSettings is everywhere else in this
    codebase: tests must never touch the real user directory. Note that pytest-qt sets
    the QApplication's applicationName itself, so the default location would resolve to a
    real on-disk path during tests - always inject in a test.
    """

    def __init__(self, base_dir=None):
        if base_dir is None:
            # AppLocalDataLocation, not AppDataLocation: the latter is the *Roaming* profile
            # on Windows, so with folder redirection, a domain profile or OneDrive's Known
            # Folder Move, session history and the paths in custom_phrase_files.json get
            # copied off the machine at logoff. For an app that promises to stay local,
            # that is the wrong default.
            self.base_dir = Path(
                QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
            )
            self._legacy_base_dir = Path(
                QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
            )
        else:
            self.base_dir = Path(base_dir)
            # An injected store is a test store: it has no legacy location, and must never
            # go looking for one in the developer's real AppData.
            self._legacy_base_dir = None

    def path_for(self, name: str) -> Path:
        return self.base_dir / f"{name}.json"

    def load(self, name: str, default, settings=None, legacy_key=None):
        path = self.path_for(name)
        if path.exists():
            return self._read(path, default)
        if settings is not None and legacy_key is not None:
            migrated = self._migrate_from_settings(name, default, settings, legacy_key)
            if migrated is not None:
                return migrated
        return default

    def save(self, name: str, payload) -> bool:
        """Writes atomically - a crash mid-write can never leave a half-written data file
        (which, unlike a settings value, would be actual lost user history).

        Returns whether the write landed. It never raises: the main caller is the
        session_ended signal chain, and an OSError there (full disk, an antivirus lock on
        the .tmp file, a %APPDATA% the user can't write) used to abort the process before
        the statistics dialog was ever reached - losing the session *and* the recap, to
        report a problem that only cost the session.
        """
        path = self.path_for(name)
        tmp_path = path.with_suffix(".json.tmp")
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp_path, path)
        except OSError as error:
            log.error("Could not save %s: %s", name, error)
            return False
        return True

    def prune_legacy_registry_keys(self, settings) -> None:
        """Drops registry keys belonging to removed features. Idempotent - removing an
        absent key is a no-op, so this can run on every launch."""
        if settings is None:
            return
        for key in LEGACY_DEAD_KEYS:
            settings.remove(key)
        settings.sync()

    def delete(self, name: str) -> bool:
        """Removes a data file at the user's request. Returns whether anything was there.

        Takes the .corrupt and .tmp siblings with it: both hold the same content, so
        leaving one behind would make the app's "delete my data" claim untrue.
        """
        path = self.path_for(name)
        removed = False
        for candidate in (path, path.with_suffix(".json.corrupt"), path.with_suffix(".json.tmp")):
            try:
                candidate.unlink()
                removed = True
            except FileNotFoundError:
                pass
            except OSError as error:
                log.warning("Could not delete %s: %s", candidate.name, error)
        return removed

    def migrate_legacy_location(self) -> None:
        """Moves data files out of the old Roaming directory. Idempotent, so it can run on
        every launch - explicit rather than done in __init__ so that merely constructing a
        store (in a test, say) never touches the filesystem, same as prune_legacy_registry_keys.
        """
        old_dir = self._legacy_base_dir
        if old_dir is None or old_dir == self.base_dir or not old_dir.is_dir():
            return

        moved = 0
        for path in sorted(old_dir.glob("*.json")):
            target = self.base_dir / path.name
            if target.exists():
                continue  # a local file is the newer one - never clobber it
            try:
                self.base_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(target))
                moved += 1
            except OSError as error:
                log.warning("Could not move %s out of the roaming profile: %s", path.name, error)
                return

        if moved:
            log.info("Moved %d data file(s) out of %s", moved, old_dir)
        try:
            old_dir.rmdir()  # only succeeds once it is genuinely empty
        except OSError:
            pass

    # --- internals ---

    def _read(self, path: Path, default):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            # Never let unreadable data stop the app from starting. The bad file is kept
            # aside rather than deleted, so it can still be recovered by hand.
            self._quarantine(path)
            return default

    @staticmethod
    def _quarantine(path: Path) -> None:
        try:
            os.replace(path, path.with_suffix(".json.corrupt"))
        except OSError:
            pass

    def _migrate_from_settings(self, name: str, default, settings, legacy_key: str):
        raw = settings.value(legacy_key)
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Leave unparseable legacy data in place - it is the only copy, and deleting
            # something we merely failed to read would destroy it for good.
            return None

        if not self.save(name, payload):
            return payload  # write failed - the registry copy is still the only one
        if self._read(self.path_for(name), default) != payload:
            return payload  # write didn't verify - keep the registry copy as the fallback

        settings.remove(legacy_key)
        settings.sync()
        return payload
