"""The Device tab.

The split here follows the dialog's contract rather than fighting it. Anything the app
stores - the server address and the stroke range - is written when you press Save, like
every other setting in this window. Turning device output on is not stored at all (it
starts off at every launch), so it is not a setting: it is an action, and it happens the
moment you tick it, which is also what makes the test buttons reachable without closing
and reopening the dialog first.
"""
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.plugins.intiface.consent import confirm_device_output

BETA_NOTICE = (
    "<b>Beta.</b> Device output has not been tested against physical hardware yet. "
    "Space is the panic key: it minimizes the window, mutes the sound and stops the "
    "device on the spot. Tell us how it went on the Discord."
)
ADDRESS_HINT = (
    "Start Intiface Central, start its server and connect your device there. Intiface "
    "Central shows the address its server is listening on - put that in below. The first "
    "device it offers with linear movement support is the one that gets used."
)
SYNC_NOTE = (
    "Panic, Emergency Stop, losing the device and losing the connection all leave device "
    "sync stopped. Use Resume Device Sync or start a new session to continue. Rhythm "
    "pauses resume on their own."
)


class IntifaceSettingsWidget(QWidget):
    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.controller = plugin.controller
        controller = self.controller
        layout = QVBoxLayout(self)

        beta = QLabel(BETA_NOTICE)
        beta.setWordWrap(True)
        layout.addWidget(beta)

        self.enabled = QCheckBox("Enable device output")
        self.enabled.setChecked(controller.enabled)
        self.enabled.clicked.connect(self._enable_clicked)
        layout.addWidget(self.enabled)

        explanation = QLabel(ADDRESS_HINT)
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        form = QFormLayout()
        self.server = QLineEdit(controller.server_url)
        form.addRow("Server:", self.server)
        self.minimum = self._position_box(controller.min_position)
        self.maximum = self._position_box(controller.max_position)
        form.addRow("Minimum position (DOWN):", self.minimum)
        form.addRow("Maximum position (UP):", self.maximum)
        layout.addLayout(form)

        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.device = QLabel()
        self.device.setWordWrap(True)
        self.sync_status = QLabel()
        for label in (self.status, self.device, self.sync_status):
            layout.addWidget(label)

        buttons = QHBoxLayout()
        self.test_up = QPushButton("Test Up")
        self.test_down = QPushButton("Test Down")
        self.stop = QPushButton("Emergency Stop")
        self.test_up.clicked.connect(controller.test_up)
        self.test_down.clicked.connect(controller.test_down)
        self.stop.clicked.connect(plugin.emergency_stop)
        for button in (self.test_up, self.test_down, self.stop):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.resume = QPushButton("Resume Device Sync")
        self.resume.clicked.connect(plugin.resume_sync)
        layout.addWidget(self.resume)
        self.scan = QPushButton("Scan for Devices")
        self.scan.clicked.connect(controller.scan)
        layout.addWidget(self.scan)

        note = QLabel(SYNC_NOTE)
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        plugin.state_changed.connect(self.refresh)
        self.refresh()

    @staticmethod
    def _position_box(position):
        box = QDoubleSpinBox()
        box.setRange(0, 100)
        box.setDecimals(1)
        box.setSuffix(" %")
        box.setValue(position * 100)
        return box

    def values(self):
        return (
            self.enabled.isChecked(), self.server.text().strip(),
            self.minimum.value() / 100, self.maximum.value() / 100,
        )

    def validation_error(self):
        """What stops these values from being saved, or None.

        The address is only checked when device output is being switched on. A half-typed
        address in a tab the user is not even using has no business blocking the Save
        button of every other setting in the dialog.
        """
        enabled, url, low, high = self.values()
        try:
            self.controller.validate_positions(low, high)
            if enabled:
                self.controller.validate_url(url)
        except ValueError as error:
            return str(error)
        return None

    def _enable_clicked(self, checked):
        """Ticking the box is the act of connecting, so it happens now rather than on
        Save - and it is where consent is asked for, because this is the moment something
        would actually leave the machine."""
        error = self.validation_error()
        self.error.setText(error or "")
        if error:
            self.enabled.setChecked(False)
            return
        _enabled, url, low, high = self.values()
        if checked and not confirm_device_output(self, url, self.controller.settings):
            self.enabled.setChecked(False)
            return
        self.controller.configure(checked, url, low, high)

    def apply_settings(self):
        """Called by SettingsDialog when the user saves."""
        values = self.values()
        current = (
            self.controller.enabled, self.controller.server_url,
            self.controller.min_position, self.controller.max_position,
        )
        if values != current:
            self.controller.configure(*values)

    def refresh(self):
        controller = self.controller
        ready = controller.enabled and bool(controller.device_name)
        self.enabled.setChecked(controller.enabled)
        self.status.setText(controller.status)
        self.device.setText(f"Device: {controller.device_name or 'No linear device connected'}")
        if not self.plugin.session_active:
            sync = "Device sync: waiting for a session"
        elif not self.plugin.armed:
            sync = "Device sync: stopped"
        elif self.plugin.paused:
            sync = "Device sync: rhythm pause"
        else:
            sync = "Device sync: active"
        self.sync_status.setText(sync)
        self.test_up.setEnabled(ready)
        self.test_down.setEnabled(ready)
        self.scan.setEnabled(controller.enabled)
        self.resume.setEnabled(self.plugin.can_resume)
