"""Locate SoundFonts for the audio engine, and download free ones (piano and GM)."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
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


# --------------------------------------------------------------------------- downloads


@dataclass(frozen=True)
class SoundFontDownload:
    key: str
    label: str
    url: str
    sha256: str
    size_mb: int
    filename: str  # the SoundFont file that ends up in the user folder
    attribution: str
    archive: bool = False  # True: a .tar.* archive containing the SoundFont


PIANO_DOWNLOAD = SoundFontDownload(
    key="piano",
    label="Piano sound",
    url=DEFAULT_SOUNDFONT_URL,
    sha256=DEFAULT_SOUNDFONT_SHA256,
    size_mb=37,
    filename="YDP-GrandPiano-20160804.sf2",
    attribution=DEFAULT_SOUNDFONT_ATTRIBUTION,
    archive=True,
)

# General MIDI set for backing instruments and drums: MuseScore General, MIT license.
GM_DOWNLOAD = SoundFontDownload(
    key="gm",
    label="Instrument sounds",
    url="https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General.sf3",
    sha256="5b85b6c2c61d10b2b91cddd41efcce7b25cd31c8271d511c73afafbef20b6fa3",
    size_mb=40,
    filename="MuseScore_General.sf3",
    attribution=(
        "MuseScore General by S. Christian Collins, based on FluidR3 by Frank Wen and "
        "FluidR3Mono by Michael Cowgill; Temple Blocks by Ethan Winer; Drumline Cymbals by "
        "Michael Schorsch. MIT license. "
        "https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/"
    ),
)

DOWNLOADS = {d.key: d for d in (PIANO_DOWNLOAD, GM_DOWNLOAD)}


class DownloadCancelledError(Exception):
    pass


def installed_path(spec: SoundFontDownload, dest_dir: Path | None = None) -> Path | None:
    path = (dest_dir or user_soundfont_dir()) / spec.filename
    return path if path.is_file() else None


def download(
    spec: SoundFontDownload,
    dest_dir: Path | None = None,
    progress: Callable[[int, int], bool | None] | None = None,
    url: str | None = None,
) -> Path:
    """Download (and unpack) a SoundFont into the user folder. Returns its path.

    ``progress(done_bytes, total_bytes)`` is called as data arrives; returning
    False cancels. The file is verified against ``spec.sha256`` and only moved
    into place when complete, so a failed download never leaves a broken file.
    """
    dest_dir = dest_dir or user_soundfont_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = url or spec.url
    with tempfile.TemporaryDirectory(dir=dest_dir) as tmp:
        part = Path(tmp) / "download.part"
        digest = hashlib.sha256()
        with urllib.request.urlopen(url, timeout=30) as resp, part.open("wb") as out:
            total = int(resp.headers.get("Content-Length") or spec.size_mb * 1_000_000)
            done = 0
            while chunk := resp.read(256 * 1024):
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress is not None and progress(done, total) is False:
                    raise DownloadCancelledError(spec.label)
        if spec.sha256 and digest.hexdigest() != spec.sha256:
            raise RuntimeError(f"Checksum mismatch for {spec.label}; the download was discarded")

        if spec.archive:
            target = None
            with tarfile.open(part) as tar:
                for member in tar.getmembers():
                    name = Path(member.name).name
                    if not member.isfile() or not name.lower().endswith((*_EXTENSIONS, ".txt")):
                        continue
                    src = tar.extractfile(member)
                    if src is None:
                        continue
                    with (Path(tmp) / name).open("wb") as out:
                        shutil.copyfileobj(src, out)
                    shutil.move(str(Path(tmp) / name), dest_dir / name)
                    if name.lower().endswith(_EXTENSIONS):
                        target = dest_dir / name
            if target is None:
                raise RuntimeError(f"No SoundFont found in the {spec.label} download")
        else:
            target = dest_dir / spec.filename
            shutil.move(str(part), target)
    (dest_dir / f"{target.name}.ATTRIBUTION.txt").write_text(spec.attribution + "\n")
    return target


def download_default_soundfont(dest_dir: Path | None = None, url: str | None = None) -> Path:
    """Download the default piano SoundFont (used by ``keyfall --download-soundfont``)."""
    return download(PIANO_DOWNLOAD, dest_dir, url=url)


@dataclass
class DownloadJob:
    spec: SoundFontDownload
    status: str = "downloading"  # downloading | done | error
    fraction: float = 0.0
    path: Path | None = None
    error: str = ""
    applied: bool = False  # loaded into the audio engine yet


class SoundFontDownloader:
    """Runs downloads on background threads so the UI keeps drawing."""

    def __init__(self, download_fn=download, dest_dir: Path | None = None) -> None:
        self._download = download_fn
        self._dest_dir = dest_dir
        self.jobs: dict[str, DownloadJob] = {}

    def start(self, spec: SoundFontDownload) -> DownloadJob:
        job = self.jobs.get(spec.key)
        if job is not None and job.status == "downloading":
            return job
        job = self.jobs[spec.key] = DownloadJob(spec)

        def progress(done: int, total: int) -> None:
            job.fraction = min(1.0, done / total) if total else 0.0

        def run() -> None:
            try:
                job.path = self._download(spec, self._dest_dir, progress)
                job.fraction = 1.0
                job.status = "done"
            except Exception as exc:
                job.error = str(exc) or type(exc).__name__
                job.status = "error"

        threading.Thread(target=run, name=f"download-{spec.key}", daemon=True).start()
        return job

    def finished_unapplied(self) -> list[DownloadJob]:
        return [j for j in self.jobs.values() if j.status == "done" and not j.applied]
