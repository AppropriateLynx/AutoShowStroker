"""What the user is told before a single byte leaves the machine.

The app already asks before its one other outbound request (Help > Check for Updates) and
spells out exactly what that request carries. Device output carries considerably more -
a live account of a session while it happens - so it is asked for in the same voice and
with the same precision.
"""
from PyQt6.QtWidgets import QCheckBox, QMessageBox

from src.plugins.intiface.controller import SETTINGS_PREFIX

CONSENT_KEY = f"{SETTINGS_PREFIX}/consent_acknowledged"


def device_output_consent_text(url: str) -> str:
    """Spells out everything that actually goes over the wire.

    The address is quoted back rather than checked against a list of local ones: the user
    typed it, only they know whether it is this machine, and the app ships no addresses of
    its own to compare it with.
    """
    return (
        f"This will open a WebSocket connection to {url} and keep it open for as long as "
        "device output stays enabled.\n\n"
        'Over it, GoonerApp sends the client name "GoonerApp", device discovery and '
        "heartbeat messages, and movement and stop commands. Those commands are a live "
        "account of your session while it happens: when it starts and ends, when every "
        "beat lands, and every pause. Nothing else is sent - no media, no folder names, "
        "no filenames, no callouts, no statistics.\n\n"
        "That address is yours, not the app's. If it is not on this machine, everything "
        "above travels across your network, and an unencrypted ws:// address sends it in "
        "the clear.\n\n"
        "Device output switches itself off again at every launch, so you will be asked "
        "for it the next time too.\n\n"
        "Enable device output?"
    )


def confirm_device_output(parent, url, settings) -> bool:
    """True when device output may be switched on. Asks unless the user has said stop."""
    if settings.value(CONSENT_KEY, False, type=bool):
        return True
    # Built via explicit QMessageBox(...) + exec() rather than the static .question()
    # convenience method - the statics are separate C++ entry points that bypass
    # Python-level QDialog.exec, so tests/_no_modal_dialogs cannot neuter them.
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Enable Device Output?")
    box.setText(device_output_consent_text(url))
    remember = QCheckBox("Don't ask me this again")
    box.setCheckBox(remember)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    box.exec()
    accepted = box.clickedButton() is box.button(QMessageBox.StandardButton.Yes)
    if accepted and remember.isChecked():
        settings.setValue(CONSENT_KEY, True)
    return accepted
