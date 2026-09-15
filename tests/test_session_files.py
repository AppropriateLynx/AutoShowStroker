"""Turning a recorded session into something that survives on disk, and back.

Qt-free: this is serialisation, and the recorder's output is plain dicts.
"""
import json

import pytest

from src import session_files


def timeline(**overrides):
    """A recorded session as SessionRecorder.timeline() hands it over - wall-clock times."""
    base = {
        "started_at": 5000.0,
        "ended_at": 5200.0,
        "climax_at": 5180.0,
        "climax_outcome": "ruined",
        "fake_climaxes": [5040.0, 5120.0],
        "segments": [
            {"kind": "beat", "pattern": "Quick Swing", "freq": 2.3,
             "start": 5000.0, "end": 5060.0,
             "media": [{"path": "C:\\pics\\a.png", "start": 5000.0, "end": 5030.0, "carried_over": False},
                       {"path": "C:\\pics\\b.png", "start": 5030.0, "end": 5090.0, "carried_over": False}]},
            {"kind": "pause", "pattern": None, "freq": None,
             "start": 5060.0, "end": 5075.0,
             "media": [{"path": "C:\\pics\\b.png", "start": 5030.0, "end": 5090.0, "carried_over": True}]},
            {"kind": "finale", "pattern": "Build Up", "freq": 4.5,
             "start": 5075.0, "end": 5200.0, "media": []},
        ],
    }
    base.update(overrides)
    return base


# --- saving ---


def test_times_are_stored_as_offsets_not_wall_clock():
    """A replay starts whenever it starts - an absolute timestamp from last Tuesday is
    meaningless to it."""
    saved = session_files.to_saved_session(timeline())

    assert saved["segments"][0]["duration_sec"] == pytest.approx(60.0)
    assert saved["climax"]["at_sec"] == pytest.approx(180.0)
    assert saved["fake_climaxes"] == pytest.approx([40.0, 120.0])
    assert saved["media"][0]["at_sec"] == pytest.approx(0.0)


def test_every_segment_keeps_its_rhythm_speed_and_type():
    saved = session_files.to_saved_session(timeline())

    first, pause, finale = saved["segments"]

    assert (first["kind"], first["pattern"], first["freq"]) == ("beat", "Quick Swing", 2.3)
    assert (pause["kind"], pause["pattern"], pause["freq"]) == ("pause", None, None)
    assert finale["kind"] == "finale"


def test_media_are_listed_once_in_order():
    """Carried-over entries are the same medium listed again under the next segment -
    replaying it twice would show it twice."""
    saved = session_files.to_saved_session(timeline())

    assert [m["path"] for m in saved["media"]] == ["C:\\pics\\a.png", "C:\\pics\\b.png"]


def test_the_session_duration_is_recorded():
    assert session_files.to_saved_session(timeline())["duration_sec"] == pytest.approx(200.0)


def test_a_session_without_a_climax_saves_cleanly():
    saved = session_files.to_saved_session(timeline(climax_at=None, climax_outcome=None))
    assert saved["climax"] is None


def test_custom_patterns_used_by_the_session_are_carried_along():
    """Without the definition, a replay on another machine dies the moment it reaches one."""
    saved = session_files.to_saved_session(
        timeline(), custom_patterns={"My Rhythm": [1, 2, -1], "Unused": [1]},
    )
    # Only what the session actually used.
    assert saved["custom_patterns"] == {}

    used = timeline()
    used["segments"][0]["pattern"] = "My Rhythm"
    saved = session_files.to_saved_session(used, custom_patterns={"My Rhythm": [1, 2, -1], "Unused": [1]})

    assert saved["custom_patterns"] == {"My Rhythm": [1, 2, -1]}


def test_the_format_version_and_app_version_are_stamped():
    saved = session_files.to_saved_session(timeline())
    assert saved["format"] == session_files.FORMAT_VERSION
    assert saved["app_version"]
    assert saved["saved_at"]


# --- stripping paths ---


def test_stripping_removes_every_path_but_keeps_the_timing():
    """Exporting with paths carries the sender's account name, folder layout and file
    names - stripping has to leave none of it."""
    saved = session_files.strip_paths(session_files.to_saved_session(timeline()))

    assert all("path" not in entry for entry in saved["media"])
    assert [entry["at_sec"] for entry in saved["media"]] == pytest.approx([0.0, 30.0])
    assert "C:\\" not in json.dumps(saved)


def test_stripping_leaves_the_original_untouched():
    saved = session_files.to_saved_session(timeline())
    session_files.strip_paths(saved)
    assert "path" in saved["media"][0]


def test_stripping_an_already_stripped_session_is_harmless():
    once = session_files.strip_paths(session_files.to_saved_session(timeline()))
    assert session_files.strip_paths(once) == once


# --- loading ---


def test_a_saved_session_parses_back(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps(session_files.to_saved_session(timeline())), encoding="utf-8")

    loaded = session_files.read_session_file(path)

    assert [s["pattern"] for s in loaded["segments"]] == ["Quick Swing", None, "Build Up"]
    assert loaded["climax"]["outcome"] == "ruined"


def test_a_future_format_is_refused_rather_than_half_read(tmp_path):
    path = tmp_path / "s.json"
    saved = session_files.to_saved_session(timeline())
    saved["format"] = session_files.FORMAT_VERSION + 1
    path.write_text(json.dumps(saved), encoding="utf-8")

    with pytest.raises(session_files.UnsupportedSessionFile):
        session_files.read_session_file(path)


def test_a_file_that_is_not_a_session_is_refused(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"hello": "world"}), encoding="utf-8")

    with pytest.raises(session_files.UnsupportedSessionFile):
        session_files.read_session_file(path)


def test_a_corrupt_file_is_refused_rather_than_raising_json_errors(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json at all", encoding="utf-8")

    with pytest.raises(session_files.UnsupportedSessionFile):
        session_files.read_session_file(path)


def test_a_missing_file_is_refused_the_same_way(tmp_path):
    with pytest.raises(session_files.UnsupportedSessionFile):
        session_files.read_session_file(tmp_path / "gone.json")


# --- labels for the manager ---


def test_a_session_gets_a_readable_label():
    saved = session_files.to_saved_session(timeline())
    label = session_files.describe(saved)

    assert "3:20" in label  # 200 seconds
    assert "Ruined" in label


def test_a_session_without_paths_says_so_in_its_label():
    saved = session_files.strip_paths(session_files.to_saved_session(timeline()))
    assert "no media" in session_files.describe(saved).lower()
