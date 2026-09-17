from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src import achievements, applog, theme

log = applog.get_logger(__name__)

MARK_SIZE = 48
LOCKED_COLOR = "#6a6175"
COLUMNS = 2


def tinted_mark(path, color, size=MARK_SIZE) -> QPixmap:
    """One SVG, either state. The marks are drawn as a single stroke with no fill, so
    painting the colour straight through the alpha gives both the lit and the locked version
    from the same file - no second asset, and no chance of the two drifting apart."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(str(path))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if renderer.isValid():
        renderer.render(painter, QRectF(0, 0, size, size))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return pixmap


class AchievementCard(QFrame):
    """One achievement: its mark, its name, and either when you got it or how close you are."""

    def __init__(self, achievement, unlocked_at, progress, secret_title, parent=None):
        super().__init__(parent)
        self.achievement = achievement
        self.unlocked = unlocked_at is not None
        self.glow = None
        self.progress_bar = None

        hidden = achievement.secret and not self.unlocked

        # Scoped by object name on purpose: QLabel is a QFrame subclass, so a bare
        # "QFrame { ... }" rule here paints the mark and the text with the card's own
        # background, padding and rounded border too.
        self.setObjectName("achievementCard")
        self.setStyleSheet(
            f"#achievementCard {{ background-color: {theme.SURFACE_DARK}; "
            "border-radius: 10px; padding: 8px; }"
        )
        row = QHBoxLayout(self)

        self.mark = QLabel()
        self.mark.setFixedSize(MARK_SIZE, MARK_SIZE)
        self.mark.setPixmap(
            tinted_mark(
                achievements.icon_path(achievement),
                theme.ACCENT if self.unlocked else LOCKED_COLOR,
            )
        )
        if self.unlocked:
            # The same glow the record-chase badge and the session timer already wear, so an
            # earned mark reads as lit rather than merely coloured.
            self.glow = QGraphicsDropShadowEffect()
            self.glow.setColor(QColor(theme.ACCENT))
            self.glow.setBlurRadius(24)
            self.glow.setOffset(0, 0)
            self.mark.setGraphicsEffect(self.glow)
        row.addWidget(self.mark)

        text = QVBoxLayout()
        self.title = QLabel(secret_title if hidden else achievement.name)
        self.title.setStyleSheet(
            f"color: {theme.ACCENT if self.unlocked else theme.TEXT}; font-weight: bold; "
            "font-size: 14px;"
        )
        text.addWidget(self.title)

        self.detail = QLabel(self._detail_for(achievement, unlocked_at, hidden))
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet(f"color: {theme.TEXT}; font-size: 12px;")
        text.addWidget(self.detail)

        if not self.unlocked and not hidden and progress is not None:
            current, target = progress
            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, int(target))
            self.progress_bar.setValue(int(current))
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setFixedHeight(6)
            # Qt's default chunk is a flat green that belongs to another application.
            self.progress_bar.setStyleSheet(
                f"QProgressBar {{ background-color: {theme.SURFACE_DARKEST}; "
                "border: none; border-radius: 3px; }"
                f"QProgressBar::chunk {{ background-color: {theme.ACCENT}; "
                "border-radius: 3px; }"
            )
            text.addWidget(self.progress_bar)

        row.addLayout(text, 1)

    @staticmethod
    def _detail_for(achievement, unlocked_at, hidden) -> str:
        if unlocked_at is not None:
            return f"Earned {unlocked_at}"
        if hidden:
            return "Not everything announces itself in advance."
        return achievement.description

    # Read by tests and by nothing else - the widgets themselves are the interface.
    def title_text(self) -> str:
        return self.title.text()

    def detail_text(self) -> str:
        return self.detail.text()


class AchievementsDialog(QDialog):
    """Everything there is to earn, earned or not.

    The point of showing the locked ones at all: until now an achievement could only be
    seen by getting it, which makes them discoveries rather than goals. Progress is read
    against the most recent session, because a per-session rule has to be measured against
    a session and the last one played is the only honest choice.
    """

    SECRET_TITLE = "???"

    def __init__(self, tracker, history, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Achievements")
        self.setModal(True)
        self.resize(820, 600)

        self.tracker = tracker
        self.cards = []

        layout = QVBoxLayout(self)

        title = QLabel("Achievements")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {theme.ACCENT};")
        layout.addWidget(title)

        earned = sum(1 for item in tracker.catalogue if tracker.is_unlocked(item.id))
        self.summary_label = QLabel(f"{earned} of {len(tracker.catalogue)} earned")
        self.summary_label.setStyleSheet(f"color: {theme.TEXT};")
        layout.addWidget(self.summary_label)

        layout.addWidget(self._build_grid(history), 1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("primary")
        self.close_button.clicked.connect(self.accept)
        close_row.addWidget(self.close_button)
        layout.addLayout(close_row)

    def _build_grid(self, history):
        latest = history[-1] if history else {}
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)

        for index, achievement in enumerate(self.tracker.catalogue):
            card = AchievementCard(
                achievement,
                self.tracker.unlocked_at(achievement.id),
                self.tracker.progress_for(achievement, latest, list(history)),
                self.SECRET_TITLE,
            )
            self.cards.append(card)
            grid.addWidget(card, index // COLUMNS, index % COLUMNS)
        grid.setRowStretch(grid.rowCount(), 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        return scroll

    def card_for(self, achievement_id):
        return next(
            (card for card in self.cards if card.achievement.id == achievement_id), None
        )
