from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from src import applog, theme

log = applog.get_logger(__name__)


class PrivacyDataDialog(QDialog):
    """Says where the app keeps things, and lets the user delete any of it.

    The Guide's Privacy tab promises nothing leaves the machine. That promise is only
    half of it: a user who wants their traces gone also has to be able to find them and
    remove them. A portable .exe has no uninstaller, so without this dialog the only route
    was regedit plus Explorer, against locations the app never named.

    Deletion is per category rather than one big button - a user clearing the folder paths
    before handing the laptop over should not have to lose their session history too.
    """

    # key -> (label, description). The key doubles as the data-store file name for the
    # JSON categories; "diagnostic_log" and "settings" are handled specially.
    CATEGORIES = (
        ("session_history", "Session history", "every recorded session and your personal records"),
        ("custom_patterns", "Custom rhythm patterns", "the patterns you built in the pattern editor"),
        ("custom_phrase_files", "Custom phrase files", "the callout files you added"),
        ("last_selected_folders", "Last used media folders", "the folder paths the picker remembers"),
        ("diagnostic_log", "Diagnostic log", "the opt-in log file, if you turned it on"),
        ("settings", "All settings", "every slider, toggle and the selected language"),
    )

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Privacy & Data")
        self.setModal(True)
        self.resize(620, 520)

        self.main_app = main_app
        self.checkboxes = {}

        layout = QVBoxLayout(self)

        title = QLabel("Your Data")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {theme.ACCENT};")
        layout.addWidget(title)

        intro = QLabel(
            "GoonerApp never sends any of this anywhere. It does have to keep some of it on "
            "disk, though - here is exactly what, and where."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {theme.TEXT};")
        layout.addWidget(intro)

        self.locations_label = QLabel(self.locations_text())
        self.locations_label.setWordWrap(True)
        # Selectable so the user can copy a path out rather than retyping it.
        self.locations_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.locations_label.setStyleSheet(
            f"color: {theme.TEXT}; background-color: {theme.SURFACE_DARK}; "
            "border-radius: 6px; padding: 8px; font-family: monospace;"
        )
        layout.addWidget(self.locations_label)

        self.btn_open_folder = QPushButton("Open data folder")
        self.btn_open_folder.clicked.connect(self._on_open_folder)
        layout.addWidget(self.btn_open_folder)

        delete_header = QLabel("Delete my data")
        delete_header.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {theme.ACCENT}; margin-top: 12px;"
        )
        layout.addWidget(delete_header)

        for key, _label, description in self.CATEGORIES:
            # Text is filled in by refresh_counts() below, which appends the live count.
            checkbox = QCheckBox()
            checkbox.setToolTip(description)
            checkbox.toggled.connect(self._update_delete_enabled)
            self.checkboxes[key] = checkbox
            layout.addWidget(checkbox)

        self.btn_delete = QPushButton("Delete selected...")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        layout.addWidget(self.btn_delete)

        layout.addStretch()

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("primary")
        self.btn_close.clicked.connect(self.accept)
        button_row.addWidget(self.btn_close)
        layout.addLayout(button_row)

        self.refresh_counts()

    # --- disclosure ---

    def locations_text(self) -> str:
        return (
            f"Data files:\n{self.main_app.data_store.base_dir}\n\n"
            f"Settings:\n{self.main_app.settings.fileName()}"
        )

    def _open_url(self, url):
        QDesktopServices.openUrl(url)

    def _on_open_folder(self):
        base_dir = self.main_app.data_store.base_dir
        # Created on demand: nothing has been saved yet on a fresh install, and opening
        # Explorer on a path that doesn't exist just fails silently.
        try:
            base_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            log.error("Could not create the data folder: %s", error)
            return
        self._open_url(QUrl.fromLocalFile(str(base_dir)))

    # --- counts ---

    def category_counts(self) -> dict:
        store = self.main_app.data_store
        return {
            "session_history": len(self.main_app.score_tracker.get_history()),
            "custom_patterns": len(self.main_app.beat_handler.custom_beat_patterns),
            "custom_phrase_files": len(self.main_app.callout_handler.custom_phrase_files),
            "last_selected_folders": len(store.load("last_selected_folders", [])),
            # Files, not lines: rotated backups count too, and reading them to count lines
            # just to label a checkbox would be silly.
            "diagnostic_log": len(applog.log_file_paths(store.base_dir)),
            "settings": len(self.main_app.settings.allKeys()),
        }

    def refresh_counts(self):
        counts = self.category_counts()
        for key, label, _description in self.CATEGORIES:
            count = counts[key]
            suffix = "nothing stored" if count == 0 else f"{count} stored"
            self.checkboxes[key].setText(f"{label} ({suffix})")

    # --- deleting ---

    def _update_delete_enabled(self):
        self.btn_delete.setEnabled(any(box.isChecked() for box in self.checkboxes.values()))

    def _selected_keys(self) -> list:
        return [key for key, box in self.checkboxes.items() if box.isChecked()]

    def _label_for(self, key: str) -> str:
        return next(label for entry_key, label, _ in self.CATEGORIES if entry_key == key)

    def _confirm_deletion(self, keys) -> bool:
        listed = "\n".join(f"  - {self._label_for(key)}" for key in keys)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Delete this data?")
        box.setText(f"This permanently deletes:\n\n{listed}\n\nThis cannot be undone.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    def clear_categories(self, keys):
        """Deletes the named categories, resetting the live objects as well as the files.

        The in-memory reset is the part that matters: dropping session_history.json while
        ScoreTracker still holds the list would just write it back at the next session end.
        """
        log.info("Clearing user data: %s", ", ".join(keys))
        for key in keys:
            if key == "session_history":
                self.main_app.score_tracker.clear_history()
            elif key == "custom_patterns":
                self.main_app.beat_handler.clear_custom_patterns()
            elif key == "custom_phrase_files":
                self.main_app.callout_handler.clear_custom_phrase_files()
            elif key == "last_selected_folders":
                self.main_app.data_store.delete("last_selected_folders")
            elif key == "diagnostic_log":
                applog.delete_log_files(self.main_app.data_store.base_dir)
            elif key == "settings":
                self.main_app.settings.clear()
                self.main_app.settings.sync()

    def _on_delete_clicked(self):
        keys = self._selected_keys()
        if not keys or not self._confirm_deletion(keys):
            return
        self.clear_categories(keys)
        for box in self.checkboxes.values():
            box.setChecked(False)
        self.refresh_counts()
