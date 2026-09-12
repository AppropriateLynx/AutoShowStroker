import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
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

# Kinds with nothing in flight to draw - upcoming_beats() is empty for both anyway
# (start_pause stops the beat timer), so the track shows just its caption.
_NOTELESS_KINDS = ("idle", "pause")

# (track background, caption color) per beat_meter_update_event kind. The track keeps a
# stable backdrop and only the accents move - unlike the old QLabel, which flashed its
# whole background on every beat because that was the only signal it could give.
KIND_COLORS = {
    "idle": (theme.SURFACE_DARK, theme.TEXT),
    "up": (theme.SURFACE_DARK, theme.TEXT),
    "down": (theme.SURFACE_DARK, theme.TEXT),
    "new_beat": (theme.SURFACE_DARK, theme.ACCENT),
    "pause": (theme.PAUSE, theme.TEXT),
}
_FALLBACK_COLORS = (theme.SURFACE_DARK, theme.TEXT)

# Kinds whose text is just the alternating blink caption - meaningless once notes
# visibly land on the hit zone, so they never overwrite the real caption.
_BLINK_KINDS = ("up", "down")


class BeatTrackWidget(QWidget):
    """Guitar-Hero-style note highway: markers flow right-to-left toward a hit zone
    near the left edge and land exactly on the beat.

    Rendering is stateless - every frame asks BeatHandler.upcoming_beats() fresh rather
    than maintaining a spawned-note list. Nothing can drift out of sync, and a mid-flight
    pattern change (recalc_beat picks a new random pattern, so the prediction beyond it
    was never knowable) simply corrects itself on the next frame.

    The only thing it needs from the handler is upcoming_beats(horizon_sec).
    """

    LEAD_TIME_SEC = LEAD_TIME_SEC
    FRAME_INTERVAL_MS = FRAME_INTERVAL_MS
    FLASH_MS = FLASH_MS
    KIND_COLORS = KIND_COLORS

    def __init__(self, beat_handler, parent=None):
        super().__init__(parent)
        self.beat_handler = beat_handler
        self._caption = ""
        self._kind = "idle"
        self._flash_until = 0.0

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
        if kind not in _BLINK_KINDS:
            self._caption = text
        self.update()

    def flash(self):
        self._flash_until = time.monotonic() + FLASH_MS / 1000
        self.update()

    def is_flashing(self) -> bool:
        return time.monotonic() < self._flash_until

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
        if self._notes_visible():
            self._paint_notes(painter)
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
        center_y = self._note_center_y()
        radius = self._note_radius()
        for seconds_until, is_audible, _weight in self.beat_handler.upcoming_beats(LEAD_TIME_SEC):
            center = QPointF(self._note_x(seconds_until), center_y)
            if is_audible:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(theme.ACCENT))
                painter.drawEllipse(center, radius, radius)
            else:
                # Silent steps drawn hollow: the rhythm's rests are part of its shape.
                painter.setPen(QPen(QColor(theme.PAUSE), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(center, radius * 0.6, radius * 0.6)

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
