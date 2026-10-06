"""SoundFont downloads from Settings: verified, cancellable, background, applied live."""

import hashlib
import io
import tarfile
import time
from dataclasses import replace

import pygame
import pytest

from keyfall import accessibility, settings, soundfont
from keyfall.soundfont import (
    GM_DOWNLOAD,
    PIANO_DOWNLOAD,
    DownloadCancelledError,
    SoundFontDownloader,
    download,
    installed_path,
)
from keyfall.ui_state import UIState

PAYLOAD = b"RIFF fake sf3 data " * 5000


def _file_spec(tmp_path, spec=GM_DOWNLOAD, data=PAYLOAD, archive=False):
    src = tmp_path / "server" / ("pack.tar.bz2" if archive else spec.filename)
    src.parent.mkdir(exist_ok=True)
    if archive:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:bz2") as tar:
            for name, content in ((f"pkg/{spec.filename}", data), ("pkg/readme.txt", b"hi")):
                info = tarfile.TarInfo(name)
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
        src.write_bytes(buf.getvalue())
    else:
        src.write_bytes(data)
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    return replace(spec, url=src.as_uri(), sha256=sha)


def test_download_verifies_and_installs_with_attribution(tmp_path):
    dest = tmp_path / "fonts"
    seen = []
    path = download(_file_spec(tmp_path), dest, progress=lambda d, t: seen.append(d))
    assert path == dest / "MuseScore_General.sf3" and path.read_bytes() == PAYLOAD
    assert seen and seen[-1] == len(PAYLOAD)
    assert "MIT" in (dest / "MuseScore_General.sf3.ATTRIBUTION.txt").read_text()
    assert installed_path(GM_DOWNLOAD, dest) == path


def test_checksum_mismatch_leaves_nothing_behind(tmp_path):
    spec = replace(_file_spec(tmp_path), sha256="0" * 64)
    dest = tmp_path / "fonts"
    with pytest.raises(RuntimeError, match="Checksum"):
        download(spec, dest)
    assert list(dest.iterdir()) == []


def test_cancel_leaves_nothing_behind(tmp_path):
    dest = tmp_path / "fonts"
    with pytest.raises(DownloadCancelledError):
        download(_file_spec(tmp_path), dest, progress=lambda d, t: False)
    assert list(dest.iterdir()) == []


def test_archive_download_extracts_the_soundfont(tmp_path):
    spec = _file_spec(tmp_path, PIANO_DOWNLOAD, archive=True)
    path = download(spec, tmp_path / "fonts")
    assert path.name == PIANO_DOWNLOAD.filename and path.read_bytes() == PAYLOAD


class FakeAudio:
    def __init__(self):
        self.loaded = []

    def load_soundfont(self, path):
        self.loaded.append(("main", path.name))

    def load_gm_soundfont(self, path):
        self.loaded.append(("gm", path.name))


def _wait(job):
    for _ in range(200):
        if job.status != "downloading":
            return
        time.sleep(0.01)


def test_background_download_is_applied_to_running_engine(tmp_path):
    spec = _file_spec(tmp_path)
    ui = UIState(persist=False,
                 downloader=SoundFontDownloader(dest_dir=tmp_path / "fonts"))
    job = ui.downloader.start(spec)
    _wait(job)
    assert job.status == "done" and job.fraction == 1.0
    audio = FakeAudio()
    assert ui.apply_downloads(audio) == ["Instrument sounds installed and in use"]
    assert audio.loaded == [("gm", "MuseScore_General.sf3")]
    assert ui.apply_downloads(audio) == []  # only once


def test_failed_download_reports_error(tmp_path):
    spec = replace(GM_DOWNLOAD, url=(tmp_path / "missing.sf3").as_uri())
    downloader = SoundFontDownloader(dest_dir=tmp_path / "fonts")
    job = downloader.start(spec)
    _wait(job)
    assert job.status == "error" and job.error


def test_settings_download_button(tmp_path, monkeypatch):
    from keyfall.views.base import ViewContext, ViewManager
    from keyfall.views.settings_view import ROW_GM, ROW_PIANO, SettingsView

    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    monkeypatch.setattr(accessibility, "_SETTINGS_PATH", tmp_path / "s.json")
    monkeypatch.setattr(soundfont, "user_soundfont_dir", lambda: tmp_path / "fonts")
    pygame.init()
    gm_spec = _file_spec(tmp_path)

    def fake_download(spec, dest_dir, progress):
        return download(gm_spec if spec.key == "gm" else spec, tmp_path / "fonts", progress)

    ui = UIState(persist=False, downloader=SoundFontDownloader(fake_download))
    audio = FakeAudio()
    ctx = ViewContext(screen_size=(1280, 720), midi_input=None, audio=audio, progress=None,
                      ui=ui)
    vm = ViewManager(ctx)
    vm.register(SettingsView)
    vm.push("settings")
    view = vm.active_view
    assert view._rows()[ROW_GM].value == "Download · 40 MB"
    view._selected = ROW_GM
    vm.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""))
    _wait(ui.downloader.jobs["gm"])
    vm.update(0.016)
    assert audio.loaded == [("gm", "MuseScore_General.sf3")]
    assert view._rows()[ROW_GM].value == "Installed"
    assert view._rows()[ROW_PIANO].value.startswith("Download")
    vm.draw(pygame.Surface((1280, 720)))
