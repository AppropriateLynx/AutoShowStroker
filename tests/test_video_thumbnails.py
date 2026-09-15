"""The async video-thumbnail queue behind the Session Explorer.

Never builds a real QMediaPlayer - the queue takes a player factory so these tests hand it
a stub, same rule as load_media's video branch in conftest.
"""
import pytest
from PyQt6.QtGui import QColor, QImage

from src.video_thumbnails import VideoThumbnailQueue, average_brightness, is_mostly_black


def _solid_image(rgb, size=8):
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor(rgb))
    return image


# --- brightness helpers (moved out of MediaFolderPickerDialog) ---


def test_is_mostly_black_detects_a_black_frame():
    assert is_mostly_black(_solid_image(0x000000)) is True


def test_is_mostly_black_rejects_a_bright_frame():
    assert is_mostly_black(_solid_image(0xFF00BF)) is False


def test_is_mostly_black_respects_a_custom_threshold():
    dark_gray = _solid_image(0x0F0F0F)
    assert is_mostly_black(dark_gray, threshold=10) is False
    assert is_mostly_black(dark_gray, threshold=20) is True


def test_average_brightness_orders_dark_to_bright():
    black, dark, bright = _solid_image(0x000000), _solid_image(0x0F0F0F), _solid_image(0xFFFFFF)
    assert average_brightness(black) < average_brightness(dark) < average_brightness(bright)


# --- the queue ---


class _StubPlayer:
    """Stands in for the QMediaPlayer+QVideoSink pair, driven by the test."""

    instances = []

    def __init__(self):
        self.path = None
        self.stopped = False
        self.on_frame = None
        _StubPlayer.instances.append(self)

    def start(self, path, on_frame):
        self.path = path
        self.on_frame = on_frame

    def stop(self):
        self.stopped = True

    def deliver(self, image):
        self.on_frame(image)


@pytest.fixture
def stub_player():
    _StubPlayer.instances = []
    return _StubPlayer


@pytest.fixture
def queue(qtbot, stub_player):
    q = VideoThumbnailQueue(player_factory=stub_player)
    yield q
    q.cancel_all()


def _results():
    got = []
    return got, lambda path, pixmap: got.append((path, pixmap))


def test_a_request_starts_a_grab(queue, stub_player):
    _got, sink = _results()
    queue.request("clip.mp4", sink)
    assert stub_player.instances[0].path == "clip.mp4"


def test_only_one_video_is_decoded_at_a_time(queue, stub_player):
    """A player per pending video would have a long session opening dozens of decoders at
    once the moment the explorer is scrolled."""
    _got, sink = _results()
    queue.request("a.mp4", sink)
    queue.request("b.mp4", sink)

    assert len(stub_player.instances) == 1


def test_the_next_video_starts_once_the_first_delivers(queue, stub_player):
    _got, sink = _results()
    queue.request("a.mp4", sink)
    queue.request("b.mp4", sink)

    stub_player.instances[0].deliver(_solid_image(0xFFFFFF))

    assert len(stub_player.instances) == 2
    assert stub_player.instances[1].path == "b.mp4"


def test_a_delivered_frame_reaches_the_caller(queue, stub_player):
    got, sink = _results()
    queue.request("a.mp4", sink)

    stub_player.instances[0].deliver(_solid_image(0xFF00BF))

    assert got[0][0] == "a.mp4"
    assert not got[0][1].isNull()


def test_the_player_is_stopped_once_it_has_delivered(queue, stub_player):
    _got, sink = _results()
    queue.request("a.mp4", sink)
    stub_player.instances[0].deliver(_solid_image(0xFFFFFF))
    assert stub_player.instances[0].stopped is True


def test_a_black_frame_does_not_settle_the_grab(queue, stub_player):
    """Black leader frames and fades are why the picker retries rather than taking the
    first frame that arrives."""
    got, sink = _results()
    queue.request("a.mp4", sink)

    stub_player.instances[0].deliver(_solid_image(0x000000))

    assert got == []


def test_a_bright_frame_after_a_black_one_wins(queue, stub_player):
    got, sink = _results()
    queue.request("a.mp4", sink)

    stub_player.instances[0].deliver(_solid_image(0x000000))
    stub_player.instances[0].deliver(_solid_image(0xFFFFFF))

    assert len(got) == 1
    assert not got[0][1].isNull()


def test_giving_up_reports_the_best_frame_seen(queue, stub_player):
    """Some clips really are dark throughout - a dim thumbnail beats none."""
    got, sink = _results()
    queue.request("a.mp4", sink)
    stub_player.instances[0].deliver(_solid_image(0x0A0A0A))

    queue._give_up()

    assert len(got) == 1
    assert not got[0][1].isNull()


def test_giving_up_with_nothing_at_all_reports_no_pixmap(queue, stub_player):
    got, sink = _results()
    queue.request("a.mp4", sink)

    queue._give_up()

    assert got == [("a.mp4", None)]


def test_giving_up_moves_on_to_the_next_video(queue, stub_player):
    _got, sink = _results()
    queue.request("a.mp4", sink)
    queue.request("b.mp4", sink)

    queue._give_up()

    assert stub_player.instances[1].path == "b.mp4"


def test_cancel_all_drops_pending_work(queue, stub_player):
    got, sink = _results()
    queue.request("a.mp4", sink)
    queue.request("b.mp4", sink)

    queue.cancel_all()
    stub_player.instances[0].deliver(_solid_image(0xFFFFFF))

    assert got == []
    assert len(stub_player.instances) == 1


def test_cancel_all_stops_the_running_player(queue, stub_player):
    _got, sink = _results()
    queue.request("a.mp4", sink)

    queue.cancel_all()

    assert stub_player.instances[0].stopped is True
