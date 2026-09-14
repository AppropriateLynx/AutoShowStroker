"""Schema check for the shipped phrase files: res/callouts/<lang>/<tone>.json.

A missing or typo'd trigger key doesn't raise - the app just goes quiet for that event,
which is nearly impossible to notice by playing alone. This is what a contributor adding
a language or a tone runs first (see CONTRIBUTING.md).
"""
import json

import pytest

from src.CalloutHandler import TRIGGER_KEYS, CalloutHandler
from src.utils import get_project_root

CALLOUT_DIR = get_project_root() / "res" / "callouts"
LANGUAGE_DIRS = sorted(path for path in CALLOUT_DIR.iterdir() if path.is_dir())
TONE_FILES = sorted(CALLOUT_DIR.glob("*/*.json"))


def _file_id(path):
    return f"{path.parent.name}/{path.stem}"


def test_at_least_one_language_exists():
    assert LANGUAGE_DIRS, f"No language folders found in {CALLOUT_DIR}"


def test_no_phrase_file_sits_outside_a_language_folder():
    """A leftover res/callouts/en.json from the pre-tone layout would simply be ignored."""
    stray = sorted(path.name for path in CALLOUT_DIR.glob("*.json"))
    assert not stray, f"Phrase files must live in res/callouts/<lang>/<tone>.json, found: {stray}"


@pytest.mark.parametrize("path", TONE_FILES, ids=_file_id)
def test_phrase_file_is_valid_json(path):
    json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", TONE_FILES, ids=_file_id)
def test_phrase_file_has_all_required_keys(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = set(TRIGGER_KEYS) - set(data.keys())
    assert not missing, f"{_file_id(path)} is missing required trigger keys: {sorted(missing)}"


@pytest.mark.parametrize("path", TONE_FILES, ids=_file_id)
def test_phrase_file_has_no_unknown_keys(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    unknown = set(data.keys()) - set(TRIGGER_KEYS)
    assert not unknown, f"{_file_id(path)} has unknown trigger keys (typo?): {sorted(unknown)}"


@pytest.mark.parametrize("path", TONE_FILES, ids=_file_id)
def test_phrase_file_values_are_lists_of_strings(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, phrases in data.items():
        assert isinstance(phrases, list), f"{_file_id(path)}:{key} must be a list, got {type(phrases).__name__}"
        for i, phrase in enumerate(phrases):
            assert isinstance(phrase, str), f"{_file_id(path)}:{key}[{i}] must be a string, got {type(phrase).__name__}"


@pytest.mark.parametrize("path", TONE_FILES, ids=_file_id)
def test_phrase_file_has_no_empty_category(path):
    """An empty array is worse than a missing tone: the tone is offered, ticked, and then
    contributes nothing for that event while the user assumes it does."""
    data = json.loads(path.read_text(encoding="utf-8"))
    empty = sorted(key for key, phrases in data.items() if not phrases)
    assert not empty, f"{_file_id(path)} has empty phrase lists for: {empty}"


@pytest.mark.parametrize("path", TONE_FILES, ids=_file_id)
def test_phrase_file_has_no_duplicate_phrases(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, phrases in data.items():
        duplicates = sorted({phrase for phrase in phrases if phrases.count(phrase) > 1})
        assert not duplicates, f"{_file_id(path)}:{key} repeats: {duplicates}"


def test_every_language_ships_the_default_tone():
    """A language may ship a subset of the tones - a contributor adding one tone in one
    language should not have to write two more languages first, and CalloutHandler skips
    what the current language lacks. The default tone is the exception: it is what an
    otherwise unusable selection falls back to, so a language without it has nothing to
    fall back on."""
    missing = [path.name for path in LANGUAGE_DIRS if not (path / f"{CalloutHandler.DEFAULT_TONE}.json").exists()]
    assert not missing, f"These languages are missing the default tone {CalloutHandler.DEFAULT_TONE!r}: {missing}"


def test_every_shipped_tone_has_a_declared_label():
    """Not required by the code (unlabelled tones get a title-cased name), but the shipped
    set is curated - a stray file here means a typo'd tone name."""
    shipped = {path.stem for path in TONE_FILES}
    assert shipped == set(CalloutHandler.TONE_LABELS)


def test_the_default_tone_is_actually_shipped():
    assert CalloutHandler.DEFAULT_TONE in {path.stem for path in TONE_FILES}


def test_no_phrase_is_shared_between_two_tones_of_a_language():
    """Tones are mixed by drawing a tone and then a line from it, so a line copied into two
    tones is heard about twice as often as its neighbours - and blurs the two tones it sits
    in, which is the whole thing the axis exists to keep apart."""
    for lang_dir in LANGUAGE_DIRS:
        owners = {}
        for path in sorted(lang_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for key, phrases in data.items():
                for phrase in phrases:
                    owners.setdefault((key, phrase), []).append(path.stem)
        shared = {ks: tones for ks, tones in owners.items() if len(tones) > 1}
        assert not shared, f"{lang_dir.name}: phrases appear in several tones: {sorted(shared)[:5]}"
