"""What the user is asked before the update check runs, and what they are told after.

Split out of GoonerApp for the same reason src/plugins/intiface/consent.py is its own file:
the question asked before the app touches the network is worth being able to find, read and
audit without wading through a window class. The request itself lives in UpdateChecker - see
there for why that one is isolated too.

The consent text interpolates UpdateChecker.USER_AGENT rather than repeating it. The promise
and the header it describes sit in different files, and a privacy promise that has quietly
drifted out of date is worse than none at all, because it is believed.
"""
from PyQt6.QtWidgets import QMessageBox

from src.UpdateChecker import UpdateChecker
from src.utils import get_current_version, open_external_url


def consent_text() -> str:
    """Spells out everything that actually goes over the wire.

    This used to say "nothing else is sent" flat out, which was not quite true: the request
    carries a User-Agent identifying the app, so GitHub's access logs tie an IP to "runs
    GoonerApp". Small, but a privacy promise is worth nothing unless it is exact.
    """
    return (
        "This will send one request to GitHub.com to check the latest release version.\n\n"
        "It carries your IP address (unavoidable for any web request) and a User-Agent of "
        f'"{UpdateChecker.USER_AGENT.decode()}", which identifies the app to GitHub. Nothing '
        "else is sent - no folders, no filenames, no statistics, nothing identifying you or "
        "your machine - and this never runs on its own.\n\n"
        "Continue?"
    )


def confirm_check(parent) -> bool:
    """Asks before anything leaves the machine. Defaults to No."""
    # Built via explicit QMessageBox(...) + exec() rather than the static .question()
    # convenience method - the static convenience methods are separate C++ entry points that
    # bypass Python-level QMessageBox.exec entirely, so tests/_no_modal_dialogs cannot neuter
    # them and a real modal loop would open during tests.
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Check for Updates?")
    box.setText(consent_text())
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    box.exec()
    return box.clickedButton() is box.button(QMessageBox.StandardButton.Yes)


def show_available(parent, latest_tag, release_url):
    box = QMessageBox(parent)
    box.setWindowTitle("Update Available")
    box.setText(f"A new version is available: {latest_tag} (you're on v{get_current_version()}).")
    open_button = box.addButton("Open Releases Page", QMessageBox.ButtonRole.ActionRole)
    box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() is open_button:
        open_external_url(release_url)


def show_up_to_date(parent):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle("Up to Date")
    box.setText(f"You're on the latest version (v{get_current_version()}).")
    box.exec()


def show_failed(parent, message):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Update Check Failed")
    box.setText(f"Couldn't check for updates:\n{message}")
    box.exec()
