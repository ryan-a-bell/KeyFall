"""Free play sandbox — no song, just play and hear audio with chord detection."""

from __future__ import annotations

import time

import pygame

from keyfall.free_play import FreePlayMode, export_midi
from keyfall.renderer.skins.frames import FreePlayFrame
from keyfall.views.base import ViewAction, ViewContext


class FreePlayView:
    name = "freeplay"
    display_name = "Free Play"

    def __init__(self) -> None:
        self._context: ViewContext | None = None
        self._mode: FreePlayMode | None = None
        self._pressed: set[int] = set()
        self._chord_history: list[str] = []

    def on_enter(self, context: ViewContext) -> None:
        self._context = context
        self._pressed = set()
        self._chord_history = []
        self._mode = FreePlayMode()

    def on_exit(self) -> None:
        if self._context and self._context.audio:
            self._context.audio.all_notes_off()

    def handle_event(self, event: pygame.event.Event) -> ViewAction | None:
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_ESCAPE:
            return ViewAction(kind="pop")
        elif event.key == pygame.K_r and self._mode is not None:
            if self._mode.is_recording:
                song = self._mode.stop_recording()
                if song.notes:
                    from pathlib import Path
                    out = Path.home() / ".keyfall" / "recordings" / f"rec_{int(time.time())}.mid"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    export_midi(song, out)
            else:
                self._mode.start_recording()

        return None

    def update(self, dt: float) -> ViewAction | None:
        if not self._context or not self._mode:
            return None

        # Poll MIDI and keyboard input
        mic = self._context.mic_input
        if getattr(mic, "connected", False):
            mic.set_expected(None)  # free play: unguided detection
        for source in (self._context.midi_input, self._context.keyboard_input,
                       mic if getattr(mic, "connected", False) else None):
            if source is None:
                continue
            while True:
                evt = source.poll()
                if evt is None:
                    break
                if evt.is_note_on:
                    self._pressed.add(evt.pitch)
                    self._mode.note_on(evt.pitch, evt.velocity)
                    if self._context.audio and getattr(source, "echo", True):
                        self._context.audio.note_on(evt.pitch, evt.velocity)
                else:
                    self._pressed.discard(evt.pitch)
                    self._mode.note_off(evt.pitch)
                    if self._context.audio:
                        self._context.audio.note_off(evt.pitch)

        # Chord history
        chord = self._mode.get_active_chord()
        if chord and (not self._chord_history or self._chord_history[-1] != chord):
            self._chord_history.append(chord)
            if len(self._chord_history) > 20:
                self._chord_history.pop(0)

        self._mode.update(dt)
        return None

    def draw(self, surface: pygame.Surface) -> None:
        if self._context is None:
            return
        self._context.skin.draw_freeplay(surface, FreePlayFrame(
            pressed=self._pressed,
            chord=self._mode.get_active_chord() if self._mode else None,
            chord_history=self._chord_history,
            recording=bool(self._mode and self._mode.is_recording),
        ))
