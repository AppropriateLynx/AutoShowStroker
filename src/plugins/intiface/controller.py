"""Optional Buttplug v3 linear output. All WebSocket work lives in a QThread.

Protocol: https://buttplug.io/docs/spec-v3/spec/generic/#linearcmd
QtWebSockets ships with PyQt6; no hardware-specific library is needed.

This half knows about sockets and positions and nothing about rhythm - BeatSync is the
other way round. Neither one can only be tested through the other, which is the point.
"""
import json
import math
import threading
import time
from urllib.parse import urlsplit

from PyQt6.QtCore import QObject, QThread, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtNetwork import QAbstractSocket
from PyQt6.QtWebSockets import QWebSocket

from src.applog import get_logger

log = get_logger("intiface")
CONNECTED = QAbstractSocket.SocketState.ConnectedState
REQUEST_TIMEOUT_MS = 3000
RECONNECT_MS = 2000
# A server is free to ask for a heartbeat far faster than it could possibly need one, and
# every ping books an entry in _pending. Without a floor, MaxPingTime: 1 turns into a
# thousand messages a second.
MIN_PING_MS = 100
MAX_PING_MS = 1000
SETTINGS_PREFIX = "IntifaceController"


class _MotionGate:
    """Invalidates queued work immediately, before the worker receives Stop's slot.

    The lock covers an epoch read and nothing else. It deliberately does not span the
    socket write: Qt can emit errorOccurred synchronously from inside sendTextMessage on a
    half-open socket, and that lands back in _fail -> stop -> _clear_connection ->
    invalidate() on the same thread. This lock is not reentrant, so holding it across the
    write deadlocked the worker - with the lock held, so the next emergency stop from the
    GUI thread blocked on it too and froze the window with a device still running.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.epoch = 0

    def invalidate(self):
        with self.lock:
            self.epoch += 1

    def current(self):
        with self.lock:
            return self.epoch

    def is_current(self, epoch):
        with self.lock:
            return epoch == self.epoch


class _IntifaceWorker(QObject):
    status_changed = pyqtSignal(str)
    device_changed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, gate):
        super().__init__()
        self._gate = gate
        self._enabled = False
        self._closing = False
        self._ready = False
        self._device = None
        self._devices = {}
        self._pending = {}
        self._next_id = 0
        self._pending_move = None
        self._last_move_at = 0.0
        self._shutdown_stop_id = None
        self._failure_status = ""

    @pyqtSlot()
    def initialize(self):
        # Created here, after moveToThread: both socket and timers belong to the worker.
        self._socket = QWebSocket(parent=self)
        self._socket.setMaxAllowedIncomingMessageSize(1024 * 1024)
        self._socket.connected.connect(self._connected)
        self._socket.disconnected.connect(self._disconnected)
        self._socket.textMessageReceived.connect(self._receive)
        self._socket.errorOccurred.connect(lambda _error: self._fail("Intiface unavailable; retrying"))
        self._retry = self._timer(self._open)
        self._connect_timeout = self._timer(lambda: self._fail("Intiface connection timed out; retrying"))
        self._move_timer = self._timer(self._flush_move)
        self._shutdown_timer = self._timer(self._finish_shutdown)
        self._scan_timer = self._timer(lambda: self._send("StopScanning"))
        self._ping = self._timer(lambda: self._send("Ping"), single=False)
        self._watchdog = self._timer(self._check_timeouts, single=False)

    def _timer(self, callback, single=True):
        timer = QTimer(self)
        timer.setSingleShot(single)
        timer.timeout.connect(callback)
        return timer

    @pyqtSlot(bool, str)
    def configure(self, enabled, url):
        if self._closing:
            return
        self._enabled = enabled
        self._url = url
        self._failure_status = ""
        self._retry.stop()
        self.stop()
        self._socket.close()  # flush the stop before replacing the connection
        self._clear_connection()
        if enabled:
            self._retry.start(100)
            self.status_changed.emit("Connecting to Intiface…")
        else:
            log.info("Device output disabled; closing the Intiface connection")
            self.status_changed.emit("Intiface disabled")

    def _open(self):
        if not self._enabled or self._closing:
            return
        self._socket.abort()
        # The address is the user's own and may name a machine on their network, so it is
        # never written to the log - the same rule media folders follow.
        self._socket.open(QUrl(self._url))
        self._connect_timeout.start(REQUEST_TIMEOUT_MS)

    def _connected(self):
        self._retry.stop()
        self._failure_status = ""
        self._connect_timeout.stop()
        self._watchdog.start(100)
        log.info("Intiface connection open; negotiating Buttplug v3")
        self._send("RequestServerInfo", ClientName="GoonerApp", MessageVersion=3)

    def _clear_connection(self):
        self._gate.invalidate()
        self._ready = False
        self._device = None
        self._devices.clear()
        self._pending.clear()
        self._pending_move = None
        self._last_move_at = 0.0
        for timer in (self._connect_timeout, self._ping, self._watchdog, self._move_timer, self._scan_timer):
            timer.stop()
        self.device_changed.emit("")

    def _disconnected(self):
        self._clear_connection()
        if self._closing:
            self._finish_shutdown()
        elif self._enabled:
            log.info("Intiface connection closed; device sync stopped")
            self.status_changed.emit(self._failure_status or "Disconnected; retrying — device sync stopped")
            self._retry.start(RECONNECT_MS)

    def _fail(self, message):
        self._failure_status = message
        self.stop()
        self._socket.close()
        self._clear_connection()
        if self._closing:
            self._finish_shutdown()
        elif self._enabled:
            log.warning("Intiface device output stopped: %s", message)
            self.status_changed.emit(message)
            self._retry.start(RECONNECT_MS)

    def _send(self, kind, **fields):
        if self._socket.state() != CONNECTED:
            return None
        self._next_id += 1
        message_id = self._next_id
        self._pending[message_id] = (kind, time.monotonic())
        self._socket.sendTextMessage(json.dumps([{kind: {"Id": message_id, **fields}}]))
        return message_id

    def _check_timeouts(self):
        now = time.monotonic()
        if any(now - sent > REQUEST_TIMEOUT_MS / 1000 for _kind, sent in self._pending.values()):
            self._fail("Intiface stopped responding; reconnecting — device sync stopped")

    def _receive(self, raw):
        try:
            self._handle(raw)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            self._fail("Invalid Intiface response; device sync stopped")
        except Exception:
            # This is a safety boundary, not ordinary parsing. An exception escaping a Qt
            # slot tears the process down, and a torn-down process sends no stop, so the
            # one failure nobody anticipated is exactly the one that leaves a device
            # running. RecursionError out of json.loads on deeply nested input is the
            # concrete case; the traceback goes to the log because the next one won't be.
            log.exception("Unexpected failure while reading an Intiface message")
            self._fail("Invalid Intiface response; device sync stopped")

    def _handle(self, raw):
        messages = json.loads(raw)
        if not isinstance(messages, list):
            raise ValueError("Expected a message array")
        for message in messages:
            if not isinstance(message, dict) or len(message) != 1:
                raise ValueError("Invalid message envelope")
            kind, body = next(iter(message.items()))
            if not isinstance(body, dict):
                raise ValueError("Invalid message body")
            message_id = body.get("Id", 0)
            request = self._pending.pop(message_id, None)
            if kind == "Error":
                if request and request[0] in ("StartScanning", "StopScanning"):
                    self.status_changed.emit("Connected; scan unavailable — scan in Intiface Central")
                    continue
                self._fail("Intiface rejected a command; device sync stopped")
                return
            if request:
                expected = {"RequestServerInfo": "ServerInfo", "RequestDeviceList": "DeviceList"}
                if kind != expected.get(request[0], "Ok"):
                    raise ValueError("Response does not match request")
            if self._closing:
                if kind == "Ok" and message_id == self._shutdown_stop_id:
                    self._finish_shutdown()
                continue
            if kind == "ServerInfo" and request and request[0] == "RequestServerInfo":
                if body.get("MessageVersion") != 3:
                    raise ValueError("Server did not negotiate Buttplug v3")
                max_ping = int(body["MaxPingTime"])
                if max_ping < 0:
                    raise ValueError("Invalid heartbeat interval")
                self._ready = True
                if max_ping:
                    self._ping.start(max(MIN_PING_MS, min(max_ping // 2, MAX_PING_MS)))
                self._send("RequestDeviceList")
                self.scan()
                self.status_changed.emit("Connected; looking for a linear device")
            elif kind == "DeviceList" and self._ready and request and request[0] == "RequestDeviceList":
                self._devices = {d["DeviceIndex"]: d for d in body["Devices"]}
                self._select_device()
            elif kind == "DeviceAdded" and self._ready:
                self._devices[body["DeviceIndex"]] = body
                self._select_device()
            elif kind == "DeviceRemoved" and self._ready:
                self._devices.pop(body["DeviceIndex"], None)
                self._select_device()

    def _select_device(self):
        available = []
        for index, device in sorted(self._devices.items()):
            gap = device.get("DeviceMessageTimingGap", 0)
            if not isinstance(gap, int) or not 0 <= gap <= 2**31 - 1:
                raise ValueError("Invalid device timing gap")
            features = device.get("DeviceMessages", {}).get("LinearCmd", [])
            if not isinstance(features, list) or not isinstance(index, int) or index < 0:
                continue

            for feature_index, feature in enumerate(features):
                if isinstance(feature, dict):
                    available.append((index, feature_index, device))
                    break
        # Keep the chosen device while it exists; hotplugging another must not redirect motion.
        chosen = next((d for d in available if self._device and d[0] == self._device[0]), None)
        chosen = chosen or (available[0] if available else None)
        if chosen == self._device:
            if chosen is None:
                self.status_changed.emit("Connected; no linear device found")
            return
        self._gate.invalidate()
        self._pending_move = None
        self._move_timer.stop()
        self._device = chosen
        name = ""
        if chosen:
            name = str(chosen[2].get("DeviceDisplayName") or chosen[2].get("DeviceName", "Linear device"))
        # The model is deliberately left out: it is on screen in the Device tab already,
        # and a diagnostic log is not the place to write down what someone owns.
        log.info("Linear device %s", "selected" if chosen else "lost")
        self.device_changed.emit(name)
        self.status_changed.emit("Connected" if chosen else "Connected; no linear device found")

    @pyqtSlot()
    def scan(self):
        if self._ready and not self._closing:
            self._send("StartScanning")
            self._scan_timer.start(10000)

    @pyqtSlot(float, float, int)
    def move(self, position, deadline, epoch):
        if self._closing or not self._ready or self._device is None:
            return
        self._pending_move = (position, deadline, epoch)
        self._flush_move()

    def _flush_move(self):
        if self._pending_move is None or self._device is None:
            return
        position, deadline, epoch = self._pending_move
        now = time.monotonic()
        gap = max(0, int(self._device[2].get("DeviceMessageTimingGap", 0))) / 1000
        if not self._gate.is_current(epoch) or deadline <= now:
            self._pending_move = None
            return
        wait = self._last_move_at + gap - now
        if wait > 0:
            self._move_timer.start(max(1, math.ceil(wait * 1000)))
            return
        duration = max(1, min(2**32 - 1, int((deadline - now) * 1000)))
        self._pending_move = None
        # Recorded before the write, not after: _send can come back through _fail on a
        # half-open socket, and this must already be true by then.
        self._last_move_at = now
        self._send("LinearCmd", DeviceIndex=self._device[0], Vectors=[{
            "Index": self._device[1], "Duration": duration, "Position": position,
        }])

    @pyqtSlot()
    def stop(self):
        """StopAllDevices rather than StopDeviceCmd: it carries no device index, so a stop
        still goes out when the device was removed while its hardware is working through a
        Duration it has already been given."""
        self._pending_move = None
        self._move_timer.stop()
        if self._ready:
            return self._send("StopAllDevices")
        return None

    @pyqtSlot()
    def shutdown(self):
        if self._closing:
            return
        self._closing = True
        self._enabled = False
        self._retry.stop()
        self._shutdown_stop_id = self.stop()
        if self._shutdown_stop_id is None:
            self._finish_shutdown()
        else:
            self._shutdown_timer.start(500)

    def _finish_shutdown(self):
        self._shutdown_timer.stop()
        self._retry.stop()
        self._clear_connection()
        self._socket.blockSignals(True)
        self._socket.abort()
        self.finished.emit()


class IntifaceController(QObject):
    """GUI-facing connection state and safety latch. Networking is reached only through
    signals, and the rhythm is not reached at all - BeatSync calls on_target()."""

    # No address ships with the app. Intiface Central shows the one its own server is
    # listening on, which is the only one that can be right for a given machine - and
    # guessing on the user's behalf would mean baking a network address into a program
    # whose whole promise is that it does not contact any.
    DEFAULTS = {"server_url": "", "min_position": 0.25, "max_position": 0.75}
    state_changed = pyqtSignal()
    shutdown_finished = pyqtSignal()
    # Losing a device latches device sync off - nothing moves again until the user says
    # so. Finding the first one does not: that is not a resume, it is the connection
    # finally arriving, and latching there stranded anyone whose server came up a moment
    # after they pressed Start, with no way back except a settings dialog.
    device_found = pyqtSignal()
    device_lost = pyqtSignal()
    _configure_requested = pyqtSignal(bool, str)
    _move_requested = pyqtSignal(float, float, int)
    _stop_requested = pyqtSignal()
    _scan_requested = pyqtSignal()
    _shutdown_requested = pyqtSignal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._gate = _MotionGate()
        self._thread = None
        self._worker = None
        self._shutting_down = False
        self.device_name = ""
        self.status = "Intiface disabled"
        # Never restored from settings. Device output starts off at every launch and has
        # to be turned on deliberately, so a box ticked once months ago can never quietly
        # open a network connection on some later start.
        self.enabled = False
        for key, default in self.DEFAULTS.items():
            setattr(self, key, default)
        try:
            url = str(settings.value(f"{SETTINGS_PREFIX}/server_url", self.server_url))
            low = float(settings.value(f"{SETTINGS_PREFIX}/min_position", self.min_position))
            high = float(settings.value(f"{SETTINGS_PREFIX}/max_position", self.max_position))
            self.validate_positions(low, high)
            if url:
                self.validate_url(url)
            self.server_url, self.min_position, self.max_position = url, low, high
        except (ValueError, TypeError, OverflowError):
            self.status = "Invalid saved device settings; Intiface disabled"
            log.warning("Invalid saved Intiface settings; starting with device output disabled")

    @staticmethod
    def validate_url(url):
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in ("ws", "wss") or not parsed.hostname or parsed.fragment or parsed.username:
                raise ValueError
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                raise ValueError
        except ValueError:
            raise ValueError(
                "Enter the WebSocket address Intiface Central shows for its server "
                "(it starts with ws:// or wss://)."
            ) from None

    @staticmethod
    def validate_positions(low, high):
        if not (math.isfinite(low) and math.isfinite(high) and 0 <= low < high <= 1):
            raise ValueError("Stroke positions must satisfy 0% ≤ minimum < maximum ≤ 100%.")

    @property
    def has_worker(self):
        return self._thread is not None

    def _ensure_worker(self):
        if self.has_worker:
            return
        self._thread = QThread(self)
        self._worker = _IntifaceWorker(self._gate)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.initialize)
        self._configure_requested.connect(self._worker.configure)
        self._move_requested.connect(self._worker.move)
        self._stop_requested.connect(self._worker.stop)
        self._scan_requested.connect(self._worker.scan)
        self._shutdown_requested.connect(self._worker.shutdown)
        self._worker.status_changed.connect(self._on_status)
        self._worker.device_changed.connect(self._on_device)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._worker_finished)
        self._thread.start()

    @pyqtSlot(str)
    def _on_status(self, status):
        self.status = status
        self.state_changed.emit()

    @pyqtSlot(str)
    def _on_device(self, name):
        had_device = bool(self.device_name)
        self.device_name = name
        self._gate.invalidate()
        if name and not had_device:
            self.device_found.emit()
        elif had_device and not name:
            self.device_lost.emit()
        self.state_changed.emit()

    @pyqtSlot()
    def _worker_finished(self):
        self._thread.deleteLater()
        self._thread = None
        self._worker = None
        self.shutdown_finished.emit()

    def configure(self, enabled, url, low, high):
        """Applies and stores the connection settings. The URL only has to be a real one
        when the feature is being switched on: a half-typed address in a tab nobody is
        using must not be able to block the Save button of every other setting."""
        url = url.strip()
        self.validate_positions(low, high)
        if enabled:
            self.validate_url(url)
        if self._shutting_down:
            return
        self.cancel_motion()
        self.enabled, self.server_url, self.min_position, self.max_position = bool(enabled), url, low, high
        for key in self.DEFAULTS:
            self.settings.setValue(f"{SETTINGS_PREFIX}/{key}", getattr(self, key))
        if enabled:
            self._ensure_worker()
        if self.has_worker:
            self._configure_requested.emit(bool(enabled), url)
        else:
            self.status = "Intiface disabled"
        self.state_changed.emit()

    def disconnect_and_forget(self):
        """For Privacy & Data's "delete everything": a live network connection left up
        until the next restart is not what deleting your settings is supposed to mean."""
        self.configure(False, "", self.DEFAULTS["min_position"], self.DEFAULTS["max_position"])

    def cancel_motion(self):
        self._gate.invalidate()
        if self.has_worker:
            self._stop_requested.emit()

    def on_target(self, up, deadline):
        """The next audible note, handed over by BeatSync. Which position that is happens
        to be this half's business, and which note it is is none of it."""
        self._queue_move(self.max_position if up else self.min_position, deadline)

    def _queue_move(self, position, deadline):
        if self.enabled and self.device_name and not self._shutting_down:
            self._move_requested.emit(position, deadline, self._gate.current())

    def move_to(self, position, duration_ms):
        if not math.isfinite(position) or not self.min_position <= position <= self.max_position:
            raise ValueError("Position is outside the configured stroke range")
        if not math.isfinite(duration_ms) or not 1 <= duration_ms <= 2**32 - 1:
            raise ValueError("Movement duration must be a positive number of milliseconds")
        self._queue_move(position, time.monotonic() + duration_ms / 1000)

    def test_up(self):
        self.cancel_motion()
        self.move_to(self.max_position, 1000)

    def test_down(self):
        self.cancel_motion()
        self.move_to(self.min_position, 1000)

    def scan(self):
        if self.has_worker and self.enabled:
            self._scan_requested.emit()

    def shutdown(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        self.cancel_motion()
        if self.has_worker:
            self._shutdown_requested.emit()
