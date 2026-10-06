"""The song library folder: where it lives, starter songs, opening it in the OS."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

STARTER_DIR = Path(__file__).resolve().parent / "assets" / "songs"
MARKER = ".keyfall-starter-songs"  # written once so deleted starter songs stay deleted


def default_songs_dir() -> Path:
    return Path.home() / "KeyFall" / "Songs"


def prepare_songs_dir(path: str | Path | None = None) -> Path:
    """Create the songs folder if needed and add the starter songs once.

    Starter songs are only copied into a folder that has never received them
    (tracked by a hidden marker file), so a user can delete them for good.
    An explicitly chosen folder that already has music is left untouched.
    """
    folder = Path(path).expanduser() if path else default_songs_dir()
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / MARKER
    if not marker.exists():
        has_music = any(f.suffix.lower() in (".mid", ".midi", ".xml", ".musicxml", ".mxl")
                        for f in folder.iterdir())
        if not has_music:
            for song in sorted(STARTER_DIR.glob("*.mid")):
                target = folder / song.name
                if not target.exists():
                    shutil.copyfile(song, target)
        marker.write_text("Starter songs were added to this folder by KeyFall.\n")
    return folder


def open_folder(path: str | Path) -> bool:
    """Open a folder in the system file manager. Returns False if that failed."""
    path = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        return True
    except (OSError, AttributeError):
        return False
