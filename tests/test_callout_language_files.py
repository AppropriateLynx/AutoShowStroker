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


def test_every_language_ships_every_tone():
    """Tone is picked once and survives a language switch, so a language missing a tone
    would silently drop it from the mix the moment the user changes language."""
    per_language = {path.name: sorted(child.stem for child in path.glob("*.json")) for path in LANGUAGE_DIRS}
    expected = sorted(set().union(*per_language.values()))
    mismatched = {lang: tones for lang, tones in per_language.items() if tones != expected}
    assert not mismatched, f"Expected every language to ship {expected}, but: {mismatched}"


def test_every_shipped_tone_has_a_declared_label():
    """Not required by the code (unlabelled tones get a title-cased name), but the shipped
    set is curated - a stray file here means a typo'd tone name."""
    shipped = {path.stem for path in TONE_FILES}
    assert shipped == set(CalloutHandler.TONE_LABELS)


def test_the_default_tone_is_actually_shipped():
    assert CalloutHandler.DEFAULT_TONE in {path.stem for path in TONE_FILES}
