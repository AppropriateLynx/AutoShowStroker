"""The device's one control in the main window.

Device sync latches off after a panic, a lost connection or an emergency stop, and it
stays off until the user says otherwise - see IntifacePlugin for why that is deliberate.
Something has to say so where they can see it, and be the way back in one click. Until
this existed the only route was Settings > Device mid-session, which nobody does.

It doubles as the disclosure the app owes: while device output is on, there is an open
network connection, and a window that says nothing about it is not being straight with
anyone. Hence a button that exists only while the feature does.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton

RESUME_TEXT = "Resume Device"
STOP_TEXT = "Stop Device"


class DeviceStatusButton(QPushButton):
    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        # Space is Panic, and a focused QPushButton swallows Space before keyPressEvent
        # ever sees it (the same reason every other button in this row is NoFocus). A
        # device button that ate the panic key would be a special kind of bad.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clicked.connect(self._clicked)
        plugin.state_changed.connect(self.refresh)
        self.refresh()

    def _clicked(self):
        # Mirrors Mute/Unmute right next to it: the button is whichever of the two things
        # is worth doing now.
        if self.plugin.armed:
            self.plugin.emergency_stop()
        else:
            self.plugin.resume_sync()

    def refresh(self):
        plugin = self.plugin
        controller = plugin.controller
        self.setVisible(controller.enabled)
        if not controller.enabled:
            return
        if plugin.armed:
            self.setText(STOP_TEXT)
            self.setEnabled(True)
            self.setToolTip(
                "Device sync is running on a rhythm pause - it comes back on its own"
                if plugin.paused else "Stop the device without ending the session"
            )
        elif plugin.can_resume:
            self.setText(RESUME_TEXT)
            self.setEnabled(True)
            self.setToolTip("Device sync stopped. It stays stopped until you say so.")
        else:
            self.setEnabled(False)
            self.setToolTip(controller.status)
            if not controller.device_name:
                self.setText("No device")
            else:
                self.setText("Device ready")
        # The accent styling belongs to the one state that is asking for a click.
        self.setObjectName("primary" if self.text() == RESUME_TEXT else "")
        self.style().unpolish(self)
        self.style().polish(self)
