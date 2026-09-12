"""User *data* storage, as opposed to user *settings*.

Settings (the sliders, toggles, selected language, last-used folders) stay in `QSettings`
- small scalar config values are exactly what it is for, and a per-user `HKCU` key is the
normal, Qt-sanctioned mechanism for them.

Data (session history, custom beat patterns, custom phrase file references) is different:
it is user-authored and it accumulates. Stuffed into single registry string values it had
to be artificially capped to keep the registry from growing without limit. It lives in
plain JSON files under QStandardPaths' AppDataLocation instead - inspectable, trivially
backed up, and uncapped by the storage mechanism.

Existing installs are migrated lazily: the first load of a given key copies it out of
QSettings into a file and only then drops the registry value.
"""

import json
import os
from pathlib import Path

from PyQt6.QtCore import QStandardPaths

# Registry keys no production code reads any more. Removed once, on the next launch.
# TTSHandler/* is left over from the text-to-speech feature that was reverted (Windows 11
# Natural voices turned out to be Narrator-exclusive); GoonerApp/loudness was superseded
# by GoonerApp/vid_loudness.
LEGACY_DEAD_KEYS = (
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
            base_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        self.base_dir = Path(base_dir)

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

    def save(self, name: str, payload) -> None:
        """Writes atomically - a crash mid-write can never leave a half-written data file
        (which, unlike a settings value, would be actual lost user history)."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self.path_for(name)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)

    def prune_legacy_registry_keys(self, settings) -> None:
        """Drops registry keys belonging to removed features. Idempotent - removing an
        absent key is a no-op, so this can run on every launch."""
        if settings is None:
            return
        for key in LEGACY_DEAD_KEYS:
            settings.remove(key)
        settings.sync()

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

        self.save(name, payload)
        if self._read(self.path_for(name), default) != payload:
            return payload  # write didn't verify - keep the registry copy as the fallback

        settings.remove(legacy_key)
        settings.sync()
        return payload
