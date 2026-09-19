"""The video surface, and the one thing about it that only pixels can answer.

Every other test in this suite asks Qt what it thinks: is the label visible, is it above the
video in the layout. Qt answered yes to both while users saw no callouts at all during
videos, because a native video surface paints over sibling widgets without Qt's layering
knowing. So these tests render and read the result back.

The bug was reported by AppropriateLynx (#51), along with the approach taken here.
"""
import pytest
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtMultimedia import QVideoFrame
from PyQt6.QtWidgets import QGridLayout, QLabel, QWidget

from src import theme
from src.VideoDisplay import VideoDisplay

FRAME_COLOUR = QColor("#168040")   # nothing in the theme is near this green
FRAME_SIZE = QSize(160, 120)


def push_frame(display, size=FRAME_SIZE):
    """Hands the surface a solid frame without needing a decoder or a file."""
    picture = QImage(size, QImage.Format.Format_RGB32)
    picture.fill(FRAME_COLOUR)
    display.video_item.videoSink().setVideoFrame(QVideoFrame(picture))


@pytest.fixture
def make_display(qtbot):
    """Each test gets its own, parented where that test needs it - handing one widget to a
    second parent mid-test makes qtbot tear it down twice."""

    def build(parent=None, size=(400, 300)):
        display = VideoDisplay(parent)
        if parent is None:
            qtbot.addWidget(display)
            display.resize(*size)
            # Shown, because a QAbstractScrollArea does not lay its viewport out until it
            # is - and the viewport size is what resizeEvent hands to the video item.
            display.show()
            qtbot.waitExposed(display)
        return display

    return build


def test_a_frame_is_painted_into_the_widget(make_display, qtbot):
    """The whole point: the picture goes through Qt's painting, which is what lets anything
    else be drawn on top of it. A QVideoWidget renders outside it and grabs come back blank."""
    display = make_display()
    push_frame(display)

    def frame_is_there():
        shot = display.grab().toImage()
        assert shot.pixelColor(shot.width() // 2, shot.height() // 2) == FRAME_COLOUR

    qtbot.waitUntil(frame_is_there, timeout=2000)


def test_a_label_over_the_video_is_not_covered_by_it(qtbot):
    """The reported bug, reduced to its smallest form: a label sharing the video's grid cell,
    exactly where a callout sits, has to survive being drawn over a live frame.

    Worth being precise about what this proves. Run against the old QVideoWidget it fails on
    the *picture* assertion, not the text one - a grab cannot see a native surface at all, so
    the composed image contains the label and no video. What it therefore guards is that both
    go through Qt's painting, which is the mechanism that makes layering possible; that the
    text is then on top is arithmetic. The user-visible symptom itself cannot be asserted from
    inside the process, which is exactly how it stayed hidden from this suite for so long.
    """
    host = QWidget()
    qtbot.addWidget(host)
    grid = QGridLayout(host)
    grid.setContentsMargins(0, 0, 0, 0)

    display = VideoDisplay()
    grid.addWidget(display, 0, 0)
    label = QLabel("callout")
    label.setStyleSheet(f"color: {theme.ACCENT}; font-size: 30px; font-weight: bold;")
    grid.addWidget(label, 0, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
    host.resize(400, 300)
    push_frame(display)

    accent = QColor(theme.ACCENT)

    def both_are_there():
        shot = host.grab().toImage()
        assert shot.pixelColor(shot.width() // 2, shot.height() // 4) == FRAME_COLOUR, "no picture"
        assert any(
            shot.pixelColor(x, y) == accent
            for y in range(int(shot.height() * 0.55), shot.height())
            for x in range(0, shot.width(), 2)
        ), "the callout was painted over"

    qtbot.waitUntil(both_are_there, timeout=2000)


def test_the_item_keeps_the_aspect_ratio(make_display):
    """A stretched picture would be a worse bug than the one being fixed."""
    display = make_display()

    assert display.video_item.aspectRatioMode() == Qt.AspectRatioMode.KeepAspectRatio


def test_the_picture_follows_the_widget_when_it_is_resized(make_display, qtbot):
    """Without this the picture keeps the size it had when the window opened, so going
    fullscreen leaves a small frame in the corner of a large black rectangle."""
    display = make_display()

    display.resize(640, 480)
    qtbot.wait(50)
    assert display.video_item.size().width() == pytest.approx(display.viewport().width(), abs=2)

    display.resize(900, 300)
    qtbot.wait(50)
    assert display.video_item.size().width() == pytest.approx(display.viewport().width(), abs=2)
    assert display.sceneRect().width() == pytest.approx(display.viewport().width(), abs=2)


def test_it_never_takes_keyboard_focus(make_display):
    """It sits under a callout in a window where Space is Panic. A focusable scroll view
    there would swallow the key."""
    assert make_display().focusPolicy() == Qt.FocusPolicy.NoFocus
