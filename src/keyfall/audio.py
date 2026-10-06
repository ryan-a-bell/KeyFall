"""Audio synthesis via FluidSynth + SoundFonts."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import fluidsynth

from keyfall.models import NoteEvent


def _audio_drivers() -> list[str]:
    """FluidSynth audio drivers to try for this platform, most preferred first."""
    if sys.platform == "linux":
        return ["pulseaudio", "pipewire", "alsa"]
    elif sys.platform == "darwin":
        return ["coreaudio"]
    elif sys.platform == "win32":
        return ["wasapi", "dsound"]
    return ["alsa"]


class AudioEngine:
    """Wraps FluidSynth for low-latency audio playback."""

    def __init__(self, soundfont_path: str | Path | None = None) -> None:
        self.fs = fluidsynth.Synth(gain=0.8)
        for driver in _audio_drivers():
            self.fs.start(driver=driver)
            if self.fs.audio_driver:
                break
        else:
            self.fs.delete()
            raise RuntimeError("No working audio output driver found")
        self._sfid: int | None = None
        self._extra_sfids: list[int] = []
        self.soundfont_path: Path | None = None
        self.gm_soundfont_path: Path | None = None
        self._pending_offs: list[tuple[float, int, int]] = []  # (off_time, pitch, channel)
        if soundfont_path:
            self.load_soundfont(soundfont_path)

    @property
    def has_soundfont(self) -> bool:
        return self._sfid is not None

    def status_text(self) -> str:
        """Short description for the menu, e.g. "Sound: YDP.sf2 + MuseScore_General.sf3"."""
        if self.soundfont_path is None:
            return "Sound: off (no SoundFont; download one in Settings)"
        text = f"Sound: {self.soundfont_path.name}"
        if self.gm_soundfont_path is not None:
            text += f" + {self.gm_soundfont_path.name}"
        return text

    def load_soundfont(self, path: str | Path) -> None:
        sfid = self.fs.sfload(str(path))
        if sfid < 0:
            raise RuntimeError(f"Could not load SoundFont: {path}")
        if self._sfid is not None:  # keep the previous one available for other instruments
            self._extra_sfids.append(self._sfid)
        self._sfid = sfid
        self.soundfont_path = Path(path)
        self.fs.program_select(0, self._sfid, 0, 0)

    def note_on(self, pitch: int, velocity: int = 80, channel: int = 0) -> None:
        self.fs.noteon(channel, pitch, velocity)

    def note_off(self, pitch: int, channel: int = 0) -> None:
        self.fs.noteoff(channel, pitch)

    def play_note_event(self, note: NoteEvent, channel: int = 0) -> None:
        self.fs.noteon(channel, note.pitch, note.velocity)
        off_time = time.time() + note.duration
        self._pending_offs.append((off_time, note.pitch, channel))

    def flush_pending_offs(self) -> None:
        """Call each frame to release notes whose duration has elapsed."""
        now = time.time()
        remaining: list[tuple[float, int, int]] = []
        for off_time, pitch, channel in self._pending_offs:
            if now >= off_time:
                self.fs.noteoff(channel, pitch)
            else:
                remaining.append((off_time, pitch, channel))
        self._pending_offs = remaining

    def load_gm_soundfont(self, path: str | Path) -> None:
        """Add a General MIDI SoundFont used for backing instruments and drums."""
        sfid = self.fs.sfload(str(path), 0)
        if sfid < 0:
            raise RuntimeError(f"Could not load SoundFont: {path}")
        self._extra_sfids.append(sfid)
        self.gm_soundfont_path = Path(path)
        if self._sfid is not None:  # keep the main piano on channel 0
            self.fs.program_select(0, self._sfid, 0, 0)

    def set_instrument(self, channel: int, program: int, bank: int = 0) -> bool:
        """Select a GM program (bank 128 = drum kits) from whichever SoundFont has it.

        Returns False and falls back to the main piano if no loaded SoundFont
        has the preset.
        """
        for sfid in ([self._sfid] if self._sfid is not None else []) + self._extra_sfids:
            if self.fs.sfpreset_name(sfid, bank, program) is not None:
                self.fs.program_select(channel, sfid, bank, program)
                return True
        if self._sfid is not None:
            self.fs.program_select(channel, self._sfid, 0, 0)
        return False

    def set_volume(self, channel: int, volume: float) -> None:
        """Set per-channel volume (0.0 to 1.0) via MIDI CC7."""
        cc_value = max(0, min(127, int(volume * 127)))
        self.fs.cc(channel, 7, cc_value)

    def all_notes_off(self) -> None:
        for ch in range(16):
            for pitch in range(128):
                self.fs.noteoff(ch, pitch)
        self._pending_offs.clear()

    def shutdown(self) -> None:
        self.all_notes_off()
        self.fs.delete()
