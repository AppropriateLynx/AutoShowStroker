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


# --- caption never sits on top of the notes ---


def test_notes_sit_below_the_caption_band(widget):
    widget.set_status("New Beat! [1, 2, 2, -1, -1]", "new_beat")
    # A note's whole circle has to clear the caption band, or the text renders on top
    # of incoming notes (which is exactly what it did before this was fixed).
    assert widget._note_center_y() - widget._note_radius() >= widget._caption_height()


def test_notes_stay_inside_the_widget_when_squeezed(qtbot, handler):
    # The climax banner takes roughly half the fixed 110px footer while it's visible.
    w = BeatTrackWidget(handler)
    qtbot.addWidget(w)
    w.resize(800, 48)
    w.set_status("New Beat! [1]", "new_beat")

    assert w._note_center_y() - w._note_radius() >= w._caption_height()
    assert w._note_center_y() + w._note_radius() <= w.height()


def test_caption_band_is_zero_without_a_caption(widget):
    assert widget._caption_height() == 0


def test_notes_still_drawn_while_paused(widget):
    """The segment behind the pause is already planned, so its notes fly in across the
    last seconds of the countdown instead of appearing halfway down the track the moment
    the beat comes back."""
    widget.set_status("Pause: 7 seconds left.", "pause")
    assert widget._notes_visible() is True


def test_notes_hidden_while_idle(widget):
    widget.set_status("Strokemeter appears here.", "idle")
    assert widget._notes_visible() is False


def test_notes_visible_during_a_running_beat(widget):
    widget.set_status("New Beat! [1]", "new_beat")
    assert widget._notes_visible() is True
    widget.set_status("UP", "up")
    assert widget._notes_visible() is True


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


# --- only audible steps are drawn ---


def test_silent_steps_are_not_drawn(widget, handler):
    # Hollow "ghost" notes for the pattern's silent steps read as confusing extra beats -
    # the rests stay visible as gaps in the spacing instead.
    handler.upcoming = [(0.0, True, 1), (0.5, False, 1), (1.0, True, 2)]
    widget.set_status("New Beat! [1, -1, 2]", "new_beat")

    visible = widget._visible_notes()

    assert [seconds for seconds, _weight in visible] == [0.0, 1.0]


def test_visible_notes_are_shown_while_paused(widget, handler):
    handler.upcoming = [(2.1, True, 1)]
    widget.set_status("Pause: 3 seconds left.", "pause")
    assert widget._visible_notes() == [(2.1, 1)]


# --- beat-change transition ---


def test_no_change_transition_initially(widget):
    assert widget._change_progress() is None


def test_pulse_change_starts_the_transition(widget):
    widget.pulse_change()
    progress = widget._change_progress()
    assert progress is not None
    assert 0.0 <= progress <= 1.0


def test_pulse_change_accepts_the_beat_change_event_payload(widget):
    # beat_change_event carries (freq, pattern_name) - the slot has to tolerate them.
    widget.pulse_change(2.5, "Quick Swing")
    assert widget._change_progress() is not None


def test_change_transition_expires(widget, qtbot):
    widget.pulse_change()
    qtbot.wait(BeatTrackWidget.CHANGE_FLASH_MS + 80)
    assert widget._change_progress() is None


def test_the_notes_keep_flowing_through_a_change(handler, qtbot):
    """The notes used to fade back in over the sweep, to cover the prediction being
    re-seeded at every change. The plan already holds the next segment, so there is
    nothing to cover - the notes must stay put and fully drawn through the sweep."""
    handler.upcoming = [(0.0, True, 1), (0.6, True, 2)]
    widget = BeatTrackWidget(handler)
    qtbot.addWidget(widget)
    widget.resize(400, 80)
    before = widget._visible_notes()

    widget.pulse_change()

    assert widget._change_progress() is not None  # the sweep is running
    assert widget._visible_notes() == before


def test_painting_during_a_change_transition_does_not_raise(qtbot, handler):
    handler.upcoming = [(0.0, True, 1), (0.6, True, 2)]
    w = BeatTrackWidget(handler)
    qtbot.addWidget(w)
    w.resize(800, 110)
    w.set_status("New Beat! [1, 2]", "new_beat")
    w.pulse_change()

    w.grab()


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
    w.set_status("New Beat! [1]", "new_beat")

    w.grab()

    assert handler.horizons
    assert handler.horizons[-1] == BeatTrackWidget.LEAD_TIME_SEC


def test_painting_while_idle_does_not_query_the_handler(qtbot, handler):
    w = BeatTrackWidget(handler)
    qtbot.addWidget(w)
    w.resize(800, 110)

    w.grab()

    assert handler.horizons == []


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
