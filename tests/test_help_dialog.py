import pytest
from PyQt6.QtWidgets import QLabel

from src.HelpDialog import HelpDialog


@pytest.fixture
def dialog(qtbot):
    d = HelpDialog()
    qtbot.addWidget(d)
    return d


def test_has_a_tab_per_help_topic(dialog):
    titles = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
    assert any("Beats" in t and "Rhythm" in t for t in titles)
    assert any("Language" in t for t in titles)


def test_beats_tab_explains_pattern_number_meaning(dialog):
    titles = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
    beats_tab = dialog.tabs.widget(titles.index("Beats && Rhythm"))
    text = " ".join(w.text() for w in beats_tab.findChildren(QLabel))
    assert "audible beat" in text
    assert "silent step" in text
    assert "1 is the longest" in text
    assert "4 is the shortest" in text


def _languages_tab_text(dialog):
    titles = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
    tab = dialog.tabs.widget(titles.index("Languages && Tones"))
    return " ".join(w.text() for w in tab.findChildren(QLabel))


def test_languages_tab_explains_adding_a_language(dialog):
    text = _languages_tab_text(dialog)
    assert "res/callouts/" in text
    assert "Trigger Key" in text
    assert "Manage Custom Phrase Files" in text


def test_languages_tab_explains_the_tone_axis(dialog):
    """The folder-per-language/file-per-tone layout is the one thing a phrase author has to
    get right, and the Guide is the only place in the app that says what it is."""
    text = _languages_tab_text(dialog)
    assert "tone" in text.lower()
    assert "Girlfriend Experience" in text
    assert "Degrading" in text


def test_languages_tab_says_tones_can_be_mixed(dialog):
    text = _languages_tab_text(dialog)
    assert "mix" in text.lower()


def test_on_screen_display_tab_documents_the_overlays(dialog):
    titles = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
    assert "On-Screen Display" in titles
    assert titles.index("On-Screen Display") == 1
    tab = dialog.tabs.widget(titles.index("On-Screen Display"))
    text = " ".join(w.text() for w in tab.findChildren(QLabel))
    assert "Session Timer" in text
    assert "Top-left" in text
    assert "Record-Chase" in text
    assert "Top-right" in text
    assert "personal record" in text
    assert "Playback" in text


def test_shortcuts_tab_lists_every_shortcut(dialog):
    titles = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
    assert "Keyboard Shortcuts" in titles
    shortcuts_tab = dialog.tabs.widget(titles.index("Keyboard Shortcuts"))
    text = " ".join(w.text() for w in shortcuts_tab.findChildren(QLabel))
    assert "Ctrl+O" in text
    assert "Right Arrow" in text
    assert "Left Arrow" in text
    assert "Ctrl+Space" in text
    assert "Toggle mute" in text
    assert "Panic" in text
    assert "F11" in text
    assert "Escape" in text
    assert "Ctrl+S" in text
    assert "F1" in text
    assert "Ctrl+Q" in text


def test_privacy_tab_states_everything_stays_local(dialog):
    titles = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
    assert "Privacy" in titles
    privacy_tab = dialog.tabs.widget(titles.index("Privacy"))
    text = " ".join(w.text() for w in privacy_tab.findChildren(QLabel))
    assert "100%" in text
    assert "locally" in text
    assert "no telemetry" in text
    assert "no account" in text
    assert "Check for Updates" in text
    assert "only when you click it" in text


def test_close_button_accepts_dialog(dialog):
    assert dialog.button.text() == "Close"
    dialog.button.click()
    assert dialog.result() == HelpDialog.DialogCode.Accepted
