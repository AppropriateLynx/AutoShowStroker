"""The global QSS sets colours explicitly, which silently defeats Qt's own disabled
palette: a rule like `QCheckBox { color: TEXT; }` applies to the disabled state too, so
setEnabled(False) changes nothing a user can see. Every control that can be disabled
therefore needs its own :disabled rule here."""
import re

from src import theme


def _rule(selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(.*?)\}}", theme.GLOBAL_QSS, re.DOTALL)
    assert match, f"No {selector} rule in GLOBAL_QSS"
    return match.group(1)


def test_a_disabled_checkbox_dims_its_label():
    assert theme.DISABLED_TEXT in _rule("QCheckBox:disabled")


def test_a_disabled_checkbox_dims_its_box():
    assert theme.DISABLED_BG in _rule("QCheckBox::indicator:disabled")


def test_a_disabled_checkbox_that_is_ticked_still_reads_as_ticked_but_dim():
    """A tone can be selected and unavailable at once - the tick has to stay visible,
    just muted, or the user sees their selection vanish."""
    rule = _rule("QCheckBox::indicator:checked:disabled")
    assert theme.ACCENT not in rule
    assert rule.strip()
