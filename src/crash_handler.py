"""What the app does with an exception nobody caught.

Without this, an uncaught exception killed the process and left nothing behind. The shipped
app is built `--windowed`, where `sys.stdout` is None, so the traceback Python prints goes
nowhere at all - a user's bug report then has no artifact, and neither does anyone trying to
fix it. The Intiface crash is the worked example: finding a RecursionError took a
reproduction and a purpose-built tracing script, when it would have been one logged line.

PyQt6 makes this sharper than ordinary Python, in a way worth being exact about because it
was measured rather than assumed. An exception escaping a slot does not unwind to the top of
the program: PyQt hands it to `sys.excepthook`. While that is Python's *default* hook, PyQt
follows up by aborting the process - which is why an unhandled error used to end the app
outright, with the `--windowed` build printing the traceback to nowhere. Installing a hook of
our own is what stops the abort: PyQt treats the exception as handled, and the event loop
carries on with the next event.

So this module does two things at once, and the second is a product decision rather than a
technical one: it records the failure, **and** the app survives it. For a slideshow with a
rhythm behind it that is the right trade - a session that keeps running while telling you
something went wrong beats one that vanishes mid-use. It is not the right trade for every
kind of program, and anyone moving this elsewhere should decide again.

Two more decisions worth knowing:

**The log entry comes first, the dialog second.** A display that cannot be built must not
cost the artifact.

**The dialog carries the traceback, not an apology.** Diagnostic logging is off by default
and deliberately stays that way (see applog), so for most users the screen is the only place
the traceback will ever exist. Putting it in `detailedText()` keeps it out of the way while
leaving it selectable and copyable into a bug report. Nothing is sent anywhere.
"""
import sys
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox

from src import applog

log = applog.get_logger(__name__)

TITLE = "GoonerApp hit a problem"
MESSAGE = (
    "Something went wrong that the app did not expect.\n\n"
    "It may keep working, or it may close. If you want to report this, the details button "
    "below has the technical part - copy it into the Discord."
)

# True while a dialog is on screen. QMessageBox.exec() runs a nested event loop, so Qt keeps
# dispatching while the box is up - a timer firing there and raising comes straight back
# here, into this handler from inside itself. Without the guard that is a modal box opened
# on top of a modal box.
#
# It guards *only* the dialog. An earlier version bailed out of the whole handler, which
# meant a failure occurring during the report was never even written down - defeating the
# one thing this module exists to do.
_showing = False

# Faults already put in front of the user this session. Because the app now survives an
# unhandled exception, the same one can happen again - something failing in a paint or a
# repeating timer would otherwise raise a modal box every time it fired, which is worse than
# the original problem. Every occurrence is still logged; only the interruption is
# suppressed, and only for a fault already shown.
_already_shown = set()


def _signature(exc_type, tb):
    """What counts as "the same failure again": the type and where it was raised."""
    last = tb
    while last is not None and last.tb_next is not None:
        last = last.tb_next
    if last is None:
        return (exc_type.__name__, None, None)
    frame = last.tb_frame
    return (exc_type.__name__, frame.f_code.co_filename, last.tb_lineno)


def _report(exc_type, value, tb):
    global _showing
    if issubclass(exc_type, KeyboardInterrupt):
        # Someone asking the program to stop, not a crash. Hand it back to Python.
        sys.__excepthook__(exc_type, value, tb)
        return

    # Unconditional, and before anything else. Every failure is recorded, including one that
    # happens while an earlier one is being reported, and a dialog that cannot be built
    # cannot cost the record. Whether this reaches a file is the user's choice - applog is
    # opt-in - but it is never this module's decision to skip it.
    log.error("Unhandled exception", exc_info=(exc_type, value, tb))

    if _showing:
        return
    signature = _signature(exc_type, tb)
    if signature in _already_shown:
        return

    _already_shown.add(signature)
    _showing = True
    try:
        _show_dialog(exc_type, value, tb)
    finally:
        _showing = False


def _show_dialog(exc_type, value, tb):
    """Best effort. There may be no QApplication yet, or no display at all."""
    if QApplication.instance() is None:
        return
    try:
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(TITLE)
        box.setText(MESSAGE)
        box.setDetailedText("".join(traceback.format_exception(exc_type, value, tb)))
        box.setStandardButtons(QMessageBox.StandardButton.Close)
        box.exec()
    except Exception:
        # Already handling a crash; making a second one here would help nobody. The log
        # entry above is the part that matters and has already happened.
        log.warning("Could not show the crash dialog", exc_info=True)


def install() -> None:
    """Routes uncaught exceptions here. Call once, as early as there is a QApplication."""
    sys.excepthook = _report
