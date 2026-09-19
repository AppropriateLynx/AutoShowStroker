#!/usr/bin/env python
"""Build GoonerApp.exe locally via PyInstaller.

Anyone with a checkout of this repo can run this to produce their own
dist/GoonerApp.exe - it only builds, it never touches GitHub or pushes anything.

Usage:
    .venv\\Scripts\\python.exe scripts/build.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_pyinstaller() -> str:
    candidate = Path(sys.executable).with_name("pyinstaller.exe")
    return str(candidate) if candidate.exists() else "pyinstaller"


def build_exe() -> Path:
    subprocess.run(
        [
            find_pyinstaller(), "--noconfirm", "--onefile", "--windowed",
            "--add-data", "res;res", "--add-data", "VERSION;.",
            # Every optional plugin needs a line here. They are looked up by name at
            # runtime (see src/plugins/__init__.py), which import analysis cannot follow,
            # so without this the .exe starts with the plugin silently missing and
            # nothing says so except the log. Naming the entry module is enough - what it
            # imports is followed from there. --collect-submodules cannot do this job:
            # it resolves the package through the *building* interpreter, which has no
            # repo root on its path, and it fails quietly when it cannot.
            "--hidden-import", "src.plugins.intiface.plugin",
            # QtWebSockets is not reachable by import analysis either, because only a
            # plugin uses it. Without it the .exe ships with no Qt6WebSockets.dll and
            # device output cannot connect to anything at all.
            "--hidden-import", "PyQt6.QtWebSockets",
            "--icon", "res/icons/favicon.ico", "--name", "GoonerApp", "main.py",
        ],
        cwd=ROOT, check=True,
    )
    exe_path = ROOT / "dist" / "GoonerApp.exe"
    if not exe_path.exists():
        raise SystemExit(f"Build finished but {exe_path} was not found.")
    return exe_path


def main() -> None:
    exe_path = build_exe()
    print(f"Built {exe_path}")


if __name__ == "__main__":
    main()
