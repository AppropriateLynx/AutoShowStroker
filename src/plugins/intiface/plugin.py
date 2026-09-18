"""The whole of what the app has to know about device support.

Everything under src/plugins/intiface/ can be deleted and the app carries on without it:
GoonerApp looks the package up before importing it, and the Device tab simply is not
built. That is the reason it is a folder rather than another pair of modules in src/ -
device support is optional in a way that the Strokemeter and the climax are not, and
somebody who does not own a stroker should be able to remove it outright.

The arrangement inside is three objects with one job each. BeatSync reads the rhythm,
IntifaceController talks to the server, and this class decides when the two are allowed to
be connected to each other - which is the only question either of them cannot answer
alone.
"""
from PyQt6.QtCore import QObject, pyqtSignal

from src.applog import get_logger
from src.plugins.intiface.beat_sync import BeatSync
from src.plugins.intiface.controller import IntifaceController

log = get_logger("intiface")


class IntifacePlugin(QObject):
    """Arming policy and the app-facing surface."""

    TAB_TITLE = "Device (Beta)"

    state_changed = pyqtSignal()
    shutdown_finished = pyqtSignal()

    def __init__(self, main_app):
        super().__init__(main_app)
        self.main_app = main_app
        self.controller = IntifaceController(main_app.settings, parent=self)
        self.sync = BeatSync(main_app.beat_handler, self.controller, parent=self)
        self.session_active = False
        self.controller.state_changed.connect(self.state_changed)
        self.controller.shutdown_finished.connect(self.shutdown_finished)
        self.controller.device_found.connect(self._on_device_found)
        self.controller.device_lost.connect(self.emergency_stop)

    def attach(self):
        """Subscribes to the app. Every hook here is a signal the app already had, or a
        generic one - nothing in GoonerApp or BeatHandler names this plugin."""
        self.sync.attach()
        self.main_app.register_start_event(self._session_started)
        self.main_app.register_end_event(self._session_ended)
        self.main_app.panic_event.connect(self.emergency_stop)

    # --- state the Device tab reads -------------------------------------------------

    @property
    def armed(self):
        return self.sync.armed

    @property
    def paused(self):
        return self.sync.paused

    @property
    def can_resume(self):
        return bool(
            self.controller.enabled and self.controller.device_name
            and self.session_active and not self.armed
        )

    # --- arming policy ----------------------------------------------------------------

    def _session_started(self):
        self.session_active = True
        self._arm_if_possible()

    def _session_ended(self):
        self.session_active = False
        self.emergency_stop()

    def _on_device_found(self):
        # A device turning up during a running session is the connection finally
        # arriving, not a resume, so it arms. Losing one latches sync off instead.
        self._arm_if_possible()

    def _arm_if_possible(self):
        if self.controller.enabled and self.controller.device_name and self.session_active:
            self.sync.arm()
        self.state_changed.emit()

    def resume_sync(self):
        self._arm_if_possible()

    def emergency_stop(self):
        self.sync.disarm()
        self.state_changed.emit()

    # --- app lifecycle -----------------------------------------------------------------

    def settings_tab(self, parent=None):
        from src.plugins.intiface.settings_widget import IntifaceSettingsWidget
        return IntifaceSettingsWidget(self, parent)

    def shutdown(self):
        """Returns True when the app has to wait for shutdown_finished before closing."""
        self.emergency_stop()
        self.controller.shutdown()
        return self.controller.has_worker

    def forget_settings(self):
        """Called when the user wipes their settings under Help > Privacy & Data."""
        self.emergency_stop()
        self.controller.disconnect_and_forget()
