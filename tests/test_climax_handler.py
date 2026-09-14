import random
import time
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QSettings

from src.BeatHandler import Segment
from src.ClimaxHandler import ClimaxHandler


@pytest.fixture
def beat_handler():
    mock = MagicMock()
    mock.is_ramp_complete.return_value = False
    return mock


@pytest.fixture
def callout_handler():
    return MagicMock()


@pytest.fixture
def handler(qtbot, beat_handler, callout_handler):
    return ClimaxHandler(beat_handler, callout_handler)


def beats(*indices, kind="beat"):
    return [Segment(kind, 20.0, 2.0, "Standard Beat", i) for i in indices]


def test_defaults_dict_matches_init_defaults(handler):
    for var_name, default_value in ClimaxHandler.DEFAULTS.items():
        assert getattr(handler, var_name) == default_value


def test_settings_override_defaults(qtbot, beat_handler, callout_handler, tmp_path):
    ini = tmp_path / "settings.ini"
    settings = QSettings(str(ini), QSettings.Format.IniFormat)
    settings.setValue("ClimaxHandler/climax_active", False)
    settings.setValue("ClimaxHandler/min_climax_delay", 60.0)
    settings.setValue("ClimaxHandler/max_climax_delay", 90.0)
    settings.setValue("ClimaxHandler/ruined_orgasm_active", True)
    settings.setValue("ClimaxHandler/ruined_orgasm_chance", 0.35)
    settings.setValue("ClimaxHandler/denied_orgasm_active", True)
    settings.setValue("ClimaxHandler/denied_orgasm_chance", 0.45)
    settings.setValue("ClimaxHandler/fake_climax_active", False)
    settings.setValue("ClimaxHandler/fake_climax_chance", 0.25)
    settings.setValue("ClimaxHandler/min_fake_climax_delay", 1.5)
    settings.setValue("ClimaxHandler/max_fake_climax_delay", 9.5)

    handler = ClimaxHandler(beat_handler, callout_handler, settings=settings)

    assert handler.climax_active is False
    assert handler.min_climax_delay == 60.0
    assert handler.max_climax_delay == 90.0
    assert handler.ruined_orgasm_active is True
    assert handler.ruined_orgasm_chance == 0.35
    assert handler.denied_orgasm_active is True
    assert handler.denied_orgasm_chance == 0.45
    assert handler.fake_climax_active is False
    assert handler.fake_climax_chance == 0.25
    assert handler.min_fake_climax_delay == 1.5
    assert handler.max_fake_climax_delay == 9.5


# --- planning the climax ---


def test_the_climax_is_placed_the_configured_delay_after_the_ramp(handler, beat_handler):
    handler.climax_active = True
    handler.min_climax_delay = handler.max_climax_delay = 100.0

    handler.on_session_planned(5000.0)

    assert handler.finale_at == 5100.0
    beat_handler.set_finale_at.assert_called_once_with(5100.0)


def test_the_delay_is_drawn_from_the_configured_range(handler):
    handler.climax_active = True
    handler.min_climax_delay, handler.max_climax_delay = 60.0, 300.0
    handler.on_session_planned(5000.0)
    assert 5060.0 <= handler.finale_at <= 5300.0


def test_no_climax_is_planned_when_it_is_switched_off(handler, beat_handler):
    handler.climax_active = False
    handler.on_session_planned(5000.0)
    assert handler.finale_at is None
    beat_handler.set_finale_at.assert_called_once_with(None)


def test_the_outcome_is_decided_up_front_not_at_the_moment_it_fires(handler):
    """The planner needs to know what it is building towards - a denial and a real
    orgasm are not the same run-in."""
    handler.climax_active = True
    handler.denied_orgasm_active = True
    handler.denied_orgasm_chance = 1.0

    handler.on_session_planned(5000.0)

    assert handler.outcome == "denied"


# --- firing the climax ---


def test_the_climax_fires_when_its_moment_arrives(handler, callout_handler):
    handler.climax_active = True
    handler.on_session_planned(time.time() + 100)

    handler._on_climax_due()

    callout_handler.force_output_sentence.assert_called_once_with("climax_real")
    assert handler.climax_triggered is True


def test_the_climax_fires_by_itself_via_the_real_timer(handler, callout_handler, qtbot):
    handler.climax_active = True
    handler.min_climax_delay = handler.max_climax_delay = 0.05

    handler.on_session_planned(time.time())

    qtbot.waitUntil(lambda: handler.climax_triggered, timeout=2000)
    callout_handler.force_output_sentence.assert_called_once_with("climax_real")


def test_the_climax_only_fires_once(handler, callout_handler):
    handler.climax_active = True
    handler.on_session_planned(time.time() + 100)

    handler._on_climax_due()
    handler._on_climax_due()

    assert callout_handler.force_output_sentence.call_count == 1


def test_the_climax_emits_its_outcome(handler, qtbot):
    handler.climax_active = True
    handler.on_session_planned(time.time() + 100)

    with qtbot.waitSignal(handler.outcome_decided_event, timeout=1000) as blocker:
        handler._on_climax_due()

    assert blocker.args == ["real"]


@pytest.mark.parametrize(
    "flag, chance, status",
    [
        ("ruined_orgasm", 1.0, "ruined"),
        ("denied_orgasm", 1.0, "denied"),
    ],
)
def test_the_climax_emits_the_status_for_its_outcome(handler, qtbot, flag, chance, status):
    handler.climax_active = True
    setattr(handler, f"{flag}_active", True)
    setattr(handler, f"{flag}_chance", chance)
    handler.on_session_planned(time.time() + 100)

    with qtbot.waitSignal(handler.status_changed_event, timeout=1000) as blocker:
        handler._on_climax_due()

    assert blocker.args == [status]


def test_a_real_outcome_emits_the_cum_status(handler, qtbot):
    handler.climax_active = True
    handler.on_session_planned(time.time() + 100)

    with qtbot.waitSignal(handler.status_changed_event, timeout=1000) as blocker:
        handler._on_climax_due()

    assert blocker.args == ["cum"]


# --- fake climaxes ---


def test_fakes_are_planned_onto_newly_planned_boundaries(handler):
    handler.fake_climax_active = True
    handler.fake_climax_chance = 1.0

    handler.on_plan_extended(beats(3, 4, 5))

    assert handler.planned_fake_boundaries == {3, 4, 5}


def test_no_fakes_are_planned_when_they_are_switched_off(handler):
    handler.fake_climax_active = False
    handler.fake_climax_chance = 1.0
    handler.on_plan_extended(beats(3, 4, 5))
    assert handler.planned_fake_boundaries == set()


def test_the_finale_is_never_planned_as_a_fake(handler):
    """Faking the climax at the exact moment the real one is due would be indistinguishable
    from a bug, and the reveal would land on top of the real announcement."""
    handler.fake_climax_active = True
    handler.fake_climax_chance = 1.0

    handler.on_plan_extended(beats(3) + beats(4, kind="finale") + beats(5))

    assert handler.planned_fake_boundaries == {3, 5}


def test_a_planned_fake_fires_when_its_segment_starts(handler, callout_handler):
    handler.fake_climax_active = True
    handler.fake_climax_chance = 1.0
    handler.on_plan_extended(beats(7))

    handler.on_segment_started(7)

    callout_handler.force_output_sentence.assert_called_once_with("climax_real")
    assert handler._fake_climax_pending is True


def test_a_segment_with_no_planned_fake_does_nothing(handler, callout_handler):
    handler.on_plan_extended(beats(7))
    handler.on_segment_started(7)
    callout_handler.force_output_sentence.assert_not_called()


def test_a_fake_fires_only_once_for_its_boundary(handler, callout_handler):
    handler.fake_climax_active = True
    handler.fake_climax_chance = 1.0
    handler.on_plan_extended(beats(7))

    handler.on_segment_started(7)
    handler._reveal_fake_climax()
    callout_handler.force_output_sentence.reset_mock()
    handler.on_segment_started(7)

    callout_handler.force_output_sentence.assert_not_called()


def test_a_fake_does_not_fire_once_the_real_climax_has_happened(handler, callout_handler):
    handler.climax_active = True
    handler.fake_climax_active = True
    handler.fake_climax_chance = 1.0
    handler.on_session_planned(time.time() + 100)
    handler.on_plan_extended(beats(7))
    handler._on_climax_due()
    callout_handler.force_output_sentence.reset_mock()

    handler.on_segment_started(7)

    callout_handler.force_output_sentence.assert_not_called()


def test_the_real_climax_cancels_a_pending_fake_reveal(handler, callout_handler, qtbot):
    """Otherwise the fake's "only joking" would land seconds after the real announcement."""
    handler.climax_active = True
    handler.fake_climax_active = True
    handler.fake_climax_chance = 1.0
    handler.min_fake_climax_delay = handler.max_fake_climax_delay = 0.05
    handler.on_session_planned(time.time() + 100)
    handler.on_plan_extended(beats(7))
    handler.on_segment_started(7)

    handler._on_climax_due()
    qtbot.wait(300)

    assert handler._fake_climax_pending is False
    assert callout_handler.force_output_sentence.call_args_list[-1].args == ("climax_real",)


def test_fake_climax_triggered_event_is_emitted(handler, qtbot):
    handler.fake_climax_active = True
    handler.fake_climax_chance = 1.0
    handler.on_plan_extended(beats(7))

    with qtbot.waitSignal(handler.fake_climax_triggered_event, timeout=1000):
        handler.on_segment_started(7)


def test_the_real_climax_does_not_emit_the_fake_event(handler):
    handler.climax_active = True
    handler.on_session_planned(time.time() + 100)
    received = []
    handler.fake_climax_triggered_event.connect(lambda: received.append(True))

    handler._on_climax_due()

    assert received == []


def test_a_fake_prompt_emits_the_cum_status(handler, qtbot):
    handler.fake_climax_active = True
    handler.fake_climax_chance = 1.0
    handler.on_plan_extended(beats(7))

    with qtbot.waitSignal(handler.status_changed_event, timeout=1000) as blocker:
        handler.on_segment_started(7)

    assert blocker.args == ["cum"]


def test_fake_climax_reveal_fires_and_resets_pending(handler, callout_handler):
    handler._fake_climax_pending = True

    handler._reveal_fake_climax()

    callout_handler.force_output_sentence.assert_called_once_with("fake_climax_reveal")
    assert handler._fake_climax_pending is False


def test_fake_climax_reveal_emits_neutral_status(handler, callout_handler, qtbot):
    handler._fake_climax_pending = True

    with qtbot.waitSignal(handler.status_changed_event, timeout=1000) as blocker:
        handler._reveal_fake_climax()

    assert blocker.args == ["neutral"]


def test_fake_climax_reveal_fires_via_real_timer(handler, callout_handler, qtbot):
    handler.fake_climax_active = True
    handler.fake_climax_chance = 1.0
    handler.min_fake_climax_delay = handler.max_fake_climax_delay = 0.05
    handler.on_plan_extended(beats(7))

    handler.on_segment_started(7)
    callout_handler.force_output_sentence.assert_called_once_with("climax_real")

    qtbot.waitUntil(lambda: not handler._fake_climax_pending, timeout=2000)

    assert callout_handler.force_output_sentence.call_args_list[-1].args == ("fake_climax_reveal",)


# --- mid-session settings changes ---


def test_a_settings_save_keeps_the_climax_where_it_was(handler):
    """Re-drawing it would make "open Settings and save" a lever for a different climax."""
    handler.climax_active = True
    handler.min_climax_delay = handler.max_climax_delay = 100.0
    handler.on_session_planned(5000.0)

    handler.min_climax_delay = handler.max_climax_delay = 5.0
    handler.settings_changed()

    assert handler.finale_at == 5100.0


def test_a_settings_save_re_resolves_the_outcome(handler):
    """Otherwise switching denial on mid-session would quietly do nothing."""
    handler.climax_active = True
    handler.on_session_planned(time.time() + 100)
    assert handler.outcome == "real"

    handler.denied_orgasm_active = True
    handler.denied_orgasm_chance = 1.0
    handler.settings_changed()

    assert handler.outcome == "denied"


def test_switching_the_climax_off_mid_session_withdraws_it(handler, beat_handler):
    handler.climax_active = True
    handler.on_session_planned(time.time() + 100)

    handler.climax_active = False
    handler.settings_changed()

    assert handler.finale_at is None
    assert beat_handler.set_finale_at.call_args.args == (None,)


def test_switching_the_climax_on_mid_session_plans_one(handler, beat_handler):
    beat_handler.session_start_time = 4000.0
    beat_handler.ramp_target_duration = 1000.0
    handler.climax_active = False
    handler.on_session_planned(5000.0)

    handler.climax_active = True
    handler.min_climax_delay = handler.max_climax_delay = 100.0
    handler.settings_changed()

    assert handler.finale_at == 5100.0


def test_a_settings_save_after_the_climax_changes_nothing(handler):
    handler.climax_active = True
    handler.on_session_planned(time.time() + 100)
    handler._on_climax_due()
    outcome = handler.outcome

    handler.denied_orgasm_active = True
    handler.denied_orgasm_chance = 1.0
    handler.settings_changed()

    assert handler.outcome == outcome


# --- outcome resolution (unchanged behaviour) ---


def test_resolve_outcome_returns_real_without_random_call_when_no_extras_active(handler, monkeypatch):
    calls = []
    monkeypatch.setattr(random, "choices", lambda *a, **kw: calls.append((a, kw)) or ["real"])
    handler.ruined_orgasm_active = False
    handler.denied_orgasm_active = False

    assert handler._resolve_outcome() == "real"
    assert calls == []


def test_resolve_outcome_chances_always_sum_to_one(handler, monkeypatch):
    captured = {}

    def fake_choices(population, weights, k):
        captured["weights"] = weights
        return ["real"]

    monkeypatch.setattr(random, "choices", fake_choices)
    handler.ruined_orgasm_active = True
    handler.ruined_orgasm_chance = 0.3
    handler.denied_orgasm_active = True
    handler.denied_orgasm_chance = 0.2

    handler._resolve_outcome()

    assert captured["weights"] == pytest.approx([0.5, 0.3, 0.2])


def test_resolve_outcome_normalizes_when_ruined_and_denied_exceed_one(handler, monkeypatch):
    captured = {}

    def fake_choices(population, weights, k):
        captured["weights"] = weights
        return ["ruined"]

    monkeypatch.setattr(random, "choices", fake_choices)
    handler.ruined_orgasm_active = True
    handler.ruined_orgasm_chance = 0.8
    handler.denied_orgasm_active = True
    handler.denied_orgasm_chance = 0.8

    handler._resolve_outcome()

    assert sum(captured["weights"]) == pytest.approx(1.0)
    assert captured["weights"][0] == pytest.approx(0.0)


def test_resolve_outcome_ruined_only(handler, monkeypatch):
    captured = {}

    def fake_choices(population, weights, k):
        captured["weights"] = weights
        return ["ruined"]

    monkeypatch.setattr(random, "choices", fake_choices)
    handler.ruined_orgasm_active = True
    handler.ruined_orgasm_chance = 1.0
    handler.denied_orgasm_active = False

    assert handler._resolve_outcome() == "ruined"
    assert captured["weights"] == pytest.approx([0.0, 1.0, 0.0])


def test_session_started_resets_state(handler):
    handler.climax_triggered = True
    handler._fake_climax_pending = True
    handler.finale_at = 123.0

    handler.session_started()

    assert handler.climax_triggered is False
    assert handler._fake_climax_pending is False
    assert handler.finale_at is None
    assert handler.planned_fake_boundaries == set()
