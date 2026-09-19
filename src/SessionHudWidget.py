"""The captions that float over the media while a session runs.

Three of them, all in the same grid cell as the picture itself: the callout the
CalloutHandler is currently saying, the personal-record chase in the top right, and the
clock in the top left. They are grouped because they are the same kind of thing - a line of
glowing text laid over whatever is playing, that appears when a session starts and is gone
when it ends - and because each of them was previously spelled out twice, once to build it
and once, two hundred lines away, to update it.

The widget owns whether a session is running. That used to be GoonerApp.is_running, read
from here across the file, with a comment in start() warning that it has to be set *before*
the session-started signal or these overlays would hide themselves at the moment they were
meant to appear. session_started() removes that ordering trap: the flag and the thing it
guards are now set by the same call.
"""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QGridLayout, QLabel, QWidget

from src import theme
from src.ScoreTracker import ScoreTracker
from src.utils import format_clock


class SessionHudWidget(QWidget):
    """Media with captions on top. `content` is the widget it overlays."""

    TICK_MS = 1000

    def __init__(self, content, score_tracker, show_record_chase=True, show_session_timer=True,
                 parent=None):
        super().__init__(parent)
        self.score_tracker = score_tracker
        self.show_record_chase = show_record_chase
        self.show_session_timer = show_session_timer
        self._running = False
        # The all-time bests as they stood when this session began. Held rather than read
        # live, because the chase is against the record you walked in with - once you beat
        # it mid-session, reading it fresh would have you chasing yourself.
        self._session_start_bests = {}

        self.callout_label = QLabel("")
        self.callout_label.setWordWrap(True)
        self.callout_label.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter)
        self.callout_label.setStyleSheet(f"""
                    color: {theme.ACCENT};
                    font-size: 24px;
                    padding: 8px;
                    background-color: rgba(45, 29, 58, 0.9);
                    border-radius: 10px;
                """)
        self.callout_label.hide()

        self.record_chase_label = self._build_caption()
        self.session_timer_label = self._build_caption()

        self._clock = QTimer(self)
        self._clock.timeout.connect(self.refresh_clock)

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        grid.addWidget(content, 0, 0)
        grid.addWidget(
            self.callout_label, 0, 0,
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter
        )
        grid.addWidget(
            self.record_chase_label, 0, 0,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight
        )
        grid.addWidget(
            self.session_timer_label, 0, 0,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

    @staticmethod
    def _build_caption():
        """A small glowing line in a corner. The chase and the clock were each spelled out
        separately with identical styling, which is the kind of duplication that drifts."""
        label = QLabel("")
        label.setStyleSheet(f"""
                    color: {theme.ACCENT};
                    font-size: 13px;
                    font-weight: bold;
                    padding: 6px 10px;
                    background-color: rgba(45, 29, 58, 0.85);
                    border-radius: 8px;
                """)
        glow = QGraphicsDropShadowEffect()
        glow.setColor(QColor(theme.ACCENT))
        glow.setBlurRadius(18)
        glow.setOffset(0, 0)
        label.setGraphicsEffect(glow)
        label.hide()
        return label

    # --- session lifecycle ---------------------------------------------------------------

    def session_started(self):
        self._running = True
        self._session_start_bests = self.score_tracker.get_all_time_bests()
        self._clock.start(self.TICK_MS)
        self.refresh()

    def session_ended(self):
        self._running = False
        self._clock.stop()
        self.record_chase_label.hide()
        self.session_timer_label.hide()

    # --- the captions ----------------------------------------------------------------------

    def refresh(self):
        """Re-evaluates both captions. Safe to call outside a session, which is what the
        settings dialog does after every save: without it, saving put a frozen clock back on
        screen counting from the previous session's start, and a chase reporting the
        previous session's numbers."""
        self.refresh_record_chase()
        self.refresh_clock()

    def refresh_record_chase(self):
        if not self._running or not self.show_record_chase:
            self.record_chase_label.hide()
            return
        status = self.score_tracker.record_chase_status(self._session_start_bests)
        if status is None:
            self.record_chase_label.hide()
            return
        metric, current, best = status
        label = ScoreTracker.PR_METRIC_LABELS[metric]
        current_text = ScoreTracker.format_metric_value(metric, current)
        if current >= best:
            text = f"\U0001f3c6 New {label} Record! {current_text}"
        else:
            best_text = ScoreTracker.format_metric_value(metric, best)
            text = f"\U0001f3c6 Closing in on your {label} record: {current_text} / {best_text}"
        self.record_chase_label.setText(text)
        self.record_chase_label.show()

    def refresh_clock(self):
        if not self._running or not self.show_session_timer:
            self.session_timer_label.hide()
            return
        elapsed = self.score_tracker.live_metrics().get("total_dur_sec", 0)
        self.session_timer_label.setText(f"⏱ {format_clock(elapsed)}")
        self.session_timer_label.show()

    # --- what the app is currently saying ---------------------------------------------------

    def show_tease(self, tease: str):
        self.callout_label.setText(tease)
        self.callout_label.show()

    def hide_tease(self):
        self.callout_label.hide()
        self.callout_label.setText("")
