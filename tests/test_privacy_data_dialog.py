from pathlib import Path

import pytest

from src.PrivacyDataDialog import PrivacyDataDialog


@pytest.fixture
def dialog(app, qtbot):
    d = PrivacyDataDialog(app, parent=app)
    qtbot.addWidget(d)
    return d


@pytest.fixture
def confirmed(dialog, monkeypatch):
    """Auto-confirms the deletion prompt and records what it was asked about."""
    asked = {}
    monkeypatch.setattr(dialog, "_confirm_deletion", lambda keys: asked.setdefault("keys", keys) or True)
    return asked


def _populate(app, tmp_path):
    app.score_tracker.history = [{"total_dur_sec": 60}, {"total_dur_sec": 30}]
    app.data_store.save("session_history", app.score_tracker.history)
    app.beat_handler.add_or_update_custom_pattern("Mine", [1, -1])
    app.data_store.save("last_selected_folders", [str(tmp_path)])


# --- disclosure ---


def test_dialog_names_the_real_data_directory(app, dialog):
    assert str(app.data_store.base_dir) in dialog.locations_text()


def test_dialog_names_where_settings_live(app, dialog):
    assert app.settings.fileName() in dialog.locations_text()


def test_open_data_folder_opens_the_store_directory(app, dialog, monkeypatch):
    opened = {}
    monkeypatch.setattr(dialog, "_open_url", lambda url: opened.setdefault("url", url))

    dialog.btn_open_folder.click()

    # QUrl.toLocalFile() normalises to forward slashes on Windows - compare as paths.
    assert Path(opened["url"].toLocalFile()) == app.data_store.base_dir


# --- counts ---


def test_counts_reflect_what_is_actually_stored(app, dialog, tmp_path):
    _populate(app, tmp_path)
    dialog.refresh_counts()

    counts = dialog.category_counts()
    assert counts["session_history"] == 2
    assert counts["custom_patterns"] == 1
    assert counts["last_selected_folders"] == 1


def test_counts_are_zero_on_a_clean_profile(dialog):
    assert all(count == 0 for key, count in dialog.category_counts().items() if key != "settings")


# --- deleting ---


def test_clearing_session_history_empties_it_in_memory_and_on_disk(app, dialog, tmp_path):
    _populate(app, tmp_path)

    dialog.clear_categories(["session_history"])

    assert app.score_tracker.get_history() == []
    assert not app.data_store.path_for("session_history").exists()


def test_clearing_custom_patterns_removes_them_everywhere(app, dialog, tmp_path):
    _populate(app, tmp_path)

    dialog.clear_categories(["custom_patterns"])

    assert "Mine" not in app.beat_handler.available_beat_patterns
    assert "Mine" not in app.beat_handler.selected_beat_patterns
    assert not app.data_store.path_for("custom_patterns").exists()
    # The built-ins must survive - clearing custom data is not a rhythm reset.
    assert "Standard Beat" in app.beat_handler.available_beat_patterns


def test_clearing_custom_phrase_files_forgets_them(app, dialog, tmp_path):
    phrase_file = tmp_path / "extra.json"
    phrase_file.write_text('{"session_start": ["hello"]}', encoding="utf-8")
    app.callout_handler.load_custom_file(str(phrase_file), "en")
    assert app.callout_handler.custom_phrase_files

    dialog.clear_categories(["custom_phrase_files"])

    assert app.callout_handler.custom_phrase_files == []
    assert not app.data_store.path_for("custom_phrase_files").exists()
    assert "hello" not in app.callout_handler.callout_data["en"].get("session_start", [])


def test_clearing_media_folders_removes_the_stored_paths(app, dialog, tmp_path):
    _populate(app, tmp_path)

    dialog.clear_categories(["last_selected_folders"])

    assert not app.data_store.path_for("last_selected_folders").exists()
    assert app.data_store.load("last_selected_folders", []) == []


def test_clearing_settings_wipes_them_but_keeps_the_data_files(app, dialog, tmp_path):
    _populate(app, tmp_path)
    app.settings.setValue("GoonerApp/min_dur", 2.5)

    dialog.clear_categories(["settings"])

    assert app.settings.value("GoonerApp/min_dur") is None
    assert app.data_store.path_for("session_history").exists()


def test_clearing_one_category_leaves_the_others_alone(app, dialog, tmp_path):
    _populate(app, tmp_path)

    dialog.clear_categories(["session_history"])

    assert app.data_store.path_for("custom_patterns").exists()
    assert app.data_store.path_for("last_selected_folders").exists()


def test_delete_button_clears_every_ticked_category(app, dialog, confirmed, tmp_path):
    _populate(app, tmp_path)
    dialog.refresh_counts()
    dialog.checkboxes["session_history"].setChecked(True)
    dialog.checkboxes["last_selected_folders"].setChecked(True)

    dialog.btn_delete.click()

    assert set(confirmed["keys"]) == {"session_history", "last_selected_folders"}
    assert not app.data_store.path_for("session_history").exists()
    assert not app.data_store.path_for("last_selected_folders").exists()
    assert app.data_store.path_for("custom_patterns").exists()


def test_delete_button_does_nothing_when_the_prompt_is_declined(app, dialog, monkeypatch, tmp_path):
    _populate(app, tmp_path)
    monkeypatch.setattr(dialog, "_confirm_deletion", lambda _keys: False)
    dialog.checkboxes["session_history"].setChecked(True)

    dialog.btn_delete.click()

    assert app.data_store.path_for("session_history").exists()


def test_delete_button_is_disabled_until_something_is_ticked(dialog):
    assert dialog.btn_delete.isEnabled() is False

    dialog.checkboxes["session_history"].setChecked(True)
    assert dialog.btn_delete.isEnabled() is True

    dialog.checkboxes["session_history"].setChecked(False)
    assert dialog.btn_delete.isEnabled() is False


def test_counts_refresh_after_a_deletion(app, dialog, confirmed, tmp_path):
    _populate(app, tmp_path)
    dialog.refresh_counts()
    dialog.checkboxes["session_history"].setChecked(True)

    dialog.btn_delete.click()

    assert dialog.category_counts()["session_history"] == 0


def test_deleting_also_removes_quarantined_and_temp_leftovers(app, dialog):
    """A .corrupt or .tmp sibling holds the same data - leaving it behind would make
    'delete my data' a lie."""
    app.data_store.save("session_history", [{"total_dur_sec": 1}])
    path = app.data_store.path_for("session_history")
    path.with_suffix(".json.corrupt").write_text("[]", encoding="utf-8")
    path.with_suffix(".json.tmp").write_text("[]", encoding="utf-8")

    dialog.clear_categories(["session_history"])

    assert not path.exists()
    assert not path.with_suffix(".json.corrupt").exists()
    assert not path.with_suffix(".json.tmp").exists()
