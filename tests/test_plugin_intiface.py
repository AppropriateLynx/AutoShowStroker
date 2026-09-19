"""Protocol tests use a local fake server, never Intiface or physical hardware."""
import json
import logging
import time

import pytest
from PyQt6.QtCore import QThread
from PyQt6.QtNetwork import QHostAddress
from PyQt6.QtWebSockets import QWebSocketServer

from src.plugins.intiface import controller as controller_module
from src.plugins.intiface.controller import IntifaceController


def linear_device(index=7, name="Test Linear"):
    return {
        "DeviceIndex": index, "DeviceName": name,
        "DeviceMessages": {"LinearCmd": [{"ActuatorType": "Linear", "StepCount": 100}]},
    }


@pytest.fixture
def server(qtbot):
    server = QWebSocketServer("Test Intiface", QWebSocketServer.SslMode.NonSecureMode)
    assert server.listen(QHostAddress.SpecialAddress.LocalHost, 0)
    server.messages = []
    server.clients = []
    server.devices = [linear_device()]
    server.max_ping_time = 200
    server.respond = True

    def accept():
        socket = server.nextPendingConnection()
        server.clients.append(socket)

        def received(raw):
            for message in json.loads(raw):
                server.messages.append(message)
                kind, body = next(iter(message.items()))
                if not server.respond:
                    continue
                if kind == "RequestServerInfo":
                    answer = {"ServerInfo": {
                        "Id": body["Id"], "MessageVersion": 3,
                        "ServerName": "Test", "MaxPingTime": server.max_ping_time,
                    }}
                elif kind == "RequestDeviceList":
                    answer = {"DeviceList": {"Id": body["Id"], "Devices": server.devices}}
                else:
                    answer = {"Ok": {"Id": body["Id"]}}
                socket.sendTextMessage(json.dumps([answer]))

        socket.textMessageReceived.connect(received)

    server.newConnection.connect(accept)
    yield server
    for client in server.clients:
        client.abort()
    server.close()


@pytest.fixture
def controller(qsettings, qtbot):
    controller = IntifaceController(qsettings)
    yield controller
    controller.shutdown()
    qtbot.waitUntil(lambda: not controller.has_worker, timeout=3000)


def connect(controller, server, qtbot):
    controller.configure(True, f"ws://127.0.0.1:{server.serverPort()}", 0.15, 0.85)
    qtbot.waitUntil(lambda: bool(controller.device_name), timeout=3000)


def commands(server, kind):
    return [message[kind] for message in server.messages if kind in message]


def test_disabled_by_default_never_starts_a_worker(controller):
    assert not controller.enabled
    assert not controller.has_worker


@pytest.mark.parametrize("saved_url", ["", "   "])
def test_empty_saved_address_uses_local_default(qsettings, saved_url):
    qsettings.setValue("IntifaceController/server_url", saved_url)
    fresh = IntifaceController(qsettings)
    assert fresh.server_url == "ws://0.0.0.0:12345"
    assert not fresh.has_worker
    assert not fresh.enabled


def test_wildcard_address_connects_to_loopback(controller, server, qtbot):
    url = f"ws://0.0.0.0:{server.serverPort()}"
    controller.configure(True, url, 0.25, 0.75)
    qtbot.waitUntil(lambda: bool(controller.device_name), timeout=3000)
    assert controller.device_name == "Test Linear"
    assert controller.server_url == url
    assert controller.settings.value("IntifaceController/server_url") == url
    assert commands(server, "RequestServerInfo")[0]["MessageVersion"] == 3


@pytest.mark.parametrize("url,low,high", [
    ("https://localhost", 0.1, 0.9), ("ws://", 0.1, 0.9),
    ("ws://localhost:99999", 0.1, 0.9), ("ws://localhost", -0.1, 0.9),
    ("ws://localhost", 0.9, 0.1), ("ws://localhost", 0.5, 0.5),
    ("ws://localhost", float("nan"), 0.9),
])
def test_invalid_configuration_does_not_enable_networking(controller, url, low, high):
    with pytest.raises(ValueError):
        controller.configure(True, url, low, high)
    assert not controller.has_worker
    assert not controller.enabled


def test_handshake_scan_and_linear_selection_run_off_ui_thread(controller, server, qtbot):
    server.devices.insert(0, {"DeviceIndex": 0, "DeviceName": "Not linear", "DeviceMessages": {}})
    connect(controller, server, qtbot)
    assert controller.device_name == "Test Linear"
    assert controller._worker.thread() != QThread.currentThread()
    assert commands(server, "RequestServerInfo")[0]["MessageVersion"] == 3
    qtbot.waitUntil(lambda: bool(commands(server, "StartScanning")))
    qtbot.waitUntil(lambda: bool(commands(server, "Ping")))


@pytest.mark.parametrize("feature", [
    {"ActuatorType": "Position", "StepCount": 100},
    {"ActuatorType": None, "StepCount": 100},
    {"StepCount": 100},
], ids=["alternate-actuator-label", "null-actuator-label", "omitted-actuator-label"])
def test_linear_capability_accepts_simulated_device_metadata(controller, server, qtbot, feature):
    # LinearCmd is the capability. Simulated devices need not repeat "Linear" in
    # ActuatorType; filtering by that label prevented them from being selected.
    server.devices[0]["DeviceMessages"]["LinearCmd"] = [feature]
    connect(controller, server, qtbot)
    controller.test_up()
    qtbot.waitUntil(lambda: bool(commands(server, "LinearCmd")))
    move = commands(server, "LinearCmd")[-1]
    assert move["DeviceIndex"] == 7
    assert move["Vectors"][0]["Index"] == 0
    assert move["Vectors"][0]["Position"] == 0.85


def test_predictive_target_uses_remaining_deadline_and_configured_range(controller, server, qtbot):
    connect(controller, server, qtbot)
    controller.on_target(True, time.monotonic() + 0.5)
    qtbot.waitUntil(lambda: bool(commands(server, "LinearCmd")))
    move = commands(server, "LinearCmd")[-1]
    assert move["DeviceIndex"] == 7
    vector = move["Vectors"][0]
    assert vector["Index"] == 0
    assert vector["Position"] == 0.85
    assert 1 <= vector["Duration"] <= 500
    controller.on_target(False, time.monotonic() + 0.5)
    qtbot.waitUntil(lambda: len(commands(server, "LinearCmd")) == 2)
    assert commands(server, "LinearCmd")[-1]["Vectors"][0]["Position"] == 0.15


def test_a_target_whose_note_has_already_landed_is_never_sent(controller, server, qtbot):
    """Its whole meaning is "be there by then". Once then has passed, sending it would
    only make the device travel to an endpoint the beat has moved on from."""
    connect(controller, server, qtbot)
    controller.on_target(True, time.monotonic() - 1)
    qtbot.wait(80)
    assert not commands(server, "LinearCmd")
    controller.on_target(False, time.monotonic() + 0.5)
    qtbot.waitUntil(lambda: len(commands(server, "LinearCmd")) == 1)


def test_cancelling_motion_stops_the_device_and_voids_what_was_queued(controller, server, qtbot):
    """The epoch gate exists for the gap between the two threads: a target handed over a
    moment before the stop must not still arrive a moment after it."""
    connect(controller, server, qtbot)
    controller.on_target(True, time.monotonic() + 1)
    controller.cancel_motion()
    qtbot.waitUntil(lambda: bool(commands(server, "StopAllDevices")))
    qtbot.wait(80)
    assert not commands(server, "LinearCmd")


def test_a_test_move_uses_the_configured_endpoints(controller, server, qtbot):
    connect(controller, server, qtbot)
    controller.test_up()
    qtbot.waitUntil(lambda: bool(commands(server, "LinearCmd")))
    assert commands(server, "LinearCmd")[-1]["Vectors"][0]["Position"] == 0.85
    controller.test_down()
    qtbot.waitUntil(lambda: len(commands(server, "LinearCmd")) == 2)
    assert commands(server, "LinearCmd")[-1]["Vectors"][0]["Position"] == 0.15


def test_a_movement_queued_for_a_lost_device_never_reaches_its_replacement(controller, server, qtbot):
    connect(controller, server, qtbot)
    server.clients[-1].sendTextMessage(json.dumps([{"DeviceRemoved": {"Id": 0, "DeviceIndex": 7}}]))
    qtbot.waitUntil(lambda: not controller.device_name)
    controller.on_target(True, time.monotonic() + 1)
    server.clients[-1].sendTextMessage(json.dumps([{"DeviceAdded": {"Id": 0, **linear_device(9)}}]))
    qtbot.waitUntil(lambda: bool(controller.device_name))
    qtbot.wait(80)
    assert not commands(server, "LinearCmd")


def test_a_reconnect_never_replays_what_the_old_connection_was_holding(controller, server, qtbot):
    connect(controller, server, qtbot)
    server.clients[-1].abort()
    qtbot.waitUntil(lambda: not controller.device_name)
    controller.on_target(True, time.monotonic() + 10)
    qtbot.waitUntil(lambda: len(server.clients) == 2 and bool(controller.device_name), timeout=5000)
    assert not commands(server, "LinearCmd")


def test_disable_stops_and_does_not_reconnect(controller, server, qtbot):
    connect(controller, server, qtbot)
    controller.configure(False, controller.server_url, 0.15, 0.85)
    qtbot.waitUntil(lambda: bool(commands(server, "StopAllDevices")))
    qtbot.waitUntil(lambda: not controller.device_name)
    assert not controller.enabled


def test_shutdown_sends_stop_before_worker_finishes(controller, server, qtbot):
    connect(controller, server, qtbot)
    controller.shutdown()
    qtbot.waitUntil(lambda: not controller.has_worker)
    assert commands(server, "StopAllDevices")


def test_stop_cancels_movement_waiting_for_device_timing_gap(controller, server, qtbot):
    server.devices[0]["DeviceMessageTimingGap"] = 300
    connect(controller, server, qtbot)
    controller.on_target(True, time.monotonic() + 1)
    qtbot.waitUntil(lambda: len(commands(server, "LinearCmd")) == 1)
    controller.on_target(False, time.monotonic() + 1)
    controller.cancel_motion()
    qtbot.waitUntil(lambda: bool(commands(server, "StopAllDevices")))
    qtbot.wait(350)
    assert len(commands(server, "LinearCmd")) == 1


def test_device_timing_gap_coalesces_to_latest_unexpired_target(controller, server, qtbot):
    server.devices[0]["DeviceMessageTimingGap"] = 200
    connect(controller, server, qtbot)
    controller.on_target(True, time.monotonic() + 1)
    qtbot.waitUntil(lambda: len(commands(server, "LinearCmd")) == 1)
    controller.on_target(False, time.monotonic() + 0.03)
    controller.on_target(True, time.monotonic() + 1)
    qtbot.waitUntil(lambda: len(commands(server, "LinearCmd")) == 2)
    assert commands(server, "LinearCmd")[-1]["Vectors"][0]["Position"] == 0.85


def test_unanswered_commands_disconnect_and_stop(controller, server, qtbot, monkeypatch):
    monkeypatch.setattr("src.plugins.intiface.controller.REQUEST_TIMEOUT_MS", 300)
    connect(controller, server, qtbot)
    server.respond = False
    controller.on_target(True, time.monotonic() + 1)
    qtbot.waitUntil(lambda: not controller.device_name, timeout=2000)
    assert "stopped responding" in controller.status


def test_malformed_server_message_stops_without_a_slot_exception(controller, server, qtbot):
    connect(controller, server, qtbot)
    server.clients[-1].sendTextMessage('{broken')
    qtbot.waitUntil(lambda: not controller.device_name)
    assert commands(server, "StopAllDevices")


def test_unsupported_devices_never_receive_motion(controller, server, qtbot):
    server.devices = [{"DeviceIndex": 0, "DeviceName": "Not linear", "DeviceMessages": {"ScalarCmd": [{}]}}]
    controller.configure(True, f"ws://127.0.0.1:{server.serverPort()}", 0.1, 0.9)
    qtbot.waitUntil(lambda: "no linear device" in controller.status)
    controller.test_up()
    qtbot.wait(50)
    assert not commands(server, "LinearCmd")


def test_the_window_goes_at_once_and_the_device_is_stopped_behind_it(app, server, qtbot):
    """In an app with a panic key, off-the-screen is the part that has to be instant.
    Waiting for a socket to close before the window disappears is the wrong way round."""
    connect(app.intiface.controller, server, qtbot)
    app.show()
    app.close()
    assert not app.isVisible()
    qtbot.waitUntil(lambda: not app.intiface.controller.has_worker, timeout=3000)
    assert commands(server, "StopAllDevices")


def test_invalid_device_gap_is_rejected_without_a_slot_exception(controller, server, qtbot):
    server.devices[0]["DeviceMessageTimingGap"] = "invalid"
    controller.configure(True, f"ws://127.0.0.1:{server.serverPort()}", 0.1, 0.9)
    qtbot.waitUntil(lambda: "Invalid Intiface response" in controller.status, timeout=1500)
    assert not controller.device_name


# --- safety boundary -----------------------------------------------------------------
# Everything below is about what happens when the far end is broken or hostile. A device
# that keeps moving because the app fell over is the one failure mode worth this much
# test code.


def test_a_command_is_never_sent_with_the_motion_lock_held(controller, server, qtbot, monkeypatch):
    """Qt can emit errorOccurred synchronously from inside sendTextMessage on a half-open
    socket, and that lands back in _fail -> stop -> _clear_connection -> invalidate(),
    which takes this same lock on this same thread. Holding it across the write deadlocks
    the worker with the lock held - and the next emergency stop from the GUI thread then
    blocks on it too, freezing the window with a device still running."""
    original = controller_module._IntifaceWorker._send
    lock_was_free = []

    def checking_send(self, kind, **fields):
        if kind == "LinearCmd":
            acquired = self._gate.lock.acquire(blocking=False)
            lock_was_free.append(acquired)
            if acquired:
                self._gate.lock.release()
        return original(self, kind, **fields)

    monkeypatch.setattr(controller_module._IntifaceWorker, "_send", checking_send)
    connect(controller, server, qtbot)
    controller.on_target(True, time.monotonic() + 1)
    qtbot.waitUntil(lambda: bool(lock_was_free))
    assert all(lock_was_free)


def test_a_message_that_blows_the_parser_stack_stops_rather_than_killing_the_process(
    controller, server, qtbot,
):
    """RecursionError is not one of the parsing errors, so it escaped the slot - and an
    exception escaping a Qt slot takes the process with it. A process that is gone sends
    no stop, which makes the one failure nobody anticipated the one that leaves a device
    running."""
    connect(controller, server, qtbot)
    server.clients[-1].sendTextMessage("[" * 5000 + "]" * 5000)
    qtbot.waitUntil(lambda: not controller.device_name)
    assert commands(server, "StopAllDevices")
    assert "Invalid Intiface response" in controller.status


def test_a_stop_still_goes_out_after_the_device_has_been_removed(controller, server, qtbot):
    """StopDeviceCmd needs a device index and there no longer is one. Hardware working
    through a Duration it was already handed is exactly when a stop matters most."""
    connect(controller, server, qtbot)
    server.clients[-1].sendTextMessage(json.dumps([{"DeviceRemoved": {"Id": 0, "DeviceIndex": 7}}]))
    qtbot.waitUntil(lambda: not controller.device_name)
    controller.shutdown()
    qtbot.waitUntil(lambda: not controller.has_worker, timeout=3000)
    assert commands(server, "StopAllDevices")


def test_a_hostile_heartbeat_interval_cannot_make_the_app_spin(controller, server, qtbot):
    """A server asking to be pinged every millisecond gets a hundred milliseconds. Each
    ping books an entry in the pending table, so obeying that literally would be a
    thousand messages a second and a table that never empties."""
    server.max_ping_time = 1
    connect(controller, server, qtbot)
    qtbot.wait(400)
    assert 1 <= len(commands(server, "Ping")) <= 8


def test_the_server_address_never_reaches_the_log(controller, server, qtbot):
    """It is the user\'s address and it may name a machine on their network, which puts
    it under the same rule as a media folder path."""
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logging.getLogger("gooner").addHandler(handler)
    try:
        connect(controller, server, qtbot)
        server.clients[-1].sendTextMessage("{broken")
        qtbot.waitUntil(lambda: not controller.device_name)
    finally:
        logging.getLogger("gooner").removeHandler(handler)
    written = "\n".join(handler.format(record) for record in records)
    assert str(server.serverPort()) not in written
    assert "127.0.0.1" not in written
    assert "Test Linear" not in written


def dead_port():
    """A port on loopback that is definitely closed: bind one, note it, let it go."""
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_a_failure_teardown_cannot_restart_itself(qtbot):
    """QWebSocket.close() on a socket whose connect attempt has just failed emits
    errorOccurred again, synchronously, straight back into the handler that called it.
    Without a latch the teardown re-enters itself for as long as the stack lasts and the
    app dies of a RecursionError - inside a Qt slot, so it takes the process with it."""
    worker = controller_module._IntifaceWorker(controller_module._MotionGate())
    worker.initialize()
    worker._enabled = True
    closes = []

    def reentrant_close():
        closes.append(True)
        worker._fail("the error that closing caused")

    worker._socket.close = reentrant_close
    worker._fail("the first error")
    assert len(closes) == 1
    worker._retry.stop()


def test_connecting_where_nothing_listens_reports_it_and_keeps_the_app_alive(controller, qtbot):
    """The first thing most people will do is enable this before starting the server."""
    controller.configure(True, f"ws://127.0.0.1:{dead_port()}", 0.25, 0.75)
    qtbot.waitUntil(lambda: "retrying" in controller.status, timeout=5000)
    qtbot.wait(300)
    assert not controller.device_name
    assert controller.has_worker
