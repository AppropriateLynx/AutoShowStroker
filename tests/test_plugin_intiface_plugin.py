"""The arming policy: when the rhythm is allowed to reach the device at all.

No sockets here - the controller is left unconnected and only told what to believe about
itself. What is being tested is the decision, not the delivery.
"""
import pytest

from src.plugins.intiface.controller import IntifaceController


@pytest.fixture
def plugin(app):
    plugin = app.intiface
    plugin.controller.enabled = True
    plugin.controller.device_name = "Test Linear"
    return plugin


def test_starting_a_session_arms_device_sync(app, plugin):
    assert not plugin.armed
    app.session_started_event.emit()
    assert plugin.armed


def test_a_device_turning_up_mid_session_arms_without_being_asked(app, plugin):
    """The connection arriving a moment after Start is not a resume, and treating it as
    one stranded anyone whose server came up late: sync stayed off for the whole session
    with no way back except opening the settings dialog and finding the button."""
    plugin.controller.device_name = ""
    app.session_started_event.emit()
    assert not plugin.armed
    plugin.controller._on_device("Test Linear")
    assert plugin.armed


def test_losing_the_device_latches_sync_off(app, plugin):
    app.session_started_event.emit()
    plugin.controller._on_device("")
    assert not plugin.armed
    plugin.controller._on_device("Test Linear")
    assert plugin.armed


def test_panic_latches_sync_off(app, plugin):
    app.session_started_event.emit()
    app.panic()
    assert not plugin.armed


def test_the_end_of_a_session_latches_sync_off(app, plugin):
    app.session_started_event.emit()
    app.session_ended_event.emit()
    assert not plugin.armed
    assert not plugin.session_active


def test_sync_never_arms_without_a_session(plugin):
    plugin.resume_sync()
    assert not plugin.armed
    assert not plugin.can_resume


def test_resume_arms_again_after_an_emergency_stop(app, plugin):
    app.session_started_event.emit()
    plugin.emergency_stop()
    assert not plugin.armed
    assert plugin.can_resume
    plugin.resume_sync()
    assert plugin.armed


def test_device_output_is_off_at_every_launch(qsettings):
    """Not persisted on purpose: a box ticked once months ago must not be able to open a
    network connection on a later start without the user saying so again. The address is
    remembered, because retyping it every time would just make people write it down."""
    qsettings.setValue("IntifaceController/enabled", True)
    qsettings.setValue("IntifaceController/server_url", "ws://a-machine-the-user-picked:1")
    fresh = IntifaceController(qsettings)
    assert not fresh.enabled
    assert not fresh.has_worker
    assert fresh.server_url == "ws://a-machine-the-user-picked:1"
