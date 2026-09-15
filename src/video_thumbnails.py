"""Still frames from video files, grabbed without blocking the window.

MediaFolderPickerDialog has its own synchronous grabber, which drives a nested event loop
and freezes the picker while it works. That is tolerable for a grid built once; it is not
tolerable for a dialog being scrolled. VideoThumbnailQueue does the same job purely on
signals and timers, one clip at a time.
"""
from PyQt6.QtCore import QObject, Qt, QTimer, QUrl
from PyQt6.QtGui import QPixmap
from PyQt6.QtMultimedia import QMediaPlayer, QVideoSink

from src.applog import get_logger

log = get_logger(__name__)

# Below this average brightness a frame is treated as a black leader/fade rather than a
# usable thumbnail.
VIDEO_BLACK_FRAME_BRIGHTNESS_THRESHOLD = 20
# How long a single clip may take before it is given up on. A codec the Media Foundation
# backend cannot open produces nothing however long it is given.
GRAB_TIMEOUT_MS = 2500
# Where in the clip to seek. Never the start: leaders and fade-ins are black there.
SEEK_POSITION_RATIO = 0.35


def average_brightness(image):
    """Cheap average-brightness check on a downscaled copy - used to catch black leader
    frames/fades so a thumbnail doesn't randomly land on one."""
    sample = image.scaled(16, 16)
    total = 0
    count = 0
    for y in range(sample.height()):
        for x in range(sample.width()):
            color = sample.pixelColor(x, y)
            total += (color.red() + color.green() + color.blue()) / 3
            count += 1
    return total / count if count > 0 else 0


def is_mostly_black(image, threshold=VIDEO_BLACK_FRAME_BRIGHTNESS_THRESHOLD):
    return average_brightness(image) < threshold


class _QtVideoPlayer:
    """A QMediaPlayer+QVideoSink pair, reduced to start/stop and a frame callback.

    Wrapped so the queue can be handed a stub in tests - building a real QMediaPlayer in
    the suite hits the Windows media backend, which is exactly what conftest keeps out.
    """

    def __init__(self):
        self._player = QMediaPlayer()
        self._sink = QVideoSink()
        self._player.setVideoSink(self._sink)
        self._seeked = False

    def start(self, path, on_frame):
        def handle(frame):
            if not frame.isValid():
                return
            # Must be converted here, inside the callback: doing it even a moment later
            # reliably yields a null image. Learned the hard way in the picker.
            image = frame.toImage()
            if not image.isNull():
                self._seek_once()
                on_frame(image)

        self._sink.videoFrameChanged.connect(handle)
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()

    def _seek_once(self):
        """Jumps into the clip on the first decoded frame, once the duration is known."""
        if self._seeked:
            return
        duration = self._player.duration()
        if duration > 0:
            self._seeked = True
            self._player.setPosition(int(duration * SEEK_POSITION_RATIO))

    def stop(self):
        try:
            self._sink.videoFrameChanged.disconnect()
        except TypeError:
            pass  # nothing connected - stop() is called on cancel paths too
        self._player.stop()
        self._player.setSource(QUrl())


class VideoThumbnailQueue(QObject):
    """Grabs one still per video, in the background, one clip at a time.

    `request(path, callback)` queues a clip; the callback is handed `(path, QPixmap)` when
    a frame arrives, or `(path, None)` when the clip yields nothing before the timeout.
    Callers show a placeholder until then.

    One clip at a time on purpose: a long session opens the explorer on dozens of videos
    at once, and a decoder per cell would bury the machine for a dialog nobody has even
    scrolled yet.
    """

    def __init__(self, player_factory=_QtVideoPlayer, thumbnail_size=140, parent=None):
        super().__init__(parent)
        self._player_factory = player_factory
        self._thumbnail_size = thumbnail_size
        self._pending = []
        self._player = None
        self._current = None
        self._best_image = None
        self._best_brightness = -1
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._give_up)

    def request(self, path, callback):
        self._pending.append((str(path), callback))
        if self._current is None:
            self._start_next()

    def cancel_all(self):
        """Drops everything queued and stops the running grab - for dialog close."""
        self._pending.clear()
        self._finish_current()

    # --- internals ---

    def _start_next(self):
        if not self._pending:
            return
        self._current = self._pending.pop(0)
        self._best_image = None
        self._best_brightness = -1
        path, _callback = self._current
        self._player = self._player_factory()
        self._timeout.start(GRAB_TIMEOUT_MS)
        self._player.start(path, self._on_frame)

    def _on_frame(self, image):
        if self._current is None:
            return  # cancelled while the decoder was still running
        brightness = average_brightness(image)
        # Keep the least-black frame seen rather than the first that arrives: a later one
        # can be dark-but-less-dark without ever clearing the threshold.
        if brightness > self._best_brightness:
            self._best_image = image
            self._best_brightness = brightness
        if brightness >= VIDEO_BLACK_FRAME_BRIGHTNESS_THRESHOLD:
            self._deliver(self._best_image)

    def _give_up(self):
        """Timeout: hand over whatever was seen. Some clips really are dark throughout, and
        a dim thumbnail beats an empty cell."""
        if self._current is None:
            return
        path, _callback = self._current
        if self._best_image is None:
            log.warning("No video frame could be decoded for %s", path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
        self._deliver(self._best_image)

    def _deliver(self, image):
        path, callback = self._current
        pixmap = None
        if image is not None:
            pixmap = QPixmap.fromImage(image).scaled(
                self._thumbnail_size,
                self._thumbnail_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._finish_current()
        callback(path, pixmap)
        self._start_next()

    def _finish_current(self):
        self._timeout.stop()
        if self._player is not None:
            self._player.stop()
            self._player = None
        self._current = None
