"""Keeps the frozen-build check honest without needing a frozen build.

The check itself can only run against a real `.exe`, which the suite has none of. What can
be tested here is the half that rots: its list of what to look for. A plugin module added
today and forgotten here would sail through every release, because the whole point of that
list is the modules PyInstaller cannot find by itself.
"""
from pathlib import Path

import pytest

from scripts.verify_frozen import BUNDLED_TREES, REQUIRED_MODULES

ROOT = Path(__file__).resolve().parent.parent


def _plugin_modules_on_disk():
    modules = set()
    for path in (ROOT / "src" / "plugins").glob("**/*.py"):
        relative = path.relative_to(ROOT).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        modules.add(".".join(parts))
    return modules


def test_every_plugin_module_is_checked_for():
    """The failure this prevents: a new plugin file that is simply not in the .exe, found by
    a user rather than by the release."""
    missing = _plugin_modules_on_disk() - set(REQUIRED_MODULES)

    assert not missing, (
        f"these plugin modules are not checked for in the frozen build: {sorted(missing)} - "
        "add them to REQUIRED_MODULES in scripts/verify_frozen.py"
    )


def test_the_list_names_nothing_that_no_longer_exists():
    """The other direction: a renamed module would otherwise fail every release with a
    complaint about something that was deliberately removed."""
    on_disk = _plugin_modules_on_disk()
    stale = [name for name in REQUIRED_MODULES if name.startswith("src.plugins") and name not in on_disk]

    assert not stale, f"REQUIRED_MODULES names modules that are gone: {stale}"


@pytest.mark.parametrize("folder,pattern,label", BUNDLED_TREES)
def test_the_counted_resource_folders_exist_and_are_not_empty(folder, pattern, label):
    """A count against an empty folder passes for the wrong reason: zero equals zero."""
    matches = list((ROOT / folder).glob(f"**/{pattern}"))

    assert (ROOT / folder).is_dir(), f"{folder} is gone; the {label} check would compare 0 to 0"
    assert matches, f"{folder} holds no {pattern} files; the {label} check proves nothing"


def test_the_hidden_imports_in_the_build_cover_the_plugin_entry_points():
    """build.py and verify_frozen.py have to agree: one puts the plugin in, the other checks
    it arrived. A plugin added to the checker but not to the build would fail every release
    with no clue why."""
    build_script = (ROOT / "scripts" / "build.py").read_text(encoding="utf-8")
    entry_points = [name for name in REQUIRED_MODULES if name.endswith(".plugin")]

    assert entry_points, "no plugin entry points listed - REQUIRED_MODULES looks wrong"
    for entry in entry_points:
        assert entry in build_script, (
            f"{entry} is checked for in the .exe but never passed to PyInstaller as a "
            "--hidden-import in scripts/build.py"
        )
