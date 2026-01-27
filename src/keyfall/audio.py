"""Audio synthesis via FluidSynth + SoundFonts."""

from __future__ import annotations

from pathlib import Path

import fluidsynth

from keyfall.models import NoteEvent


class AudioEngine:
    """Wraps FluidSynth for low-latency audio playback."""

    def __init__(self, soundfont_path: str | Path | None = None) -> None:
        self.fs = fluidsynth.Synth(gain=0.8)
        self.fs.start(driver="alsa")  # platform-dependent; override as needed
        self._sfid: int | None = None
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

    def all_notes_off(self) -> None:
        for ch in range(16):
            for pitch in range(128):
                self.fs.noteoff(ch, pitch)

    def shutdown(self) -> None:
        self.all_notes_off()
        self.fs.delete()
