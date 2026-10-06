"""Locate a SoundFont for the audio engine, or download a default piano one."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

# Default download: YDP Grand Piano (Yamaha Disklavier Pro samples), CC-BY 3.0.
# ~37 MB compressed, ~118 MB extracted. Too large to ship in the repository.
DEFAULT_SOUNDFONT_URL = (
    "https://freepats.zenvoid.org/Piano/YDP-GrandPiano/YDP-GrandPiano-SF2-20160804.tar.bz2"
)
DEFAULT_SOUNDFONT_SHA256 = "d243dc3e182a60df2a16e92828c1821cf3eb5748b45e2e2bdcfa9cf7af056026"
DEFAULT_SOUNDFONT_ATTRIBUTION = (
    "YDP Grand Piano by Zenph Studios / OLPC, packaged by FreePats "
    "(https://freepats.zenvoid.org). Licensed CC-BY 3.0."
)

ENV_VAR = "KEYFALL_SOUNDFONT"
_EXTENSIONS = (".sf2", ".sf3")

# Well-known locations where OS packages install General MIDI SoundFonts.
_SYSTEM_PATHS = [
    "/usr/share/sounds/sf2/FluidR3_GM.sf2",
    "/usr/share/soundfonts/FluidR3_GM.sf2",
    "/usr/share/sounds/sf2/default-GM.sf2",
    "/usr/share/soundfonts/default.sf2",
    "/usr/share/sounds/sf3/default-GM.sf3",
    "/usr/share/soundfonts/FluidR3_GM.sf3",
    "/opt/homebrew/share/fluid-synth/sf2/VintageDreamsWaves-v2.sf2",
    "/usr/local/share/fluid-synth/sf2/VintageDreamsWaves-v2.sf2",
]


def user_soundfont_dir() -> Path:
    """Per-user directory where downloaded SoundFonts are stored."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "keyfall" / "soundfonts"


def find_soundfont(explicit: str | Path | None = None) -> Path | None:
    """Return the first usable SoundFont, or None.

    Search order: explicit path, $KEYFALL_SOUNDFONT, the user SoundFont
    directory (piano-named files first), then common system install paths.
    """
    for candidate in (explicit, os.environ.get(ENV_VAR)):
        if candidate and Path(candidate).is_file():
            return Path(candidate)

    user_dir = user_soundfont_dir()
    if user_dir.is_dir():
        found = sorted(p for p in user_dir.iterdir() if p.suffix.lower() in _EXTENSIONS)
        found.sort(key=lambda p: "piano" not in p.name.lower())
        if found:
            return found[0]

    for path in _SYSTEM_PATHS:
        if Path(path).is_file():
            return Path(path)
    return None


GM_ENV_VAR = "KEYFALL_GM_SOUNDFONT"
_GM_HINTS = ("gm", "general", "fluidr3", "musescore", "timgm", "generaluser", "arachno")


def find_gm_soundfont(exclude: Path | None = None) -> Path | None:
    """A General MIDI SoundFont for backing instruments (guitar, strings, drums...).

    Used alongside the main (often piano-only) SoundFont. Search order:
    $KEYFALL_GM_SOUNDFONT, GM-looking files in the user folder, system paths.
    """
    exclude = exclude.resolve() if exclude else None

    def ok(path: Path) -> bool:
        return path.is_file() and (exclude is None or path.resolve() != exclude)

    env = os.environ.get(GM_ENV_VAR)
    if env and ok(Path(env)):
        return Path(env)
    user_dir = user_soundfont_dir()
    if user_dir.is_dir():
        for p in sorted(user_dir.iterdir()):
            if p.suffix.lower() in _EXTENSIONS and any(h in p.name.lower() for h in _GM_HINTS):
                if ok(p):
                    return p
    for path in _SYSTEM_PATHS:
        if ok(Path(path)):
            return Path(path)
    return None


def download_default_soundfont(
    dest_dir: Path | None = None, url: str = DEFAULT_SOUNDFONT_URL
) -> Path:
    """Download and extract the default piano SoundFont. Returns the .sf2 path."""
    dest_dir = dest_dir or user_soundfont_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "soundfont.tar.bz2"
        with urllib.request.urlopen(url) as resp, archive.open("wb") as out:
            shutil.copyfileobj(resp, out)

        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if url == DEFAULT_SOUNDFONT_URL and digest != DEFAULT_SOUNDFONT_SHA256:
            raise RuntimeError(f"Checksum mismatch for {url}: got {digest}")

        sf_path: Path | None = None
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                name = Path(member.name).name
                if not member.isfile() or not name.lower().endswith((*_EXTENSIONS, ".txt")):
                    continue
                src = tar.extractfile(member)
                if src is None:
                    continue
                target = dest_dir / name
                with target.open("wb") as out:
                    shutil.copyfileobj(src, out)
                if target.suffix.lower() in _EXTENSIONS:
                    sf_path = target

    if sf_path is None:
        raise RuntimeError(f"No SoundFont found in archive from {url}")
    (dest_dir / "ATTRIBUTION.txt").write_text(DEFAULT_SOUNDFONT_ATTRIBUTION + "\n")
    return sf_path
