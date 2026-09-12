import pytest

from src.BeatTrackWidget import BeatTrackWidget


class _StubBeatHandler:
    """The widget only ever asks the handler for upcoming notes - nothing else."""

    def __init__(self, upcoming=None):
        self.upcoming = upcoming or []
        self.horizons = []

    def upcoming_beats(self, horizon_sec):
        self.horizons.append(horizon_sec)
        return self.upcoming


@pytest.fixture
def handler():
    return _StubBeatHandler()


@pytest.fixture
def widget(qtbot, handler):
    w = BeatTrackWidget(handler)
    qtbot.addWidget(w)
    w.resize(800, 110)
    return w


# --- note geometry ---


def test_note_landing_now_sits_on_the_hit_zone(widget):
    assert widget._note_x(0.0) == pytest.approx(widget._hit_zone_x())


def test_note_at_full_lead_time_sits_at_the_right_edge(widget):
    assert widget._note_x(BeatTrackWidget.LEAD_TIME_SEC) == pytest.approx(widget.width())


def test_notes_further_out_are_further_right(widget):
    assert widget._note_x(0.5) < widget._note_x(1.5)


def test_hit_zone_is_near_the_left_edge(widget):
    assert 0 < widget._hit_zone_x() < widget.width() / 2


# --- status caption ---


def test_starts_with_no_caption(widget):
    assert widget._caption == ""


def test_set_status_stores_caption_and_kind(widget):
    widget.set_status("New Beat! [1, 2]", "new_beat")
    assert widget._caption == "New Beat! [1, 2]"
    assert widget._kind == "new_beat"


def test_blink_kinds_update_kind_but_never_overwrite_the_caption(widget):
    # "UP"/"DOWN" is redundant once notes visibly land on the hit zone - the meaningful
    # caption (pattern / pause countdown) has to survive the blink updates.
    widget.set_status("New Beat! [1, 2]", "new_beat")

    widget.set_status("UP", "up")
    assert widget._caption == "New Beat! [1, 2]"
    widget.set_status("DOWN", "down")
    assert widget._caption == "New Beat! [1, 2]"


def test_pause_status_replaces_the_caption(widget):
    widget.set_status("New Beat! [1]", "new_beat")
    widget.set_status("Pause: 7 seconds left.", "pause")
    assert widget._caption == "Pause: 7 seconds left."
    assert widget._kind == "pause"


def test_idle_status_replaces_the_caption(widget):
    widget.set_status("New Beat! [1]", "new_beat")
    widget.set_status("Strokemeter appears here.", "idle")
    assert widget._caption == "Strokemeter appears here."


def test_unknown_kind_does_not_raise(widget):
    widget.set_status("something", "not_a_real_kind")
    assert widget._kind == "not_a_real_kind"


# --- hit flash ---


def test_not_flashing_initially(widget):
    assert widget.is_flashing() is False


def test_flash_marks_the_widget_as_flashing(widget):
    widget.flash()
    assert widget.is_flashing() is True


def test_flash_expires(widget, qtbot):
    widget.flash()
    qtbot.wait(BeatTrackWidget.FLASH_MS + 60)
    assert widget.is_flashing() is False


# --- frame timer lifecycle ---


def test_frame_timer_not_running_before_session_starts(widget):
    assert widget.frame_timer.isActive() is False


def test_start_runs_the_frame_timer(widget):
    widget.start()
    assert widget.frame_timer.isActive() is True
    assert widget.frame_timer.interval() == BeatTrackWidget.FRAME_INTERVAL_MS


def test_stop_halts_the_frame_timer(widget):
    widget.start()
    widget.stop()
    assert widget.frame_timer.isActive() is False


# --- painting ---


def test_painting_an_empty_track_does_not_raise(widget):
    widget.grab()


def test_painting_notes_does_not_raise(qtbot, handler):
    handler.upcoming = [(0.0, True, 1), (0.4, False, 2), (1.1, True, 1), (2.4, True, 4)]
    w = BeatTrackWidget(handler)
    qtbot.addWidget(w)
    w.resize(800, 110)
    w.set_status("New Beat! [1, -2, 1, 4]", "new_beat")
    w.flash()

    w.grab()


def test_painting_asks_the_handler_for_its_lead_time_window(qtbot, handler):
    w = BeatTrackWidget(handler)
    qtbot.addWidget(w)
    w.resize(800, 110)

    w.grab()

    assert handler.horizons
    assert handler.horizons[-1] == BeatTrackWidget.LEAD_TIME_SEC


def test_painting_survives_a_squeezed_footer(qtbot, handler):
    # The climax banner takes about half the fixed 110px footer while it's visible.
    handler.upcoming = [(0.0, True, 1), (1.0, True, 1)]
    w = BeatTrackWidget(handler)
    qtbot.addWidget(w)
    w.resize(800, 48)

    w.grab()


def test_painting_a_paused_track_does_not_raise(qtbot, handler):
    w = BeatTrackWidget(handler)
    qtbot.addWidget(w)
    w.resize(800, 110)
    w.set_status("Pause: 4 seconds left.", "pause")

    w.grab()
