"""The plugin's own prediction. BeatHandler contributes one neutral signal and
upcoming_beats(); everything device-shaped lives here."""
import time

import pytest

from src.BeatHandler import BeatHandler
from src.plugins.intiface.beat_sync import BeatSync


class FakeController:
    """Stands in for IntifaceController: records targets, nothing else."""

    def __init__(self):
        self.targets = []
        self.cancelled = 0

    def on_target(self, up, deadline):
        self.targets.append((up, deadline))

    def cancel_motion(self):
        self.cancelled += 1


@pytest.fixture
def beat(qsettings, qtbot):
    handler = BeatHandler(settings=qsettings)
    handler.ramping_active = False
    handler.min_beat_freq = handler.max_beat_freq = 2.0
    handler.min_beat_dur = handler.max_beat_dur = 30.0
    handler.pause_chance = 0
    handler.selected_beat_patterns = ["Standard Beat"]
    yield handler
    handler.stop()


@pytest.fixture
def sync(beat):
    controller = FakeController()
    sync = BeatSync(beat, controller)
    sync.attach()
    sync.arm()
    return sync


def test_the_first_target_is_sent_before_the_first_beat(beat, sync):
    now = time.monotonic()
    beat.start_beat()
    assert len(sync.controller.targets) == 1
    up, deadline = sync.controller.targets[0]
    assert 0.45 <= deadline - now <= 0.55
    assert isinstance(up, bool)


def test_one_target_per_note_however_often_the_rhythm_reschedules(beat, sync):
    beat.start_beat()
    sync.on_note_scheduled()
    sync.on_note_scheduled()
    assert len(sync.controller.targets) == 1
    beat.beat()
    assert len(sync.controller.targets) == 2


def test_targets_alternate_and_match_the_direction_the_meter_shows(beat, sync):
    shown = []
    beat.beat_meter_update_event.connect(lambda _text, kind: shown.append(kind))
    beat.start_beat()
    for _ in range(9):
        predicted = sync.controller.targets[-1][0]
        shown.clear()
        beat.beat()
        if "up" in shown or "down" in shown:
            assert predicted == ("up" in shown)
    directions = [up for up, _deadline in sync.controller.targets]
    assert all(a != b for a, b in zip(directions, directions[1:], strict=False))


def test_the_device_is_in_step_again_the_moment_a_highlight_ends(beat, sync):
    """The meter shows "New Beat!" instead of a direction for the first few notes of
    every segment, a session's opening segment included. The device keeps stroking
    through that and has to be on the right endpoint when UP/DOWN comes back - being one
    stroke out for the rest of the segment is exactly what this counts its way around."""
    shown = []
    beat.beat_meter_update_event.connect(lambda _text, kind: shown.append(kind))
    beat.start_beat()
    for _ in range(beat.NEW_BEAT_HIGHLIGHT_NOTES):
        beat.beat()
    assert "up" not in shown and "down" not in shown
    directions = [up for up, _deadline in sync.controller.targets]
    assert all(a != b for a, b in zip(directions, directions[1:], strict=False))

    predicted = sync.controller.targets[-1][0]
    shown.clear()
    beat.beat()
    assert predicted == ("up" in shown)


def test_a_rhythm_pause_cancels_whatever_the_device_is_doing(beat, sync):
    beat.start_beat()
    beat.start_pause()
    assert sync.controller.cancelled


def test_a_silent_step_extends_the_target_to_the_next_audible_note(beat, sync):
    beat.start_beat()
    beat.current_beat_pattern = [1, -1, -1, 1]
    beat.current_beat_position = 1
    beat._pattern_audible_count = 2
    beat._pattern_inv_sum = 4.0
    beat.beat_meter_timer.start(250)
    sync.controller.targets.clear()
    sync.arm()
    assert len(sync.controller.targets) == 1
    assert 0.70 <= sync.controller.targets[0][1] - time.monotonic() <= 0.76


def test_nothing_is_sent_while_the_rhythm_is_paused(beat, sync):
    beat.start_beat()
    sync.controller.targets.clear()
    beat.start_pause()
    sync.on_note_scheduled()
    assert sync.controller.targets == []


def test_nothing_is_sent_once_the_beat_has_stopped(beat, sync):
    beat.start_beat()
    beat.stop()
    sync.controller.targets.clear()
    sync.on_note_scheduled()
    assert sync.controller.targets == []


def test_nothing_is_sent_until_the_sync_is_armed(beat):
    controller = FakeController()
    sync = BeatSync(beat, controller)
    sync.attach()
    beat.start_beat()
    assert controller.targets == []
    sync.arm()
    assert len(controller.targets) == 1


def test_disarming_stops_further_targets(beat, sync):
    beat.start_beat()
    sync.disarm()
    sync.controller.targets.clear()
    beat.beat()
    assert sync.controller.targets == []


def test_arming_mid_note_re_sends_the_note_already_running(beat, sync):
    beat.start_beat()
    sync.disarm()
    sync.controller.targets.clear()
    sync.arm()
    assert len(sync.controller.targets) == 1
