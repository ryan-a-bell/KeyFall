"""Audio synthesis via FluidSynth + SoundFonts."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import fluidsynth

from keyfall.models import NoteEvent


def _detect_audio_driver() -> str:
    """Auto-detect the appropriate FluidSynth audio driver for the platform."""
    if sys.platform == "linux":
        return "pulseaudio"
    elif sys.platform == "darwin":
        return "coreaudio"
    elif sys.platform == "win32":
        return "dsound"
    return "alsa"


class AudioEngine:
    """Wraps FluidSynth for low-latency audio playback."""

    def __init__(self, soundfont_path: str | Path | None = None) -> None:
        self.fs = fluidsynth.Synth(gain=0.8)
        self.fs.start(driver=_detect_audio_driver())
        self._sfid: int | None = None
        self._pending_offs: list[tuple[float, int, int]] = []  # (off_time, pitch, channel)
        if soundfont_path:
            self.load_soundfont(soundfont_path)

    def load_soundfont(self, path: str | Path) -> None:
        self._sfid = self.fs.sfload(str(path))
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

    def set_instrument(self, channel: int, program: int) -> None:
        """Change the MIDI program (instrument) on a channel."""
        if self._sfid is not None:
            self.fs.program_select(channel, self._sfid, 0, program)

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
