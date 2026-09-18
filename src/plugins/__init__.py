"""Optional parts of the app, each one a folder that can be deleted whole.

This is not a plugin *loader*: there is no discovery, no download and no path someone
else's code can arrive on. The names are literals in the app's own source, and the only
thing dynamic about the lookup is whether the folder is still there - which is the one
property worth having, because "delete the bit you do not want" should be a supported
answer for a feature that opens a network connection.
"""
import importlib
import importlib.util

from src.applog import get_logger

log = get_logger(__name__)

# The optional parts this app knows about, and the object that speaks for each of them.
KNOWN_PLUGINS = {"intiface": ("src.plugins.intiface.plugin", "IntifacePlugin")}


def load_optional_plugin(name, main_app):
    """The plugin's entry object, or None when its folder is not installed.

    Only a missing folder is tolerated. An ImportError raised from *inside* a plugin that
    is present is a real bug and is left to travel - swallowing it would turn a typo into
    a feature that silently stops existing.
    """
    module_name, attribute = KNOWN_PLUGINS[name]
    try:
        # ModuleNotFoundError rather than None when it is the package itself that is gone.
        found = importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        found = False
    if not found:
        log.info("Optional plugin %s is not installed", name)
        return None
    module = importlib.import_module(module_name)
    return getattr(module, attribute)(main_app)
