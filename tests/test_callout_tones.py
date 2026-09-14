"""Tone as a second axis alongside language.

res/callouts/<lang>/<tone>.json - the same {trigger_key: [phrases]} schema the flat
<lang>.json files used, just indexed by tone as well. Several tones can be active at
once; the handler then mixes them.
"""
import json
import random

import pytest
from PyQt6.QtCore import QSettings

from src.CalloutHandler import TRIGGER_KEYS, CalloutHandler


def _write_tone(base, lang, tone, phrases_per_key=1, prefix=None):
    prefix = prefix if prefix is not None else f"{lang} {tone}"
    data = {key: [f"{prefix} {key} {i}" for i in range(phrases_per_key)] for key in TRIGGER_KEYS}
    lang_dir = base / lang
    lang_dir.mkdir(exist_ok=True)
    (lang_dir / f"{tone}.json").write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def tone_dir(tmp_path):
    root = tmp_path / "callouts"
    root.mkdir()
    for lang in ("en", "de"):
        for tone in ("flirty", "shy", "degrading"):
            _write_tone(root, lang, tone)
    return root


@pytest.fixture
def handler(qapp, tone_dir):
    return CalloutHandler(callout_dir=tone_dir)


def _drain(handler, category, draws=1):
    """Collects what select_and_output_sentence would emit, without the tease timer."""
    handler.active_callout = True
    handler.talking_chance = 1.0
    seen = []
    for _ in range(draws):
        handler.is_teasing = False
        handler.tease_active_timer.stop()
        phrase = handler.pick_phrase(category)
        seen.append(phrase)
    return seen


# --- discovery ---


def test_tones_are_discovered_from_the_directory_layout(handler):
    assert set(handler.available_tones) == {"flirty", "shy", "degrading"}


def test_languages_are_still_discovered_one_level_up(handler):
    assert set(handler.available_languages) == {"en", "de"}


def test_available_tones_follow_the_declared_order_not_the_filesystem(handler):
    declared = [tone for tone in CalloutHandler.TONE_LABELS if tone in handler.available_tones]
    assert handler.available_tones == declared


def test_a_tone_nobody_declared_a_label_for_is_still_offered(qapp, tone_dir):
    _write_tone(tone_dir, "en", "bratty")

    handler = CalloutHandler(callout_dir=tone_dir)

    assert "bratty" in handler.available_tones
    assert handler.tone_label("bratty") == "Bratty"


def test_tones_for_reports_what_a_single_language_actually_ships(qapp, tone_dir):
    _write_tone(tone_dir, "en", "shouty")

    handler = CalloutHandler(callout_dir=tone_dir)

    assert "shouty" in handler.tones_for("en")
    assert "shouty" not in handler.tones_for("de")


def test_an_unreadable_tone_file_does_not_take_the_language_down(qapp, tone_dir):
    (tone_dir / "en" / "shy.json").write_text("{not json", encoding="utf-8")

    handler = CalloutHandler(callout_dir=tone_dir)

    assert "en" in handler.available_languages
    assert set(handler.tones_for("en")) == {"flirty", "degrading"}


# --- selection ---


def test_the_default_selection_is_the_default_tone_alone(handler):
    assert handler.selected_tones == CalloutHandler.DEFAULTS["selected_tones"]
    assert handler.selected_tones == [CalloutHandler.DEFAULT_TONE]


def test_only_the_selected_tone_is_drawn_from(handler):
    handler.set_tones(["shy"])

    assert _drain(handler, "session_started", draws=10) == ["en shy session_started 0"] * 10


def test_selecting_several_tones_mixes_them(handler):
    handler.set_tones(["flirty", "shy"])

    seen = set(_drain(handler, "session_started", draws=60))

    assert seen == {"en flirty session_started 0", "en shy session_started 0"}


def test_an_unticked_tone_never_speaks(handler):
    handler.set_tones(["flirty", "shy"])

    assert not any("degrading" in phrase for phrase in _drain(handler, "session_started", draws=60))


def test_every_selected_tone_gets_an_equal_voice_regardless_of_file_size(qapp, tmp_path):
    """A tone with 50 lines must not drown out one with a single line - the user ticked
    two tones and expects to hear both, not a 50:1 split."""
    root = tmp_path / "callouts"
    root.mkdir()
    _write_tone(root, "en", "flirty", phrases_per_key=1)
    _write_tone(root, "en", "shy", phrases_per_key=50)
    handler = CalloutHandler(callout_dir=root)
    handler.set_tones(["flirty", "shy"])

    random.seed(0)
    seen = _drain(handler, "session_started", draws=200)
    flirty = sum(1 for phrase in seen if phrase.startswith("en flirty"))

    assert flirty > 50  # ~100 when weighted per tone, ~4 when weighted per phrase


def test_set_tones_drops_tones_that_do_not_exist(handler):
    handler.set_tones(["shy", "nonexistent"])

    assert handler.selected_tones == ["shy"]


def test_a_selection_with_nothing_usable_falls_back_to_the_default_tone(handler):
    """Never silently promote whatever happens to be on disk - degrading is opt-in."""
    handler.set_tones(["nonexistent"])

    assert _drain(handler, "session_started", draws=10) == ["en flirty session_started 0"] * 10


def test_switching_language_keeps_the_tone_selection(handler):
    handler.set_tones(["shy"])
    handler.set_lang("de")

    assert handler.selected_tones == ["shy"]
    assert _drain(handler, "session_started", draws=5) == ["de shy session_started 0"] * 5


def test_a_tone_missing_for_the_current_language_is_skipped_not_crashed(qapp, tone_dir):
    _write_tone(tone_dir, "en", "shouty")
    handler = CalloutHandler(callout_dir=tone_dir)
    handler.set_tones(["shouty", "shy"])
    handler.set_lang("de")

    assert _drain(handler, "session_started", draws=5) == ["de shy session_started 0"] * 5


def test_force_output_sentence_mixes_the_same_way(handler, qtbot):
    handler.set_tones(["shy"])

    with qtbot.waitSignal(handler.new_tease_event, timeout=1000) as blocker:
        handler.force_output_sentence("climax_real")

    assert blocker.args == ["en shy climax_real 0"]


def test_an_empty_category_does_not_raise(handler):
    handler.callout_data["en"]["flirty"]["session_started"] = []

    assert _drain(handler, "session_started") == [None]


# --- persistence ---


def test_the_tone_selection_survives_a_restart(qapp, tone_dir, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    first = CalloutHandler(settings=settings, callout_dir=tone_dir)
    first.set_tones(["shy", "degrading"])
    settings.setValue("CalloutHandler/selected_tones", first.selected_tones)
    settings.sync()

    second = CalloutHandler(settings=settings, callout_dir=tone_dir)

    assert second.selected_tones == ["shy", "degrading"]


def test_a_single_stored_tone_comes_back_as_a_list(qapp, tone_dir, tmp_path):
    """QSettings hands a one-element string list back as a bare str - the same trap
    BeatHandler.selected_beat_patterns already has to defuse."""
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("CalloutHandler/selected_tones", ["shy"])
    settings.sync()

    handler = CalloutHandler(settings=settings, callout_dir=tone_dir)

    assert handler.selected_tones == ["shy"]
