"""Turns the rhythm into the next linear target.

The BeatHandler contributes exactly one thing to device support: `note_scheduled_event`,
which says "the rhythm has committed to its next note". Everything else is read off its
existing public surface - `upcoming_beats()` for when the next audible note lands (it
already walks silent steps, predicts across segment boundaries and takes the pattern
mutex), and `beat_meter_update_event` for which way the meter will show it. That is
deliberate, and it is the same rule the climax follows: the BeatHandler is only ever told
"be fast here" and never learns what is listening.

A target is sent once per audible note. The note's identity is simply how many notes have
played - `beat_event` counts them - so a re-prediction after a settings change or a resume
cannot make the device stroke twice for the same beat.
"""
import time

from PyQt6.QtCore import QObject

from src.applog import get_logger

log = get_logger("intiface")


class BeatSync(QObject):
    """Prediction and bookkeeping only. It never talks to a socket, and the controller
    never talks to the rhythm - that split is what keeps either one testable alone."""

    # Far enough ahead to contain the next audible note even at the slowest usable
    # rhythm with several silent steps in front of it. Only the first audible entry is
    # ever read, so a generous horizon costs nothing.
    HORIZON_SEC = 30.0

    def __init__(self, beat_handler, controller, parent=None):
        super().__init__(parent)
        self.beat_handler = beat_handler
        self.controller = controller
        self.armed = False
        self.paused = False
        self._note_id = 0
        self._sent_note_id = None
        # The direction the next audible note will be shown as. Mirrors BeatHandler's
        # is_red, which starts on DOWN and is deliberately not reset between sessions.
        self._next_up = False

    def attach(self):
        handler = self.beat_handler
        handler.note_scheduled_event.connect(self.on_note_scheduled)
        handler.beat_event.connect(self._on_beat)
        handler.beat_meter_update_event.connect(self._on_meter)
        handler.session_planned_event.connect(self._on_session_planned)
        handler.register_beat_pause_events(self._on_pause, self._on_pause_ended)

    def arm(self):
        """Start driving the device from the rhythm, beginning with the note in flight."""
        self.armed = True
        self._sent_note_id = None
        self.on_note_scheduled()

    def disarm(self):
        self.armed = False
        self._sent_note_id = None
        self.controller.cancel_motion()

    def on_note_scheduled(self):
        if not self.armed or self.paused or self._sent_note_id == self._note_id:
            return
        deadline = self._next_audible_deadline()
        if deadline is None:
            return
        self._sent_note_id = self._note_id
        self.controller.on_target(self._next_up, deadline)

    def _next_audible_deadline(self):
        """When the next audible note lands, on the monotonic clock, or None.

        upcoming_beats() also predicts through a running pause - there is a rhythm behind
        it and the note track draws it flying in. A device must not move during one, which
        is what `paused` above guards.
        """
        now = time.monotonic()
        for offset, audible, _weight in self.beat_handler.upcoming_beats(self.HORIZON_SEC):
            if audible:
                return now + offset
        return None

    def _on_beat(self):
        self._note_id += 1

    def _on_meter(self, _text, kind):
        # Every audible note carries a direction, so the device never has to guess at one:
        # whatever the meter just showed, the next note is the other way.
        if kind in ("up", "down"):
            self._next_up = kind == "down"

    def _on_session_planned(self, _start_time, _script):
        self.paused = False
        self._sent_note_id = None

    def _on_pause(self):
        self.paused = True
        self.controller.cancel_motion()

    def _on_pause_ended(self):
        self.paused = False
        self.on_note_scheduled()
