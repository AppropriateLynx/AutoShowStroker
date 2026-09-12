import json

import pytest
from PyQt6.QtCore import QSettings

from src.user_data import LEGACY_DEAD_KEYS, UserDataStore


@pytest.fixture
def store(tmp_path):
    return UserDataStore(base_dir=tmp_path / "appdata")


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


# --- basic round-trip ---


def test_load_returns_default_when_nothing_saved(store):
    assert store.load("session_history", []) == []
    assert store.load("custom_patterns", {}) == {}


def test_save_then_load_round_trips(store):
    store.save("session_history", [{"total_num_beat": 42}])
    assert store.load("session_history", []) == [{"total_num_beat": 42}]


def test_save_creates_the_data_directory(store):
    assert not store.base_dir.exists()
    store.save("custom_patterns", {"Mine": [1, -1]})
    assert store.base_dir.is_dir()


def test_save_writes_readable_json(store):
    store.save("custom_patterns", {"Mine": [1, -1]})
    raw = store.path_for("custom_patterns").read_text(encoding="utf-8")
    assert json.loads(raw) == {"Mine": [1, -1]}


def test_save_leaves_no_temp_file_behind(store):
    store.save("session_history", [1, 2, 3])
    assert list(store.base_dir.glob("*.tmp")) == []


def test_save_overwrites_previous_content(store):
    store.save("session_history", [{"a": 1}])
    store.save("session_history", [{"b": 2}])
    assert store.load("session_history", []) == [{"b": 2}]


def test_non_ascii_content_survives_a_round_trip(store):
    store.save("custom_patterns", {"Süß  Pattern": [1, -1]})
    assert store.load("custom_patterns", {}) == {"Süß  Pattern": [1, -1]}


# --- migration out of QSettings ---


def test_migrates_a_legacy_registry_value_into_a_file(store, settings):
    history = [{"ended_at": "2026-07-18 19:18", "total_num_beat": 102}]
    settings.setValue("ScoreTracker/session_history", json.dumps(history))

    loaded = store.load("session_history", [], settings, "ScoreTracker/session_history")

    assert loaded == history
    assert store.path_for("session_history").exists()


def test_migration_removes_the_legacy_key(store, settings):
    settings.setValue("ScoreTracker/session_history", json.dumps([{"total_num_beat": 1}]))

    store.load("session_history", [], settings, "ScoreTracker/session_history")

    assert settings.value("ScoreTracker/session_history") is None


def test_migration_leaves_other_settings_untouched(store, settings):
    settings.setValue("ScoreTracker/session_history", json.dumps([{"total_num_beat": 1}]))
    settings.setValue("BeatHandler/min_beat_freq", 2.0)

    store.load("session_history", [], settings, "ScoreTracker/session_history")

    assert settings.value("BeatHandler/min_beat_freq") is not None


def test_file_wins_once_migrated(store, settings):
    store.save("session_history", [{"from": "file"}])
    settings.setValue("ScoreTracker/session_history", json.dumps([{"from": "registry"}]))

    loaded = store.load("session_history", [], settings, "ScoreTracker/session_history")

    assert loaded == [{"from": "file"}]


def test_migration_is_idempotent(store, settings):
    history = [{"total_num_beat": 7}]
    settings.setValue("ScoreTracker/session_history", json.dumps(history))

    first = store.load("session_history", [], settings, "ScoreTracker/session_history")
    second = store.load("session_history", [], settings, "ScoreTracker/session_history")

    assert first == second == history


def test_no_migration_when_legacy_key_absent(store, settings):
    assert store.load("session_history", [], settings, "ScoreTracker/session_history") == []
    assert not store.path_for("session_history").exists()


def test_corrupt_legacy_value_is_not_migrated_and_does_not_raise(store, settings):
    settings.setValue("ScoreTracker/session_history", "{not valid json")

    loaded = store.load("session_history", [], settings, "ScoreTracker/session_history")

    assert loaded == []
    # Unparseable legacy data is left alone rather than silently destroyed - deleting it
    # would throw away the only copy of something we simply failed to read.
    assert settings.value("ScoreTracker/session_history") is not None


# --- corrupt data files must never crash the app ---


def test_corrupt_file_returns_the_default_instead_of_raising(store):
    store.save("session_history", [{"a": 1}])
    store.path_for("session_history").write_text("{not valid json", encoding="utf-8")

    assert store.load("session_history", []) == []


def test_corrupt_file_is_quarantined(store):
    store.save("session_history", [{"a": 1}])
    store.path_for("session_history").write_text("{not valid json", encoding="utf-8")

    store.load("session_history", [])

    assert store.path_for("session_history").with_suffix(".json.corrupt").exists()
    assert not store.path_for("session_history").exists()


def test_saving_after_a_corrupt_file_recovers(store):
    store.path_for("session_history").parent.mkdir(parents=True, exist_ok=True)
    store.path_for("session_history").write_text("garbage", encoding="utf-8")
    store.load("session_history", [])

    store.save("session_history", [{"fresh": True}])

    assert store.load("session_history", []) == [{"fresh": True}]


# --- dead registry keys from removed features ---


def test_prune_removes_the_reverted_tts_keys(store, settings):
    settings.setValue("TTSHandler/enabled", True)
    settings.setValue("TTSHandler/voice_id", "some-voice")
    settings.setValue("TTSHandler/volume", 0.8)

    store.prune_legacy_registry_keys(settings)

    assert settings.value("TTSHandler/enabled") is None
    assert settings.value("TTSHandler/voice_id") is None
    assert settings.value("TTSHandler/volume") is None


def test_prune_removes_the_superseded_loudness_key(store, settings):
    settings.setValue("GoonerApp/loudness", 1.0)

    store.prune_legacy_registry_keys(settings)

    assert settings.value("GoonerApp/loudness") is None


def test_prune_keeps_live_settings(store, settings):
    settings.setValue("GoonerApp/vid_loudness", 0.5)
    settings.setValue("GoonerApp/last_seen_version", "0.7.1")
    settings.setValue("BeatHandler/min_beat_freq", 2.0)

    store.prune_legacy_registry_keys(settings)

    assert float(settings.value("GoonerApp/vid_loudness")) == 0.5
    assert settings.value("GoonerApp/last_seen_version") == "0.7.1"
    assert float(settings.value("BeatHandler/min_beat_freq")) == 2.0


def test_prune_is_safe_when_nothing_is_there(store, settings):
    store.prune_legacy_registry_keys(settings)


def test_dead_keys_list_does_not_name_anything_still_read_by_the_app(store):
    # Guard against someone adding a key here that production code still reads.
    assert "GoonerApp/vid_loudness" not in LEGACY_DEAD_KEYS
    assert "ScoreTracker/session_history" not in LEGACY_DEAD_KEYS


# --- default location ---


def test_defaults_to_a_real_app_data_directory():
    store = UserDataStore()
    assert store.base_dir.is_absolute()
