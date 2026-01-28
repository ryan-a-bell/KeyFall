"""Free play sandbox — no song, just play and hear audio with chord detection."""

from __future__ import annotations

import time

import pygame

from keyfall.free_play import FreePlayMode, export_midi
from keyfall.renderer import colors as colors_mod
from keyfall.renderer.keyboard import render_keyboard
from keyfall.views.base import ViewAction, ViewContext

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


class FreePlayView:
    name = "freeplay"
    display_name = "Free Play"

    def __init__(self) -> None:
        self._context: ViewContext | None = None
        self._mode: FreePlayMode | None = None
        self._pressed: set[int] = set()
        self._chord_history: list[str] = []
        self._font: pygame.font.Font | None = None
        self._chord_font: pygame.font.Font | None = None

    def on_enter(self, context: ViewContext) -> None:
        self._context = context
        self._font = pygame.font.SysFont("monospace", 20)
        self._chord_font = pygame.font.SysFont("monospace", 48)
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
        for source in (self._context.midi_input, self._context.keyboard_input):
            if source is None:
                continue
            while True:
                evt = source.poll()
                if evt is None:
                    break
                if evt.is_note_on:
                    self._pressed.add(evt.pitch)
                    self._mode.note_on(evt.pitch, evt.velocity)
                    if self._context.audio:
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
        surface.fill(colors_mod.BG)
        w, h = surface.get_size()

        # Title bar
        if self._font:
            title = self._font.render("Free Play", True, colors_mod.NOTE_PERFECT)
            surface.blit(title, (20, 15))

            if self._mode and self._mode.is_recording:
                rec_text = self._font.render("REC", True, (220, 60, 60))
                surface.blit(rec_text, (w - rec_text.get_width() - 20, 15))

        # Chord display
        chord = self._mode.get_active_chord() if self._mode else None
        if chord and self._chord_font:
            chord_surf = self._chord_font.render(chord, True, colors_mod.NOTE_RIGHT_HAND)
            surface.blit(chord_surf, (w // 2 - chord_surf.get_width() // 2, 80))

        # Chord history
        if self._font and self._chord_history:
            history_text = "  ".join(self._chord_history[-10:])
            hist_surf = self._font.render(history_text, True, (120, 120, 140))
            surface.blit(hist_surf, (20, 160))

        # Note names of currently held keys
        if self._font and self._pressed:
            names = sorted(self._pressed)
            note_str = ", ".join(f"{_NOTE_NAMES[p % 12]}{p // 12 - 1}" for p in names)
            notes_surf = self._font.render(note_str, True, colors_mod.HUD_TEXT)
            surface.blit(notes_surf, (20, 200))

        # Keyboard
        render_keyboard(surface, self._pressed)

        # Controls
        if self._font:
            hint = self._font.render("R: toggle recording | Esc: back to menu", True, (80, 80, 100))
            surface.blit(hint, (20, h - 150))
