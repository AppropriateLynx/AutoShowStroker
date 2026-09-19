from unittest.mock import MagicMock

import pytest

from src.SettingsDialog import SettingsDialog


@pytest.fixture
def dialog(app, qtbot):
    dialog = SettingsDialog(app)
    qtbot.addWidget(dialog)
    return dialog


@pytest.fixture
def allow_consent(monkeypatch):
    """The consent dialog is a real modal - answered here rather than opened."""
    asked = []
    monkeypatch.setattr(
        "src.plugins.intiface.settings_widget.confirm_device_output",
        lambda parent, url, settings: asked.append(url) or True,
    )
    return asked


def test_the_device_tab_ships_no_address_of_its_own(dialog):
    """Intiface Central shows the address its server listens on, and that is the only
    one that can be right for a given machine. Filling one in for the user would also
    mean shipping a network address inside an app that promises not to contact any."""
    tab = dialog.intiface_tab
    assert not tab.enabled.isChecked()
    assert tab.server.text() == ""
    assert tab.minimum.value() == 25
    assert tab.maximum.value() == 75
    assert not tab.test_up.isEnabled()
    assert not tab.test_down.isEnabled()


def test_a_half_typed_address_does_not_block_every_other_setting(app, dialog):
    """The address only has to be a real one when device output is being switched on. A
    typo in a tab the user is not even using has no business locking the Save button."""
    dialog.intiface_tab.server.setText("not an address")
    dialog.settings_fields["max_dur"]["widget"].setValue(9)
    dialog.settings_fields["min_dur"]["widget"].setValue(8)
    dialog.accept_settings()
    assert app.player.min_dur == 8


def test_an_impossible_stroke_range_still_blocks_the_save(app, dialog):
    dialog.intiface_tab.minimum.setValue(95)
    dialog.intiface_tab.maximum.setValue(20)
    dialog.settings_fields["max_dur"]["widget"].setValue(9)
    dialog.settings_fields["min_dur"]["widget"].setValue(8)
    old = app.player.min_dur
    dialog.accept_settings()
    assert app.player.min_dur == old
    assert not app.intiface.controller.enabled


def test_enabling_device_output_asks_first_and_connects_there_and_then(app, dialog, allow_consent, monkeypatch):
    """Ticking the box is the act of connecting, not a preference to be saved later -
    which is also why it is where consent belongs: it is the moment something would
    actually leave the machine."""
    configure = MagicMock()
    monkeypatch.setattr(app.intiface.controller, "configure", configure)
    tab = dialog.intiface_tab
    tab.server.setText("ws://the-address-the-user-typed:1")
    tab.enabled.click()
    assert allow_consent == ["ws://the-address-the-user-typed:1"]
    configure.assert_called_once_with(True, "ws://the-address-the-user-typed:1", 0.25, 0.75)


def test_declining_the_consent_leaves_device_output_off(app, dialog, monkeypatch):
    monkeypatch.setattr(
        "src.plugins.intiface.settings_widget.confirm_device_output",
        lambda parent, url, settings: False,
    )
    configure = MagicMock()
    monkeypatch.setattr(app.intiface.controller, "configure", configure)
    tab = dialog.intiface_tab
    tab.server.setText("ws://the-address-the-user-typed:1")
    tab.enabled.click()
    assert not tab.enabled.isChecked()
    configure.assert_not_called()


def test_enabling_with_no_address_says_so_instead_of_connecting(app, dialog, allow_consent, monkeypatch):
    configure = MagicMock()
    monkeypatch.setattr(app.intiface.controller, "configure", configure)
    tab = dialog.intiface_tab
    tab.enabled.click()
    assert not tab.enabled.isChecked()
    assert "Intiface Central" in tab.error.text()
    assert allow_consent == []
    configure.assert_not_called()


def test_the_stroke_range_is_applied_on_save(app, dialog, allow_consent, monkeypatch):
    configure = MagicMock()
    monkeypatch.setattr(app.intiface.controller, "configure", configure)
    tab = dialog.intiface_tab
    tab.server.setText("ws://the-address-the-user-typed:1")
    tab.minimum.setValue(15)
    tab.maximum.setValue(85)
    dialog.accept_settings()
    configure.assert_called_once_with(False, "ws://the-address-the-user-typed:1", 0.15, 0.85)


def test_saving_unrelated_settings_does_not_touch_the_connection(app, dialog, monkeypatch):
    configure = MagicMock()
    monkeypatch.setattr(app.intiface.controller, "configure", configure)
    dialog.accept_settings()
    configure.assert_not_called()


@pytest.mark.parametrize("action", ["panic", "close"])
def test_panic_and_exit_stop_the_device_even_with_no_session_running(app, monkeypatch, action):
    cancelled = MagicMock()
    monkeypatch.setattr(app.intiface.controller, "cancel_motion", cancelled)
    getattr(app, action)()
    assert cancelled.called


def test_a_rhythm_pause_gates_device_sync(app):
    app.session_started_event.emit()
    app.beat_handler.beat_paused_event.emit()
    assert app.intiface.paused
    app.beat_handler.beat_resumed_event.emit()
    assert not app.intiface.paused


def test_the_settings_dialog_builds_without_the_plugin_installed(app, qtbot):
    """Deleting src/plugins/intiface/ has to leave a working app behind, which is the
    whole reason device support is a folder rather than two more modules in src/."""
    app.intiface = None
    dialog = SettingsDialog(app)
    qtbot.addWidget(dialog)
    assert dialog.intiface_tab is None
    titles = [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())]
    assert not any("Device" in title for title in titles)
    dialog.accept_settings()


def _already_connected_to(app, address):
    app.intiface.controller.enabled = True
    app.intiface.controller.server_url = address


def test_saving_a_different_address_asks_before_connecting_to_it(app, dialog, allow_consent, monkeypatch):
    """Consent names the address it is for, and says plainly that one which is not this
    machine crosses your network. Agreeing to a server on your desk and then being moved
    to another one by a Save would make that promise worth nothing."""
    _already_connected_to(app, "ws://the-address-i-agreed-to:1")
    configure = MagicMock()
    monkeypatch.setattr(app.intiface.controller, "configure", configure)
    tab = dialog.intiface_tab
    tab.enabled.setChecked(True)
    tab.server.setText("ws://somewhere-else-entirely:1")

    dialog.accept_settings()

    assert allow_consent == ["ws://somewhere-else-entirely:1"]
    configure.assert_called_once_with(True, "ws://somewhere-else-entirely:1", 0.25, 0.75)


def test_declining_the_new_address_leaves_the_connection_where_it_was(app, dialog, monkeypatch):
    monkeypatch.setattr(
        "src.plugins.intiface.settings_widget.confirm_device_output",
        lambda parent, url, settings: False,
    )
    _already_connected_to(app, "ws://the-address-i-agreed-to:1")
    configure = MagicMock()
    monkeypatch.setattr(app.intiface.controller, "configure", configure)
    tab = dialog.intiface_tab
    tab.enabled.setChecked(True)
    tab.server.setText("ws://somewhere-else-entirely:1")

    dialog.accept_settings()

    configure.assert_not_called()
    # What is on screen has to match what is actually connected.
    assert tab.server.text() == "ws://the-address-i-agreed-to:1"


def test_saving_only_the_stroke_range_does_not_ask_again(app, dialog, allow_consent, monkeypatch):
    _already_connected_to(app, "ws://the-address-i-agreed-to:1")
    configure = MagicMock()
    monkeypatch.setattr(app.intiface.controller, "configure", configure)
    tab = dialog.intiface_tab
    tab.enabled.setChecked(True)
    tab.server.setText("ws://the-address-i-agreed-to:1")
    tab.minimum.setValue(30)

    dialog.accept_settings()

    assert allow_consent == []
    configure.assert_called_once_with(True, "ws://the-address-i-agreed-to:1", 0.30, 0.75)
