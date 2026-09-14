import json

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QFileDialog

from src.CalloutHandler import CalloutHandler
from src.CustomPhraseFilesDialog import CustomPhraseFilesDialog


@pytest.fixture
def callout_dir(tmp_path):
    from src.CalloutHandler import TRIGGER_KEYS
    (tmp_path / "en").mkdir()
    for tone in ("flirty", "shy"):
        phrases = {key: [f"en {tone} {key} phrase"] for key in TRIGGER_KEYS}
        (tmp_path / "en" / f"{tone}.json").write_text(json.dumps(phrases), encoding="utf-8")
    return tmp_path


@pytest.fixture
def callout_handler(qapp, callout_dir, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    return CalloutHandler(settings=settings, callout_dir=callout_dir)


@pytest.fixture
def dialog(callout_handler, qtbot):
    d = CustomPhraseFilesDialog(callout_handler)
    qtbot.addWidget(d)
    return d


def _write_custom_file(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_starts_with_empty_list(dialog):
    assert dialog.file_list.count() == 0


def test_add_file_loads_it_and_updates_list(dialog, callout_handler, tmp_path, monkeypatch):
    custom_path = _write_custom_file(tmp_path, "custom.json", {"session_started": ["custom phrase"]})
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (custom_path, "JSON Files (*.json)"))
    dialog.lang_combo.setCurrentText("en")

    dialog._on_add_file()

    assert callout_handler.callout_data["en"]["flirty"]["session_started"] == [
        "en flirty session_started phrase",
        "custom phrase",
    ]
    assert dialog.file_list.count() == 1
    assert "en" in dialog.file_list.item(0).text()
    assert custom_path in dialog.file_list.item(0).text()


def test_add_file_cancelled_is_noop(dialog, callout_handler, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))

    dialog._on_add_file()

    assert dialog.file_list.count() == 0
    assert callout_handler.custom_phrase_files == []


def test_add_file_invalid_shows_error_and_does_not_add(dialog, callout_handler, tmp_path, monkeypatch):
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(bad_path), "JSON Files (*.json)"))
    dialog.lang_combo.setCurrentText("en")

    dialog._on_add_file()

    assert dialog.error_label.text() != ""
    assert dialog.file_list.count() == 0
    assert callout_handler.custom_phrase_files == []


def test_remove_selected_unloads_file(dialog, callout_handler, tmp_path, monkeypatch):
    custom_path = _write_custom_file(tmp_path, "custom.json", {"session_started": ["custom phrase"]})
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (custom_path, "JSON Files (*.json)"))
    dialog.lang_combo.setCurrentText("en")
    dialog._on_add_file()
    dialog.file_list.setCurrentRow(0)

    dialog._on_remove_selected()

    assert dialog.file_list.count() == 0
    assert callout_handler.custom_phrase_files == []
    assert callout_handler.callout_data["en"]["flirty"]["session_started"] == ["en flirty session_started phrase"]


# --- tone, the second axis next to language ---


def test_tone_combo_offers_any_tone_first_then_every_tone(dialog, callout_handler):
    items = [dialog.tone_combo.itemData(i) for i in range(dialog.tone_combo.count())]

    assert items == [None] + callout_handler.available_tones
    assert dialog.tone_combo.itemText(0) == "Any tone"
    assert dialog.tone_combo.itemText(1) == "Flirty"


def test_a_file_added_for_any_tone_speaks_in_every_tone(dialog, callout_handler, tmp_path, monkeypatch):
    """Phrase files predate tones and used to always apply - "Any tone" is that behaviour,
    and is what stored entries without a tone fall back to."""
    custom_path = _write_custom_file(tmp_path, "custom.json", {"session_started": ["anywhere"]})
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (custom_path, "JSON Files (*.json)"))
    dialog.lang_combo.setCurrentText("en")
    dialog.tone_combo.setCurrentIndex(0)

    dialog._on_add_file()

    assert callout_handler.custom_phrase_files[0]["tone"] is None
    for tone in ("flirty", "shy"):
        assert "anywhere" in callout_handler.callout_data["en"][tone]["session_started"]


def test_a_file_added_for_one_tone_stays_in_that_tone(dialog, callout_handler, tmp_path, monkeypatch):
    custom_path = _write_custom_file(tmp_path, "custom.json", {"session_started": ["shy only"]})
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (custom_path, "JSON Files (*.json)"))
    dialog.lang_combo.setCurrentText("en")
    dialog.tone_combo.setCurrentIndex(dialog.tone_combo.findData("shy"))

    dialog._on_add_file()

    assert callout_handler.custom_phrase_files[0]["tone"] == "shy"
    assert "shy only" in callout_handler.callout_data["en"]["shy"]["session_started"]
    assert "shy only" not in callout_handler.callout_data["en"]["flirty"]["session_started"]


def test_the_list_row_names_the_tone(dialog, tmp_path, monkeypatch):
    custom_path = _write_custom_file(tmp_path, "custom.json", {"session_started": ["shy only"]})
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (custom_path, "JSON Files (*.json)"))
    dialog.tone_combo.setCurrentIndex(dialog.tone_combo.findData("shy"))

    dialog._on_add_file()

    assert "Shy" in dialog.file_list.item(0).text()


def test_close_button_accepts_dialog(dialog):
    assert dialog.close_button.text() == "Close"
    dialog.close_button.click()
    assert dialog.result() == CustomPhraseFilesDialog.DialogCode.Accepted
