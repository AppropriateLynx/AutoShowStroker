import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from src import theme

# How far into the future the track shows. Fixed rather than scaled to the current
# frequency, so a faster beat reads as denser notes - the way a rhythm game conveys
# difficulty - instead of everything always looking the same.
LEAD_TIME_SEC = 2.5
FRAME_INTERVAL_MS = 16  # ~60fps
HIT_ZONE_X_RATIO = 0.12
HIT_ZONE_WIDTH = 6
NOTE_RADIUS = 11
FLASH_MS = 130
CAPTION_MARGIN = 10
CAPTION_PADDING = 4
TRACK_INSET = 4

# A sweep of light runs across the track when the rhythm changes. It used to do a job -
# the prediction was re-seeded at every change, every note jumped at once, and the notes
# were faded back in to cover the pop. The session plan removed the pop: upcoming_beats()
# already knows the next segment, so the notes flow straight through the change and are
# never faded. The sweep stays purely as an announcement that the rhythm just changed.
CHANGE_FLASH_MS = 420
SWEEP_WIDTH_RATIO = 0.18

# Only the idle track has nothing to draw - upcoming_beats() is empty there anyway, so it
# shows just its caption. "pause" is deliberately NOT here: the segment waiting behind the
# pause is already planned, so its notes fly in across the last couple of seconds of the
# countdown. Suppressing them meant the track sat empty and then had notes appear halfway
# down it the instant the beat came back.
_NOTELESS_KINDS = ("idle",)

# (track background, caption color) per beat_meter_update_event kind. The track keeps a
# stable backdrop and only the accents move - unlike the old QLabel, which flashed its
# whole background on every beat because that was the only signal it could give.
KIND_COLORS = {
    "idle": (theme.SURFACE_DARK, theme.TEXT),
    "new_beat": (theme.SURFACE_DARK, theme.ACCENT),
    "pause": (theme.PAUSE, theme.TEXT),
}
_FALLBACK_COLORS = (theme.SURFACE_DARK, theme.TEXT)


class BeatTrackWidget(QWidget):
    """Guitar-Hero-style note highway: markers flow right-to-left toward a hit zone
    near the left edge and land exactly on the beat.

    Rendering is stateless - every frame asks BeatHandler.upcoming_beats() fresh rather
    than maintaining a spawned-note list. Nothing can drift out of sync, and a mid-flight
    pattern change simply corrects itself on the next frame. Since the session is planned
    ahead the prediction now runs past the next pattern change too, so the track shows the
    rhythm genuinely arriving rather than stopping at the edge of what is known.

    The only thing it needs from the handler is upcoming_beats(horizon_sec).
    """

    LEAD_TIME_SEC = LEAD_TIME_SEC
    FRAME_INTERVAL_MS = FRAME_INTERVAL_MS
    FLASH_MS = FLASH_MS
    CHANGE_FLASH_MS = CHANGE_FLASH_MS
    KIND_COLORS = KIND_COLORS

    def __init__(self, beat_handler, parent=None):
        super().__init__(parent)
        self.beat_handler = beat_handler
        self._caption = ""
        self._kind = "idle"
        self._flash_until = 0.0
        self._change_started_at = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Only runs while a session does - a free-running 60fps timer would repaint for
        # nothing on the start screen. update() on a hidden window is a no-op anyway, so
        # this also costs nothing after a Panic minimize.
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.update)

    # --- state ---

    def start(self):
        self.frame_timer.start(FRAME_INTERVAL_MS)

    def stop(self):
        self.frame_timer.stop()
        self.update()

    def set_status(self, text, kind):
        self._kind = kind
        self._caption = text
        self.update()

    def flash(self):
        self._flash_until = time.monotonic() + FLASH_MS / 1000
        self.update()

    def is_flashing(self) -> bool:
        return time.monotonic() < self._flash_until

    def pulse_change(self, _freq=None, _pattern_name=None):
        """Starts the pattern-change sweep. Takes beat_change_event's (freq, pattern_name)
        payload so it can be connected to it directly, but doesn't need either value."""
        self._change_started_at = time.monotonic()
        self.update()

    def _change_progress(self):
        """0.0 -> 1.0 across the transition, or None when no transition is running."""
        if self._change_started_at is None:
            return None
        elapsed = time.monotonic() - self._change_started_at
        if elapsed >= CHANGE_FLASH_MS / 1000:
            self._change_started_at = None
            return None
        return elapsed / (CHANGE_FLASH_MS / 1000)

    # --- geometry ---

    def _hit_zone_x(self) -> float:
        return self.width() * HIT_ZONE_X_RATIO

    def _note_x(self, seconds_until: float) -> float:
        """Maps 'lands in N seconds' to an x position: 0 sits on the hit zone, a full
        LEAD_TIME_SEC away sits at the right edge."""
        hit_x = self._hit_zone_x()
        return hit_x + (seconds_until / LEAD_TIME_SEC) * (self.width() - hit_x)

    def _notes_visible(self) -> bool:
        return self._kind not in _NOTELESS_KINDS

    def _visible_notes(self):
        """Upcoming audible steps as (seconds_from_now, weight).

        Silent steps are deliberately dropped rather than drawn as hollow markers - as
        ghosts they read like extra beats you were supposed to hit. The rests still show
        up, as the gaps they create in the spacing.
        """
        if not self._notes_visible():
            return []
        return [
            (seconds, weight)
            for seconds, is_audible, weight in self.beat_handler.upcoming_beats(LEAD_TIME_SEC)
            if is_audible
        ]

    def _caption_height(self) -> float:
        """Height of the band reserved for the caption. The caption gets its own band
        rather than sharing the notes' row - drawn over them it landed directly on top
        of incoming notes, worst of all in the squeezed-footer case."""
        if not self._caption:
            return 0
        return self.fontMetrics().height() + CAPTION_PADDING

    def _note_lane(self) -> tuple[float, float]:
        """(top, height) of the strip the notes travel through, below the caption band."""
        top = self._caption_height() + TRACK_INSET
        return top, max(1.0, self.height() - TRACK_INSET - top)

    def _note_center_y(self) -> float:
        top, height = self._note_lane()
        return top + height / 2

    def _note_radius(self) -> float:
        _top, height = self._note_lane()
        # Shrink rather than overflow when the climax banner squeezes the footer.
        return min(NOTE_RADIUS, max(3.0, height / 2 - 2))

    # --- painting ---

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        background, caption_color = KIND_COLORS.get(self._kind, _FALLBACK_COLORS)
        track_rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(track_rect, 8, 8)

        self._paint_hit_zone(painter)
        self._paint_notes(painter)
        self._paint_change_sweep(painter, track_rect)
        self._paint_caption(painter, track_rect, caption_color)

        painter.end()

    def _paint_hit_zone(self, painter) -> None:
        hit_x = self._hit_zone_x()
        top, height = self._note_lane()
        flashing = self.is_flashing()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.ACCENT if flashing else theme.SECONDARY))
        painter.drawRoundedRect(QRectF(hit_x - HIT_ZONE_WIDTH / 2, top, HIT_ZONE_WIDTH, height), 3, 3)
        if flashing:
            painter.setPen(QPen(QColor(theme.ACCENT), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            radius = self._note_radius() + 7
            painter.drawEllipse(QPointF(hit_x, self._note_center_y()), radius, radius)

    def _paint_notes(self, painter) -> None:
        notes = self._visible_notes()
        if not notes:
            return
        center_y = self._note_center_y()
        radius = self._note_radius()
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.ACCENT))
        for seconds_until, _weight in notes:
            painter.drawEllipse(QPointF(self._note_x(seconds_until), center_y), radius, radius)
        painter.restore()

    def _paint_change_sweep(self, painter, track_rect) -> None:
        progress = self._change_progress()
        if progress is None:
            return
        sweep_width = track_rect.width() * SWEEP_WIDTH_RATIO
        center_x = track_rect.left() - sweep_width + progress * (track_rect.width() + sweep_width * 2)

        glow = QColor(theme.ACCENT)
        gradient = QLinearGradient(center_x - sweep_width, 0.0, center_x + sweep_width, 0.0)
        edge = QColor(glow)
        edge.setAlpha(0)
        peak = QColor(glow)
        peak.setAlpha(int(190 * (1 - progress)))  # fades out as it crosses
        gradient.setColorAt(0.0, edge)
        gradient.setColorAt(0.5, peak)
        gradient.setColorAt(1.0, edge)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(track_rect, 8, 8)

    def _paint_caption(self, painter, track_rect, caption_color) -> None:
        if not self._caption:
            return
        painter.setPen(QColor(caption_color))
        text_rect = QRectF(
            track_rect.left() + CAPTION_MARGIN,
            track_rect.top(),
            max(1.0, track_rect.width() - CAPTION_MARGIN * 2),
            self._caption_height(),
        )
        # Vertically centered in the whole track while nothing is in flight (pause/idle),
        # otherwise kept to its own band at the top so notes never run underneath it.
        if not self._notes_visible():
            text_rect = QRectF(text_rect.left(), track_rect.top(), text_rect.width(), track_rect.height())
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            self._caption,
        )
