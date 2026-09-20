import sys

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from src import crash_handler, theme
from src.GoonerApp import GoonerApp
from src.SplashScreen import SplashScreen

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Before anything that could fail, and after the QApplication so the report has
    # somewhere to appear. PyQt6 aborts the process when an exception escapes a slot, so
    # this hook is the only chance to leave anything behind - see src/crash_handler.py.
    crash_handler.install()
    # QStandardPaths resolves the app data directory through these, so UserDataStore
    # writes to %LOCALAPPDATA%\GoonerCock\GoonerApp. They match the QSettings org/app names
    # GoonerApp passes explicitly, so the registry location is unaffected.
    app.setOrganizationName("GoonerCock")
    app.setApplicationName("GoonerApp")
    app.setStyle("Fusion")
    app.setPalette(theme.build_palette())
    app.setStyleSheet(theme.GLOBAL_QSS)

    # Read straight from QSettings rather than from the window: the whole point below is to
    # get the splash on screen *before* GoonerApp is constructed. Same key GoonerApp reads.
    show_splash = QSettings("GoonerCock", "GoonerApp").value(
        "GoonerApp/show_startup_splash", GoonerApp.DEFAULTS["show_startup_splash"], type=bool
    )

    holder = {}

    def _build_main_window():
        holder["window"] = GoonerApp()

    def _reveal_main_window():
        window = holder.get("window") or GoonerApp()
        window.showMaximized()
        window.maybe_show_whats_new_on_startup()
        holder["window"] = window

    if show_splash:
        splash = SplashScreen()
        # Construction happens on fade_in_finished, i.e. while the splash is already up and
        # fully visible, so its 1.8s runs concurrently with the load instead of after it.
        # The logo sits still during that stretch, which is what a static logo does anyway.
        splash.fade_in_finished.connect(_build_main_window)
        splash.finished.connect(_reveal_main_window)
        splash.show()
    else:
        _build_main_window()
        _reveal_main_window()

    sys.exit(app.exec())
