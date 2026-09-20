"""What happens when something goes wrong that nobody caught.

Until now an uncaught exception killed the process with nothing left behind: the app is
built `--windowed`, so the traceback went to a `sys.stdout` that is None. The Intiface
crash is the worked example - it took a reproduction and a purpose-built tracing script to
find a RecursionError that would have been one line in a log.

PyQt6 makes this sharper than ordinary Python. An exception escaping a slot does not
unwind to the top of the program; PyQt hands it to `sys.excepthook`, and aborts the process
afterwards only while that is Python's default hook. Installing one of our own both records
the failure and keeps the app alive - verified against a real QTimer slot rather than
assumed, because every test in this file would pass either way.
"""
import logging
import sys

import pytest
from PyQt6.QtWidgets import QMessageBox

from src import applog, crash_handler


@pytest.fixture
def captured_log():
    """The app logger writes with propagate=False, so caplog cannot see it."""
    records = []

    class Collector(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger(applog.LOGGER_NAME)
    handler = Collector()
    logger.addHandler(handler)
    yield records
    logger.removeHandler(handler)


@pytest.fixture
def shown_dialogs(qapp, monkeypatch):
    """Every box the handler tries to put on screen, without any of them opening.

    Takes `qapp` because the handler deliberately does nothing when there is no
    QApplication - without one these would pass for the wrong reason."""
    shown = []
    monkeypatch.setattr(
        QMessageBox, "exec",
        lambda box: shown.append((box.text(), box.detailedText())),
    )
    return shown


@pytest.fixture(autouse=True)
def restore_excepthook():
    original = sys.excepthook
    yield
    sys.excepthook = original
    crash_handler._showing = False
    crash_handler._already_shown.clear()


def _boom():
    raise ValueError("the thing exploded")


def _raise_and_report():
    try:
        _boom()
    except ValueError:
        sys.excepthook(*sys.exc_info())


def test_install_replaces_the_default_hook():
    crash_handler.install()

    assert sys.excepthook is not sys.__excepthook__


def test_the_traceback_reaches_the_log(captured_log, shown_dialogs):
    crash_handler.install()

    _raise_and_report()

    assert captured_log, "nothing was logged at all"
    record = captured_log[-1]
    assert record.levelno >= logging.ERROR
    assert record.exc_info is not None, "logged without the traceback attached"
    assert "the thing exploded" in logging.Formatter().formatException(record.exc_info)


def test_the_user_is_shown_something_they_can_report(shown_dialogs, captured_log):
    """With the diagnostic log off - the default - the dialog is the only artifact there is,
    so it carries the traceback rather than just apologising."""
    crash_handler.install()

    _raise_and_report()

    assert len(shown_dialogs) == 1
    message, details = shown_dialogs[0]
    assert message, "the box has no message"
    assert "ValueError" in details and "the thing exploded" in details
    assert "_boom" in details, "the detail is not a traceback"


def test_a_broken_dialog_is_survived(qapp, captured_log, monkeypatch):
    """A display that cannot be built is not allowed to become a second crash."""
    def exploding_box(_box):
        raise RuntimeError("even the dialog is broken")

    monkeypatch.setattr(QMessageBox, "exec", exploding_box)
    crash_handler.install()

    _raise_and_report()   # must not raise


def test_a_failure_inside_the_dialogs_own_event_loop(qapp, captured_log, monkeypatch):
    """The re-entry that can really happen, and the reason this needs a guard at all.

    QMessageBox.exec() runs a nested event loop, so Qt keeps dispatching while the box is
    up. A timer firing there and raising goes straight back to sys.excepthook - into this
    handler, from inside itself. Without a guard that is a modal box opened on top of a
    modal box; guarded wrongly, the second failure is dropped without being recorded, which
    would defeat the point of the module.
    """
    attempts = []

    def reentering_box(_box):
        attempts.append(1)
        if len(attempts) == 1:
            try:
                raise RuntimeError("a timer misfired while the box was up")
            except RuntimeError:
                sys.excepthook(*sys.exc_info())

    monkeypatch.setattr(QMessageBox, "exec", reentering_box)
    crash_handler.install()

    _raise_and_report()

    assert len(attempts) == 1, "a second box was opened on top of the first"
    logged = [logging.Formatter().formatException(r.exc_info) for r in captured_log if r.exc_info]
    assert any("the thing exploded" in entry for entry in logged), "the first failure was lost"
    assert any("a timer misfired" in entry for entry in logged), (
        "the failure that happened during the report was never recorded"
    )


def test_a_broken_dialog_still_leaves_the_log_entry(qapp, captured_log, monkeypatch):
    """Order matters: the log is written before anything is put on screen, so the artifact
    survives a display that cannot be built."""
    monkeypatch.setattr(QMessageBox, "exec", lambda _box: (_ for _ in ()).throw(RuntimeError("no display")))
    crash_handler.install()

    _raise_and_report()

    assert any(r.exc_info for r in captured_log), "the traceback was lost when the dialog failed"


def test_the_same_failure_only_interrupts_you_once(shown_dialogs, captured_log):
    """Because the app now survives, the same fault can happen again - and something failing
    in a paint or a timer would otherwise put a modal box up every time it fired. The record
    is still written each time; only the interruption is suppressed."""
    crash_handler.install()

    _raise_and_report()
    _raise_and_report()
    _raise_and_report()

    assert len(shown_dialogs) == 1, "the same failure asked for attention more than once"
    assert len([r for r in captured_log if r.exc_info]) == 3, "a repeat went unrecorded"


def test_a_different_failure_is_still_worth_showing(shown_dialogs, captured_log):
    """The suppression is per fault, not a one-shot mute for the rest of the session."""
    crash_handler.install()

    _raise_and_report()
    try:
        raise TypeError("a completely different problem")
    except TypeError:
        sys.excepthook(*sys.exc_info())

    assert len(shown_dialogs) == 2
    assert "TypeError" in shown_dialogs[1][1]


def test_ctrl_c_is_left_to_python(shown_dialogs, captured_log):
    """A KeyboardInterrupt is someone asking the program to stop, not a crash to report."""
    crash_handler.install()

    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        sys.excepthook(*sys.exc_info())

    assert not shown_dialogs
    assert not [r for r in captured_log if r.levelno >= logging.ERROR]


def test_it_reports_without_a_running_application(shown_dialogs, captured_log, monkeypatch):
    """A crash during startup happens before there is anything to show a dialog on. It still
    has to be logged rather than swallowed."""
    monkeypatch.setattr("src.crash_handler.QApplication.instance", staticmethod(lambda: None))
    crash_handler.install()

    _raise_and_report()

    assert not shown_dialogs
    assert any(r.exc_info for r in captured_log)
