"""The surface a clip is painted on.

A `QVideoWidget` renders through a native surface of its own, outside Qt's widget painting.
Anything Qt draws beside it - a callout, the record chase, the session clock - is composited
underneath that surface and simply never reaches the screen, while Qt goes on answering
`isVisible()` with True. That is why the whole overlay silently disappeared during videos and
no test noticed: every one of them asked Qt rather than looking.

A `QGraphicsVideoItem` inside a view is drawn by Qt like any other widget content, so the
layering works again - and, usefully, a `grab()` of the window now contains the picture, which
is what makes the behaviour testable at all.

The cost is real and was measured before taking it: at 2560x1440 this is about 30% of one
core against 10% for a QVideoWidget, with no dropped frames at either. Neither an OpenGL
viewport nor minimal viewport updates moved that, and parenting the label *into* the video
widget does not work - the native surface covers its own children too. This is the cheapest
arrangement that actually shows the text.

Reported and diagnosed by AppropriateLynx (#51), whose approach this is.
"""
from PyQt6.QtCore import QRectF, QSizeF, Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
from PyQt6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView


class VideoDisplay(QGraphicsView):
    """Plays into `video_item`; hand that to `QMediaPlayer.setVideoOutput()`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QBrush(QColor("black")))
        self.setInteractive(False)
        # Space is Panic in the main window, and a focusable scroll view would swallow it.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumSize(1, 1)

        self.video_item = QGraphicsVideoItem()
        self.video_item.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.scene().addItem(self.video_item)

    def resizeEvent(self, event):
        """Keeps the picture the size of the view.

        Without it the item stays at whatever size it had when the window opened, so going
        fullscreen leaves a small picture in a corner of a large black rectangle.
        """
        super().resizeEvent(event)
        size = QSizeF(self.viewport().size())
        self.setSceneRect(QRectF(0, 0, size.width(), size.height()))
        self.video_item.setSize(size)
