"""The plugin's own prediction. BeatHandler contributes one neutral signal and
upcoming_beats(); everything device-shaped lives here."""
import time

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

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


class RhythmDouble(QObject):
    """Everything BeatSync is allowed to need from a rhythm - and nothing in it says
    which way a device should move."""

    note_scheduled_event = pyqtSignal()
    beat_event = pyqtSignal()
    beat_paused_event = pyqtSignal()
    beat_resumed_event = pyqtSignal()
    session_planned_event = pyqtSignal(float, object)

    def upcoming_beats(self, _horizon):
        return [(0.5, True, 1)]

    def register_beat_pause_events(self, pause, resume):
        self.beat_paused_event.connect(pause)
        self.beat_resumed_event.connect(resume)


def test_the_direction_is_the_plugins_own_and_needs_nothing_from_the_rhythm():
    """It used to be read off the Strokemeter, which announced UP/DOWN for every note -
    residue from the label that flashed on each beat, with no visible effect left by the
    time the note track replaced it. Which way a stroker travels is not something a
    rhythm engine should have to have an opinion about."""
    rhythm = RhythmDouble()
    controller = FakeController()
    sync = BeatSync(rhythm, controller)
    sync.attach()
    sync.arm()
    for _ in range(8):
        rhythm.beat_event.emit()
        rhythm.note_scheduled_event.emit()
    directions = [up for up, _deadline in controller.targets]
    assert len(directions) >= 8
    assert all(a != b for a, b in zip(directions, directions[1:], strict=False))


def test_targets_alternate_across_a_whole_session(beat, sync):
    beat.start_beat()
    for _ in range(12):
        beat.beat()
    directions = [up for up, _deadline in sync.controller.targets]
    assert len(directions) >= 12
    assert all(a != b for a, b in zip(directions, directions[1:], strict=False))


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


def _script(segments):
    from src.SessionScript import SessionScript

    return SessionScript({
        "duration_sec": sum(s["duration_sec"] for s in segments), "segments": segments,
        "custom_patterns": {}, "climax": None, "fake_climaxes": [], "media": [],
    })


def test_a_replayed_session_drives_the_device_off_its_recorded_rhythm(beat, sync):
    """A replay reads its segments instead of drawing them, so nothing about the rhythm
    is rolled. The device has to follow it exactly the same way - and at the recorded
    frequency, not whatever the settings happen to say today."""
    beat.min_beat_freq = beat.max_beat_freq = 9.0
    script = _script([
        {"kind": "beat", "pattern": "Standard Beat", "freq": 1.0, "duration_sec": 30.0},
    ])
    now = time.monotonic()
    beat.start_beat(script=script)
    assert len(sync.controller.targets) == 1
    assert 0.9 <= sync.controller.targets[0][1] - now <= 1.1


def test_a_replayed_pause_stops_the_device_and_the_rhythm_behind_it_starts_it(beat, sync):
    beat.start_beat(script=_script([
        {"kind": "pause", "pattern": None, "freq": None, "duration_sec": 2.0},
        {"kind": "beat", "pattern": "Standard Beat", "freq": 2.0, "duration_sec": 30.0},
    ]))
    assert sync.paused
    assert sync.controller.cancelled
    assert sync.controller.targets == []
    beat.beat_meter_pause_timer.stop()
    beat.cur_pause_dur = 0
    beat.pause_loop()
    assert not sync.paused
    assert len(sync.controller.targets) == 1
