"""The session plan: BeatHandler decides what the next segments are before they happen.

These tests never monkeypatch random - they pin the settings ranges to a single value so
the draw has only one possible outcome, which is both stricter and easier to read.
"""
import pytest

from src.BeatHandler import BeatHandler, Segment


@pytest.fixture
def handler(qtbot):
    h = BeatHandler()
    yield h
    h.stop()


def pin(handler, *, beat_dur=20.0, freq=2.0, pause_chance=0.0, pause_dur=5, ramping=False):
    """Collapses every range to a point, so the draws have only one outcome."""
    handler.min_beat_dur = handler.max_beat_dur = beat_dur
    handler.min_beat_freq = handler.max_beat_freq = freq
    handler.min_pause_dur = handler.max_pause_dur = pause_dur
    handler.pause_chance = pause_chance
    handler.ramping_active = ramping
    handler.selected_beat_patterns = ["Standard Beat"]


def freeze(monkeypatch, now):
    monkeypatch.setattr("src.BeatHandler.time.time", lambda: now)


# --- the buffer ---


def test_start_beat_fills_the_plan_buffer(handler):
    pin(handler)
    handler.start_beat()
    assert len(handler.planned_segments) == BeatHandler.PLAN_BUFFER_SEGMENTS


def test_start_beat_puts_the_first_segment_on_the_air(handler):
    pin(handler, freq=3.0)
    handler.start_beat()
    assert handler.current_segment.kind == "beat"
    assert handler.cur_freq == 3.0
    assert handler.current_beat_pattern_name == "Standard Beat"


def test_plan_refills_as_segments_are_consumed(handler):
    pin(handler)
    handler.start_beat()
    for _ in range(4):
        handler._begin_next_segment()
    assert len(handler.planned_segments) == BeatHandler.PLAN_BUFFER_SEGMENTS


def test_segment_indices_are_monotonic(handler):
    pin(handler)
    handler.start_beat()
    seen = [handler.current_segment.index]
    for _ in range(6):
        handler._begin_next_segment()
        seen.append(handler.current_segment.index)
    assert seen == list(range(len(seen)))


def test_replan_does_not_reuse_indices(handler):
    pin(handler)
    handler.start_beat()
    before = max(s.index for s in handler.planned_segments)
    handler.replan_from_next_segment()
    assert min(s.index for s in handler.planned_segments) > before


def test_plan_extended_event_carries_the_new_segments(handler, qtbot):
    pin(handler)
    with qtbot.waitSignal(handler.plan_extended_event, timeout=1000) as blocker:
        handler.start_beat()
    added = blocker.args[0]
    assert all(isinstance(s, Segment) for s in added)
    assert len(added) == BeatHandler.PLAN_BUFFER_SEGMENTS


def test_segment_started_event_reports_the_index(handler, qtbot):
    pin(handler)
    handler.start_beat()
    with qtbot.waitSignal(handler.segment_started_event, timeout=1000) as blocker:
        handler._begin_next_segment()
    assert blocker.args == [handler.current_segment.index]


def test_session_planned_event_reports_when_the_ramp_completes(handler, qtbot, monkeypatch):
    pin(handler)
    handler.min_ramp_duration = handler.max_ramp_duration = 600.0
    freeze(monkeypatch, 1000.0)
    with qtbot.waitSignal(handler.session_planned_event, timeout=1000) as blocker:
        handler.start_beat()
    assert blocker.args == [1600.0]


def test_session_planned_event_fires_before_the_plan_is_built(handler):
    """Otherwise the run-in to the climax could already be planned by the time anyone
    gets to say where the climax is."""
    pin(handler)
    sizes = []
    handler.session_planned_event.connect(lambda _t: sizes.append(len(handler.planned_segments)))
    handler.start_beat()
    assert sizes == [0]


# --- segment contents ---


def test_beat_segment_duration_has_no_tail_beyond_the_configured_range(handler):
    handler.min_beat_dur = 10.0
    handler.max_beat_dur = 12.0
    handler.pause_chance = 0.0
    handler.selected_beat_patterns = ["Standard Beat"]
    handler.start_beat()
    durations = [handler.current_segment.duration_sec]
    for _ in range(40):
        handler._begin_next_segment()
        durations.append(handler.current_segment.duration_sec)
    assert all(10.0 <= d <= 12.0 for d in durations)


def test_pause_segments_use_the_pause_range(handler):
    pin(handler, pause_chance=1.0, pause_dur=7)
    handler.start_beat()
    pause = next(s for s in handler.planned_segments if s.kind == "pause")
    assert pause.duration_sec == 7


def test_a_session_never_opens_on_a_pause(handler):
    """start_beat() used to pick a beat outright - a session that begins by telling the
    user to take their hands off would be a new and unwelcome behaviour."""
    pin(handler, pause_chance=1.0)
    handler.start_beat()
    assert handler.current_segment.kind == "beat"


def test_a_pause_is_never_followed_by_another_pause(handler):
    pin(handler, pause_chance=1.0)
    handler.start_beat()
    kinds = [handler.current_segment.kind] + [s.kind for s in handler.planned_segments]
    assert "pause" in kinds
    assert not any(a == b == "pause" for a, b in zip(kinds, kinds[1:], strict=False))


def test_ramping_is_evaluated_at_each_segments_planned_start(handler, monkeypatch):
    """The whole point of planning ahead: the ramp becomes a curve the plan walks along,
    not a corridor sampled at whatever moment the dice happened to be thrown."""
    freeze(monkeypatch, 1000.0)
    handler.min_beat_freq, handler.max_beat_freq = 1.0, 5.0
    handler.min_beat_dur = handler.max_beat_dur = 20.0
    handler.min_ramp_duration = handler.max_ramp_duration = 400.0
    handler.ramp_window_width = 0.02  # a near-point window, so the draw is effectively fixed
    handler.ramping_active = True
    handler.pause_chance = 0.0
    handler.selected_beat_patterns = ["Standard Beat"]

    handler.start_beat()
    freqs = [handler.current_segment.freq] + [s.freq for s in handler.planned_segments]
    assert freqs == sorted(freqs)
    assert freqs[-1] > freqs[0]


# --- the finale ---


def _segment_covering(handler, moment, session_start=1000.0):
    """The planned segment spanning `moment`, or None if the plan does not reach it."""
    start = session_start
    for segment in [handler.current_segment, *handler.planned_segments]:
        end = start + segment.duration_sec
        if start <= moment < end:
            return segment
        start = end
    return None


def test_no_finale_is_planned_when_none_is_requested(handler):
    pin(handler)
    handler.start_beat()
    assert all(s.kind != "finale" for s in handler.planned_segments)


def test_the_finale_covers_the_moment_the_climax_is_announced(handler, monkeypatch):
    freeze(monkeypatch, 1000.0)
    pin(handler, beat_dur=20.0)
    handler.start_beat()
    handler.set_finale_at(1000.0 + 95.0)

    starts, finale = 1000.0, None
    for segment in [handler.current_segment, *handler.planned_segments]:
        if segment.kind == "finale":
            finale = (starts, starts + segment.duration_sec)
            break
        starts += segment.duration_sec
    assert finale is not None, "the planner never marked a run-in to the climax"
    assert finale[0] <= 1095.0 < finale[1]


def test_the_finale_runs_at_the_top_of_its_frequency_window(handler, monkeypatch):
    freeze(monkeypatch, 1000.0)
    handler.min_beat_freq, handler.max_beat_freq = 1.0, 5.0
    handler.min_beat_dur = handler.max_beat_dur = 20.0
    handler.ramping_active = False
    handler.pause_chance = 0.0
    handler.selected_beat_patterns = ["Standard Beat"]
    handler.start_beat()
    handler.set_finale_at(1000.0 + 95.0)

    finale = next(s for s in handler.planned_segments if s.kind == "finale")
    assert finale.freq == 5.0


def test_the_finale_is_never_a_pause(handler, monkeypatch):
    """Even with a pause due at every boundary, the moment the climax is announced is
    covered by a rhythm - being told to cum with your hands off would be nonsense."""
    freeze(monkeypatch, 1000.0)
    pin(handler, beat_dur=20.0, pause_chance=1.0)
    handler.start_beat()
    handler.set_finale_at(1060.0)

    covering = _segment_covering(handler, 1060.0)
    assert covering is not None
    assert covering.kind == "finale"


def test_the_finale_swallows_a_leftover_too_short_to_stand_alone(handler, monkeypatch):
    """4 x 20s lands on 80s, leaving 5s before an 85s climax - too short for a segment of
    its own, so the run-in is extended over it instead of a runt being planned."""
    freeze(monkeypatch, 1000.0)
    pin(handler, beat_dur=20.0)
    handler.start_beat()
    handler.set_finale_at(1000.0 + 85.0)

    planned = [handler.current_segment, *handler.planned_segments]
    assert all(s.duration_sec >= handler.min_beat_dur for s in planned)
    finale = next(s for s in planned if s.kind == "finale")
    assert finale.duration_sec > 20.0


def test_only_one_finale_is_planned(handler, monkeypatch):
    freeze(monkeypatch, 1000.0)
    pin(handler, beat_dur=20.0)
    handler.start_beat()
    handler.set_finale_at(1000.0 + 45.0)
    planned = [handler.current_segment, *handler.planned_segments]
    assert [s.kind for s in planned].count("finale") == 1


def test_a_late_starting_segment_that_becomes_the_finale_drops_the_stale_one(handler, monkeypatch):
    """Segments start at the first beat tick past their planned end, so they run late. When
    that drift turns an ordinary segment into the run-in, everything queued behind it was
    planned against a timeline that no longer holds - including, once, a second finale
    still sitting in the queue after the climax had already been covered."""
    freeze(monkeypatch, 1000.0)
    pin(handler, beat_dur=4.0)
    handler.min_beat_dur = handler.max_beat_dur = 4.0
    handler.start_beat()
    handler.set_finale_at(1015.0)

    freeze(monkeypatch, 1010.0)  # the next segment starts six seconds late
    handler._begin_next_segment()

    planned = [handler.current_segment, *handler.planned_segments]
    assert handler.current_segment.kind == "finale"
    assert [s.kind for s in planned].count("finale") == 1


def test_planning_continues_normally_past_the_finale(handler, monkeypatch):
    freeze(monkeypatch, 1000.0)
    pin(handler, beat_dur=20.0)
    handler.start_beat()
    handler.set_finale_at(1000.0 + 45.0)
    planned = [handler.current_segment, *handler.planned_segments]
    after = planned[[s.kind for s in planned].index("finale") + 1:]
    assert after and all(s.kind == "beat" for s in after)


# --- replanning ---


def test_replan_leaves_the_running_segment_alone(handler):
    pin(handler, beat_dur=20.0)
    handler.start_beat()
    running = handler.current_segment
    handler.min_beat_dur = handler.max_beat_dur = 40.0
    handler.replan_from_next_segment()
    assert handler.current_segment is running
    assert all(s.duration_sec == 40.0 for s in handler.planned_segments)


def test_replan_keeps_the_finale_where_it_was(handler, monkeypatch):
    freeze(monkeypatch, 1000.0)
    pin(handler, beat_dur=20.0)
    handler.start_beat()
    handler.set_finale_at(1000.0 + 95.0)
    handler.replan_from_next_segment()
    assert handler._finale_at == 1095.0
    assert any(s.kind == "finale" for s in handler.planned_segments)


def test_replan_before_a_session_starts_does_nothing(handler):
    handler.replan_from_next_segment()
    assert handler.planned_segments == ()


def test_stop_clears_the_plan(handler):
    pin(handler)
    handler.start_beat()
    handler.stop()
    assert handler.planned_segments == ()
    assert handler.current_segment is None
