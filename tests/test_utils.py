import sys

import pytest

from src import utils
from src.utils import format_clock, format_duration, get_current_version, get_project_root


def test_get_project_root_finds_repo_root_from_script():
    root = get_project_root()
    assert (root / "main.py").exists()


def test_get_project_root_uses_meipass_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert get_project_root() == tmp_path


def test_get_current_version_reads_version_file(monkeypatch, tmp_path):
    (tmp_path / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    monkeypatch.setattr(utils, "get_project_root", lambda: tmp_path)

    assert get_current_version() == "1.2.3"


def test_get_current_version_strips_whitespace(monkeypatch, tmp_path):
    (tmp_path / "VERSION").write_text("  0.1.0  \n\n", encoding="utf-8")
    monkeypatch.setattr(utils, "get_project_root", lambda: tmp_path)

    assert get_current_version() == "0.1.0"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (None, "N/A"),
        (0, "0s"),
        (45, "45s"),
        (60, "1 Min"),
        (125, "2 Min 5s"),
    ],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (None, "N/A"),
        (0, "00:00"),
        (42, "00:42"),
        (522, "08:42"),
        (522.9, "08:42"),
        (3600, "1:00:00"),
        (3735, "1:02:15"),
    ],
)
def test_format_clock(seconds, expected):
    assert format_clock(seconds) == expected


# --- image loading ---


def _write_large_png(tmp_path, width, height):
    from PyQt6.QtCore import Qt as _Qt
    from PyQt6.QtGui import QImage

    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(_Qt.GlobalColor.red)
    path = tmp_path / "big.png"
    assert image.save(str(path))
    return path


def test_load_scaled_pixmap_fits_the_target_and_keeps_the_aspect_ratio(qapp, tmp_path):
    from PyQt6.QtCore import QSize

    path = _write_large_png(tmp_path, 2000, 1000)

    pixmap = utils.load_scaled_pixmap(str(path), QSize(200, 200))

    assert pixmap.width() == 200
    assert pixmap.height() == 100


def test_load_scaled_pixmap_decodes_at_the_target_size(qapp, tmp_path, monkeypatch):
    """QPixmap(path).scaled() decodes the full image first - 134ms for a 24MP JPEG versus
    22ms when the decoder is told the target size up front."""
    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QImageReader

    path = _write_large_png(tmp_path, 2000, 1000)
    requested = []

    class SpyReader(QImageReader):
        def setScaledSize(self, size):
            requested.append(size)
            super().setScaledSize(size)

    monkeypatch.setattr("src.utils.QImageReader", SpyReader)

    utils.load_scaled_pixmap(str(path), QSize(200, 200))

    assert requested == [QSize(200, 100)]


def test_load_scaled_pixmap_returns_a_null_pixmap_for_an_unreadable_file(qapp, tmp_path):
    from PyQt6.QtCore import QSize

    broken = tmp_path / "not-an-image.png"
    broken.write_bytes(b"nope")

    assert utils.load_scaled_pixmap(str(broken), QSize(100, 100)).isNull()


def test_load_scaled_pixmap_handles_an_invalid_target_size(qapp, tmp_path):
    from PyQt6.QtCore import QSize

    path = _write_large_png(tmp_path, 400, 200)

    pixmap = utils.load_scaled_pixmap(str(path), QSize(0, 0))

    assert not pixmap.isNull()


def test_a_foreign_scheme_url_is_not_opened(monkeypatch):
    """The one route out of the app to a web page, and the reason it is a route rather than
    a bare call: a release_url comes straight from the GitHub API response, and anything but
    http(s) would hand an arbitrary protocol handler to the shell on a single click."""
    opened = []
    monkeypatch.setattr("src.utils.QDesktopServices.openUrl", opened.append)

    utils.open_external_url("file:///C:/Windows/System32/calc.exe")

    assert opened == []


def test_an_https_url_is_opened(monkeypatch):
    opened = []
    monkeypatch.setattr("src.utils.QDesktopServices.openUrl", opened.append)

    utils.open_external_url("https://github.com/owner/repo/releases")

    assert [u.toString() for u in opened] == ["https://github.com/owner/repo/releases"]
