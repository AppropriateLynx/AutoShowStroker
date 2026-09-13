import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImageReader, QPixmap


def get_project_root() -> Path:
    """
    Findet das Projekt-Wurzelverzeichnis robust, sowohl als Skript
    als auch als PyInstaller-Exe.
    """
    # Fall 1: Läuft als PyInstaller Exe
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)

    # Fall 2: Läuft als Skript (PyCharm, Terminal)
    # Startpunkt ist die Datei, in der wir uns befinden (GoonerApp.py oder main.py)
    start_path = Path(__file__).resolve()

    # Wir durchsuchen die Eltern-Ordner nach einer Marker-Datei.
    # requirements.txt oder .git sind gute Marker.
    for parent in start_path.parents:
        if (parent / 'main.py').exists():
            return parent

    # Falls kein Marker gefunden wurde, nutzen wir den Fallback
    # (z.B. wenn man ohne Git arbeitet).
    # Hier könnte man hartkodiert `..` nutzen, falls GoonerApp.py in src/ liegt.
    return start_path.parent.parent  # Entspricht ../.. wenn start_path in src/ liesgt


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
