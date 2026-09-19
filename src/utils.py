import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QImageReader, QPixmap

from src import applog

log = applog.get_logger(__name__)


def get_project_root() -> Path:
    """Resolves the project root, both when run as a script and when frozen by PyInstaller.

    Every read under res/ (and the root VERSION file) has to go through this - a relative
    path resolves against the current working directory and breaks the packaged .exe as
    well as any launch from outside the repo root.
    """
    # Frozen by PyInstaller: resources are extracted to a temp directory it names for us.
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)

    # Running from source: walk up from this file looking for the repo's marker file.
    start_path = Path(__file__).resolve()
    for parent in start_path.parents:
        if (parent / 'main.py').exists():
            return parent

    # No marker found - fall back to ../.. , which is the repo root for a file in src/.
    return start_path.parent.parent


def get_current_version() -> str:
    return (get_project_root() / "VERSION").read_text(encoding="utf-8").strip()


def format_duration(seconds: float) -> str:
    if seconds is None:
        return "N/A"
    total_seconds = int(round(seconds))
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes = total_seconds // 60
    secs = total_seconds % 60
    if secs == 0:
        return f"{minutes} Min"
    return f"{minutes} Min {secs}s"


def format_clock(seconds: float) -> str:
    if seconds is None:
        return "N/A"
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def load_scaled_pixmap(file_path: str, target_size) -> QPixmap:
    """Loads an image already scaled to fit target_size, preserving the aspect ratio.

    QPixmap(path).scaled(...) decodes the file at full resolution first and only then
    shrinks it. Handing the target size to QImageReader instead lets the decoder do the
    scaling itself, and peaks at a fraction of the full uncompressed frame either way.

    The speedup depends on the format, so don't be surprised by a flat benchmark: measured
    on a 24MP source scaled to 1900x1000, JPEG goes 138ms -> 36ms (~3.9x, libjpeg scales in
    the DCT domain), while PNG is unchanged because libpng has to decode it in full
    regardless. Worth it for the JPEG case alone - that is what a photo library is.

    Returns a null QPixmap if the file can't be decoded, same as QPixmap(path) would.
    """
    reader = QImageReader(file_path)
    reader.setAutoTransform(True)  # honour EXIF orientation, which QPixmap(path) also does

    source_size = reader.size()
    if source_size.isValid() and not source_size.isEmpty() and target_size.isValid() \
            and not target_size.isEmpty():
        reader.setScaledSize(source_size.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio))

    image = reader.read()
    if image.isNull():
        return QPixmap()
    return QPixmap.fromImage(image)


def open_external_url(url_string):
    """Hands a URL to the browser, but only if it is one.

    The single route out of the app to a web page. release_url is whatever the GitHub API
    response said, and if that response is ever attacker-influenced, a file:// or custom
    scheme URL would otherwise be handed to the default Windows handler on a single click.
    """
    url = QUrl(url_string)
    if url.scheme() not in ("http", "https"):
        log.warning("Refusing to open a non-web URL: %r", url_string)
        return
    QDesktopServices.openUrl(url)
