"""The dialogs around the update check, and the promise they make about it.

The check itself is tested in test_update_checker.py. What is tested here is the half the
user actually sees: the consent box asked before anything leaves the machine, and the three
boxes that report the result.
"""
from PyQt6.QtNetwork import QNetworkReply
from PyQt6.QtWidgets import QMessageBox, QWidget

from src import update_dialogs
from src.UpdateChecker import UpdateChecker
from tests.test_update_checker import _FakeManager, _FakeReply


def test_consent_text_names_the_user_agent_the_request_actually_sends():
    """The consent box promises exactly what goes over the wire, and the request that goes
    over the wire is built in a different file. Interpolating the one constant is what stops
    the promise and the header from drifting apart - a stale privacy promise is worse than
    none, because it is believed."""
    assert UpdateChecker.USER_AGENT.decode() in update_dialogs.consent_text()


def test_the_request_carries_exactly_that_user_agent():
    """The other half of the same guarantee: the constant is not decoration, it is the
    header."""
    checker = UpdateChecker("0.1.0", manager=_FakeManager(_FakeReply()))

    checker.check_now()

    assert bytes(checker._manager.last_request.rawHeader(b"User-Agent")) == UpdateChecker.USER_AGENT


def test_consent_text_does_not_promise_that_nothing_identifying_is_sent():
    """It used to say 'nothing else is sent' flat out, which was not quite true: an IP and a
    self-identifying User-Agent land in GitHub's access logs."""
    text = update_dialogs.consent_text()

    assert "IP address" in text
    assert "User-Agent" in text


def test_confirm_check_defaults_to_no(qtbot, monkeypatch):
    """A network call the user has to actively agree to, not one they dismiss into."""
    parent = QWidget()
    qtbot.addWidget(parent)
    seen = {}

    def fake_exec(box):
        seen["default"] = box.defaultButton()
        seen["buttons"] = box.standardButtons()
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    update_dialogs.confirm_check(parent)

    assert seen["default"] is not None
    assert seen["default"].text().endswith("No")
    assert seen["buttons"] == QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No


def test_confirm_check_is_false_when_declined(qtbot, monkeypatch):
    parent = QWidget()
    qtbot.addWidget(parent)
    monkeypatch.setattr(
        QMessageBox, "exec",
        lambda box: box.setResult(QMessageBox.StandardButton.No)
    )

    assert update_dialogs.confirm_check(parent) is False


def test_show_available_opens_the_release_page_when_asked(qtbot, monkeypatch):
    parent = QWidget()
    qtbot.addWidget(parent)
    opened = []
    monkeypatch.setattr("src.update_dialogs.open_external_url", opened.append)
    # The "Open Releases Page" button is the one added with ActionRole.
    monkeypatch.setattr(
        QMessageBox, "exec",
        lambda box: box.setActiveWindow() if False else None
    )
    monkeypatch.setattr(
        QMessageBox, "clickedButton",
        lambda box: next(b for b in box.buttons() if b.text() == "Open Releases Page")
    )

    update_dialogs.show_available(parent, "v9.9.9", "https://example.com/release")

    assert opened == ["https://example.com/release"]


def test_show_available_opens_nothing_when_closed(qtbot, monkeypatch):
    parent = QWidget()
    qtbot.addWidget(parent)
    opened = []
    monkeypatch.setattr("src.update_dialogs.open_external_url", opened.append)
    monkeypatch.setattr(QMessageBox, "exec", lambda box: None)
    monkeypatch.setattr(
        QMessageBox, "clickedButton",
        lambda box: next(b for b in box.buttons() if b.text() == "Close")
    )

    update_dialogs.show_available(parent, "v9.9.9", "https://example.com/release")

    assert opened == []


def test_failed_dialog_repeats_the_reason(qtbot, monkeypatch):
    """A failed check that only says 'it failed' is a support ticket."""
    parent = QWidget()
    qtbot.addWidget(parent)
    shown = {}
    monkeypatch.setattr(QMessageBox, "exec", lambda box: shown.update(text=box.text()))

    update_dialogs.show_failed(parent, "Host not found")

    assert "Host not found" in shown["text"]


def test_up_to_date_dialog_names_the_running_version(qtbot, monkeypatch):
    parent = QWidget()
    qtbot.addWidget(parent)
    shown = {}
    monkeypatch.setattr(QMessageBox, "exec", lambda box: shown.update(text=box.text()))

    update_dialogs.show_up_to_date(parent)

    from src.utils import get_current_version
    assert get_current_version() in shown["text"]


def test_a_reply_error_still_reaches_a_dialog(qtbot):
    """Guards the seam rather than the dialog: the checker reports failures as a signal, and
    that signal is what GoonerApp hangs the dialog off."""
    checker = UpdateChecker(
        "0.1.0",
        manager=_FakeManager(_FakeReply(error=QNetworkReply.NetworkError.HostNotFoundError,
                                        error_string="Host not found")),
    )
    seen = []
    checker.check_failed.connect(seen.append)

    checker.check_now()
    checker._manager._reply.finished.emit()

    assert seen == ["Host not found"]
