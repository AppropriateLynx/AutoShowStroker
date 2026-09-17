"""Reading and writing saved sessions.

A saved session is what SessionRecorder recorded, turned into something a later run can
replay: the segments in order, when the climax landed and how it went, the fake-outs, the
media and when each came up.

Every time in the file is **seconds from the start of the session**, never a wall clock. A
replay starts whenever it starts, and an absolute timestamp from last Tuesday would mean
nothing to it.

Note what this writes: media file paths. That is the one thing this app otherwise keeps off
disk entirely - it is not even allowed in the log (see CLAUDE.md). It happens here because
the user asked for it by pressing Save, it is disclosed and deletable under Privacy & Data,
and strip_paths() exists so a session can be handed to someone else without carrying the
sender's account name, folder layout and file names along with it.
"""
import json
import time
from pathlib import Path

from src.applog import get_logger
from src.utils import format_clock, get_current_version

log = get_logger(__name__)

# Bumped whenever the shape below changes incompatibly. read_session_file() refuses
# anything newer rather than half-reading it into a session that then behaves oddly.
FORMAT_VERSION = 1

OUTCOME_LABELS = {"real": "Climax", "ruined": "Ruined", "denied": "Denied"}


class UnsupportedSessionFile(Exception):
    """The file is not a session this build can replay - missing, corrupt, or newer."""


def to_saved_session(timeline, custom_patterns=None) -> dict:
    """Converts a SessionRecorder timeline into the saved form."""
    start = timeline.get("started_at") or 0.0
    segments = [
        {
            "kind": data["kind"],
            "pattern": data["pattern"],
            "freq": data["freq"],
            "duration_sec": data["end"] - data["start"],
        }
        for data in timeline["segments"]
    ]

    climax = None
    if timeline.get("climax_at") is not None:
        climax = {"at_sec": timeline["climax_at"] - start, "outcome": timeline.get("climax_outcome")}

    return {
        "format": FORMAT_VERSION,
        "app_version": get_current_version(),
        "saved_at": time.strftime("%Y-%m-%d %H:%M", time.localtime()),
        "duration_sec": (timeline.get("ended_at") or start) - start,
        "segments": segments,
        "custom_patterns": _patterns_used(timeline, custom_patterns or {}),
        "climax": climax,
        "fake_climaxes": [at - start for at in timeline.get("fake_climaxes", [])],
        "media": _media_script(timeline, start),
    }


def _patterns_used(timeline, custom_patterns) -> dict:
    """Only the custom rhythms this session actually played.

    Carrying the definitions matters: a replay on another machine hits the first scripted
    segment naming a pattern it has never heard of and has nothing to play. Carrying *all*
    of them would quietly hand over the user's whole pattern library instead.
    """
    used = {data["pattern"] for data in timeline["segments"] if data["pattern"]}
    return {name: list(steps) for name, steps in custom_patterns.items() if name in used}


def _media_script(timeline, start) -> list:
    """Each medium once, in the order it came up.

    The timeline lists a medium again under every segment it spanned (flagged
    carried_over), which is right for the explorer and wrong here - replaying it would
    show the same picture twice.
    """
    script = []
    for data in timeline["segments"]:
        for entry in data["media"]:
            if entry["carried_over"]:
                continue
            script.append({"at_sec": entry["start"] - start, "path": entry["path"]})
    return script


def strip_paths(saved: dict) -> dict:
    """A copy with every media path removed, keeping the timings.

    What is left replays the session's difficulty and pacing against whatever collection
    the other person has. What is gone is everything that would tell them where yours
    lives.
    """
    stripped = dict(saved)
    stripped["media"] = [{"at_sec": entry["at_sec"]} for entry in saved.get("media", [])]
    return stripped


def has_paths(saved: dict) -> bool:
    return any("path" in entry for entry in saved.get("media", []))


def read_session_file(path) -> dict:
    """Loads a saved session, or raises UnsupportedSessionFile.

    One exception for every way this can fail - the caller shows the same "this file cannot
    be replayed" either way, and the specifics belong in the log rather than in a dialog.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        log.warning("Could not read the session file: %s", error)
        raise UnsupportedSessionFile("The file could not be read.") from error

    if not isinstance(data, dict) or "format" not in data or "segments" not in data:
        raise UnsupportedSessionFile("That is not a saved session.")
    if data["format"] > FORMAT_VERSION:
        raise UnsupportedSessionFile(
            "That session was saved by a newer version of GoonerApp."
        )
    return data


def describe(saved: dict) -> str:
    """One line for the saved-sessions list."""
    parts = [saved.get("saved_at", "?"), format_clock(saved.get("duration_sec") or 0)]
    climax = saved.get("climax")
    if climax:
        parts.append(OUTCOME_LABELS.get(climax.get("outcome"), str(climax.get("outcome"))))
    fakes = len(saved.get("fake_climaxes", []))
    if fakes:
        parts.append(f"{fakes} fake-out{'s' if fakes > 1 else ''}")
    if not has_paths(saved):
        parts.append("no media paths")
    return "  -  ".join(parts)


def write_session_file(path, saved: dict) -> bool:
    """Exports one session to a file the user picked. Returns whether it landed.

    Never raises: the caller is a file dialog's OK button, and a read-only stick or a
    vanished network drive should get a "could not write that" box, not a traceback over
    the app.
    """
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(saved, handle, ensure_ascii=False, indent=2)
    except OSError as error:
        log.error("Could not write the session file: %s", error)
        return False
    return True


# --- the shelf of saved sessions ---

SAVED_SESSIONS_KEY = "saved_sessions"
# Far below ScoreTracker.MAX_HISTORY_ENTRIES on purpose: a history entry is a handful of
# numbers, a saved session carries every segment and every medium it showed.
MAX_SAVED_SESSIONS = 50


def load_saved_sessions(data_store) -> list:
    """Every saved session, oldest first."""
    stored = data_store.load(SAVED_SESSIONS_KEY, [])
    if not isinstance(stored, list):
        log.warning("The saved sessions file did not contain a list - ignoring it.")
        return []
    return stored


def store_session(data_store, saved: dict) -> bool:
    """Puts one session on the shelf, dropping the oldest once it is full."""
    sessions = load_saved_sessions(data_store)
    sessions.append(saved)
    return data_store.save(SAVED_SESSIONS_KEY, sessions[-MAX_SAVED_SESSIONS:])


def delete_saved_session(data_store, index: int) -> bool:
    """Removes one session from the shelf. Returns whether there was one at that index."""
    sessions = load_saved_sessions(data_store)
    if not 0 <= index < len(sessions):
        return False
    del sessions[index]
    data_store.save(SAVED_SESSIONS_KEY, sessions)
    return True


def recorded_paths(saved: dict) -> list:
    """The media the session showed, in order. Empty when the paths were stripped."""
    return [entry["path"] for entry in saved.get("media", []) if "path" in entry]


def missing_paths(saved: dict) -> list:
    """Recorded media that is no longer where it was, so the caller can offer to replay
    against another library instead of showing a session of empty frames."""
    return [path for path in recorded_paths(saved) if not Path(path).exists()]
