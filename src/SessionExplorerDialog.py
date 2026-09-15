from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src import media_kinds, theme
from src.utils import format_clock, load_scaled_pixmap
from src.video_thumbnails import VideoThumbnailQueue

CELL_SIZE = 120
CELL_SPACING = 6
# How far beyond the visible area thumbnails are prepared, so scrolling meets ready cells
# rather than empty ones. One screenful either side is enough at any sane scroll speed.
PRELOAD_MARGIN_PX = 600

KIND_LABELS = {"beat": "Beat", "pause": "Pause", "finale": "Finale"}
# Same colours the climax banner uses in GoonerApp, so an outcome reads the same in both.
OUTCOME_COLORS = {"cum": theme.ACCENT, "real": theme.ACCENT, "ruined": theme.RUINED, "denied": theme.DENIED}
OUTCOME_LABELS = {"real": "Climax", "ruined": "Ruined", "denied": "Denied"}


class MediaCell(QFrame):
    """One medium inside a segment card. Starts blank and is filled on demand."""

    def __init__(self, entry, on_click, parent=None):
        super().__init__(parent)
        self.path = entry["path"]
        self.carried_over = entry["carried_over"]
        self._on_click = on_click
        self._loaded = False

        self.setFixedSize(CELL_SIZE, CELL_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        carried_note = " (still on screen from the previous segment)" if self.carried_over else ""
        self.setToolTip(Path(self.path).name + carried_note)
        # Darker than the card it sits on, so an empty cell still reads as a cell - a video
        # shows this black frame until the queue comes back with a still.
        self.setStyleSheet(
            f"background-color: {theme.SURFACE_DARKEST}; border-radius: 8px;"
            + (f" border: 2px dashed {theme.DISABLED_TEXT};" if self.carried_over else "")
        )

        self.image_label = QLabel(self)
        self.image_label.setGeometry(4, 4, CELL_SIZE - 8, CELL_SIZE - 8)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet(f"color: {theme.TEXT}; font-size: 10px;")
        self.image_label.setWordWrap(True)

    def mousePressEvent(self, event):
        self._on_click(self.path)
        super().mousePressEvent(event)

    def load(self, thumbnail_source):
        """Fills the cell. Images decode here and now; a video is handed to the queue and
        the cell stays dark until the frame comes back."""
        if self._loaded:
            return
        self._loaded = True

        if media_kinds.media_kind(self.path) == "video":
            self.image_label.setText("")
            thumbnail_source.request(self.path, self._video_frame_ready)
            return

        pixmap = load_scaled_pixmap(self.path, QSize(CELL_SIZE - 8, CELL_SIZE - 8))
        self._show(pixmap)

    def _video_frame_ready(self, _path, pixmap):
        self._show(pixmap)

    def _show(self, pixmap):
        if pixmap is None or pixmap.isNull():
            self.image_label.setText(Path(self.path).name)
            return
        self.image_label.setPixmap(pixmap)


class SegmentCard(QFrame):
    """One planned segment, with whatever was on screen while it played."""

    def __init__(self, data, session_start, climax_outcome, on_media_click, parent=None):
        super().__init__(parent)
        self.data = data
        self.climax_outcome = climax_outcome
        self.media_cells = []
        self._loaded = False

        accent = OUTCOME_COLORS.get(climax_outcome, theme.ACCENT) if climax_outcome else theme.SURFACE_DARK
        self.setStyleSheet(
            f"QFrame {{ background-color: {theme.SURFACE_DARK}; border-radius: 10px;"
            f" border-left: 4px solid {accent}; }}"
        )

        layout = QVBoxLayout(self)
        self._summary = self._build_summary(data, session_start, climax_outcome)
        self.header_label = QLabel(self._summary)
        self.header_label.setStyleSheet(
            f"color: {theme.ACCENT if climax_outcome else theme.TEXT}; font-size: 13px;"
            " font-weight: bold; border: none;"
        )
        layout.addWidget(self.header_label)

        self.media_columns = 0
        self._media_grid = None
        if data["media"]:
            self._media_grid = QGridLayout()
            self._media_grid.setSpacing(CELL_SPACING)
            for entry in data["media"]:
                self.media_cells.append(MediaCell(entry, on_media_click))
            layout.addLayout(self._media_grid)
            self._reflow(1)

    @staticmethod
    def _build_summary(data, session_start, climax_outcome):
        kind = KIND_LABELS.get(data["kind"], data["kind"])
        started = format_clock(max(0, data["start"] - session_start))
        ran_for = format_clock(max(0, data["end"] - data["start"]))
        parts = [f"{started}", kind]
        if data["freq"]:
            parts.append(f"{data['freq']:.2f} Hz")
        if data["pattern"]:
            parts.append(data["pattern"])
        parts.append(f"for {ran_for}")
        if climax_outcome:
            parts.append(f"- {OUTCOME_LABELS.get(climax_outcome, climax_outcome)} landed here")
        return "  ".join(parts)

    def summary(self) -> str:
        return self._summary

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow(self._columns_that_fit())

    def _columns_that_fit(self):
        margins = self.contentsMargins()
        usable = self.width() - margins.left() - margins.right()
        return max(1, (usable + CELL_SPACING) // (CELL_SIZE + CELL_SPACING))

    def _reflow(self, columns):
        """Wraps the media into rows that fit the card's current width.

        A 45-second segment at the default slideshow speed holds dozens of media; in one
        row they run straight off the side of the card. Qt has no flow layout, so the grid
        is rebuilt whenever the column count actually changes - not on every resize event.
        """
        if self._media_grid is None or columns == self.media_columns:
            return
        self.media_columns = columns
        for index, cell in enumerate(self.media_cells):
            self._media_grid.addWidget(cell, index // columns, index % columns)
        for column in range(columns):
            self._media_grid.setColumnStretch(column, 0)
        self._media_grid.setColumnStretch(columns, 1)  # push the row left

    def load_media(self, thumbnail_source):
        if self._loaded:
            return
        self._loaded = True
        for cell in self.media_cells:
            cell.load(thumbnail_source)


class SessionExplorerDialog(QDialog):
    """Scroll back through the session that just ended.

    One card per planned segment, in order, holding the media that were on screen while it
    played. The point is finding a particular picture again, so a cell can be clicked to
    see it large and to open the folder it lives in.

    The timeline is handed in and never stored: it holds media paths, which this app keeps
    out of its data directory and out of its log.
    """

    def __init__(self, timeline, thumbnail_source=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Session Explorer")
        self.setModal(True)
        self.resize(900, 620)

        self._thumbnail_source = thumbnail_source or VideoThumbnailQueue(thumbnail_size=CELL_SIZE, parent=self)
        self.selected_path = None
        self.segment_cards = []

        session_start = timeline.get("started_at") or 0.0
        climax_at = timeline.get("climax_at")
        climax_outcome = timeline.get("climax_outcome")

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_heading(timeline, session_start))

        body = QHBoxLayout()
        body.addWidget(self._build_timeline(timeline, session_start, climax_at, climax_outcome), 3)
        body.addWidget(self._build_detail_pane(), 2)
        layout.addLayout(body)

    # --- construction ---

    def _build_heading(self, timeline, session_start):
        total = max(0, (timeline.get("ended_at") or session_start) - session_start)
        label = QLabel(f"{len(timeline['segments'])} segments over {format_clock(total)}")
        label.setStyleSheet(f"color: {theme.TEXT}; font-size: 14px; font-weight: bold;")
        return label

    def _build_timeline(self, timeline, session_start, climax_at, climax_outcome):
        container = QWidget()
        self._timeline_layout = QVBoxLayout(container)
        self._timeline_layout.setSpacing(8)

        for data in timeline["segments"]:
            covers_climax = climax_at is not None and data["start"] <= climax_at < data["end"]
            card = SegmentCard(
                data,
                session_start,
                climax_outcome if covers_climax else None,
                self.select_medium,
            )
            self.segment_cards.append(card)
            self._timeline_layout.addWidget(card)
        self._timeline_layout.addStretch()

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(container)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._load_visible_cards)
        return self.scroll_area

    def _build_detail_pane(self):
        pane = QFrame()
        pane.setStyleSheet(f"background-color: {theme.SURFACE_DARK}; border-radius: 10px;")
        layout = QVBoxLayout(pane)

        self.detail_image_label = QLabel("Pick a moment on the left.")
        self.detail_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_image_label.setMinimumHeight(260)
        self.detail_image_label.setStyleSheet(f"color: {theme.TEXT}; border: none;")
        self.detail_image_label.setWordWrap(True)

        self.detail_name_label = QLabel("")
        self.detail_name_label.setWordWrap(True)
        self.detail_name_label.setStyleSheet(f"color: {theme.TEXT}; font-size: 12px; border: none;")

        self.reveal_button = QPushButton("Show in folder")
        self.reveal_button.setEnabled(False)
        self.reveal_button.clicked.connect(self._reveal_selected)

        self.play_button = QPushButton("Open in player")
        self.play_button.clicked.connect(self._play_selected)
        self.play_button.hide()

        layout.addWidget(self.detail_image_label, 1)
        layout.addWidget(self.detail_name_label)
        layout.addWidget(self.reveal_button)
        layout.addWidget(self.play_button)
        return pane

    # --- behaviour ---

    def showEvent(self, event):
        super().showEvent(event)
        self._load_visible_cards()

    def _load_visible_cards(self, *_args):
        """Decodes only what is on screen or just off it.

        A long session holds hundreds of media; building every thumbnail when the dialog
        opens would stall it for seconds on a screen most of which is never scrolled to.
        """
        viewport = self.scroll_area.viewport()
        top = self.scroll_area.verticalScrollBar().value() - PRELOAD_MARGIN_PX
        bottom = top + viewport.height() + 2 * PRELOAD_MARGIN_PX
        for card in self.segment_cards:
            if card.y() <= bottom and card.y() + card.height() >= top:
                card.load_media(self._thumbnail_source)

    def select_medium(self, path):
        self.selected_path = path
        self.detail_name_label.setText(Path(path).name)
        self.reveal_button.setEnabled(True)

        is_video = media_kinds.media_kind(path) == "video"
        self.play_button.setVisible(is_video)
        if is_video:
            self.detail_image_label.setPixmap(QPixmap())
            self.detail_image_label.setText("Video - open it in your player to watch it.")
            return

        pixmap = load_scaled_pixmap(path, self.detail_image_label.size())
        if pixmap.isNull():
            self.detail_image_label.setPixmap(QPixmap())
            self.detail_image_label.setText("This file can no longer be read.")
        else:
            self.detail_image_label.setPixmap(pixmap)

    def _reveal_selected(self):
        if not self.selected_path:
            return
        # The containing folder rather than the file: opening the file would launch it in
        # whatever is registered for the type, which is what "Open in player" is for.
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.selected_path).parent)))

    def _play_selected(self):
        if self.selected_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.selected_path))

    def closeEvent(self, event):
        # Anything still decoding is for a dialog that is going away.
        self._thumbnail_source.cancel_all()
        super().closeEvent(event)
