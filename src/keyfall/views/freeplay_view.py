"""Free play sandbox — no song, just play and hear audio with chord detection."""

from __future__ import annotations

import time

import pygame

from keyfall.renderer.colors import BG, HUD_TEXT, NOTE_PERFECT, NOTE_RIGHT_HAND
from keyfall.renderer.keyboard import render_keyboard
from keyfall.views.base import ViewAction, ViewContext

# Chord templates: interval set from root -> chord name suffix
_CHORD_TEMPLATES: list[tuple[frozenset[int], str]] = [
    (frozenset({0, 4, 7}), ""),       # major
    (frozenset({0, 3, 7}), "m"),      # minor
    (frozenset({0, 3, 6}), "dim"),    # diminished
    (frozenset({0, 4, 8}), "aug"),    # augmented
    (frozenset({0, 4, 7, 10}), "7"),  # dominant 7th
    (frozenset({0, 4, 7, 11}), "maj7"),
    (frozenset({0, 3, 7, 10}), "m7"),
    (frozenset({0, 3, 6, 10}), "m7b5"),
    (frozenset({0, 3, 6, 9}), "dim7"),
    (frozenset({0, 4, 7, 11, 2}), "maj9"),
    (frozenset({0, 5, 7}), "sus4"),
    (frozenset({0, 2, 7}), "sus2"),
]

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _detect_chord(pitches: set[int]) -> str | None:
    """Detect chord name from a set of MIDI pitches."""
    if len(pitches) < 2:
        return None

    pitch_classes = frozenset(p % 12 for p in pitches)
    if len(pitch_classes) < 2:
        return None

    best_match: str | None = None
    best_score = 0

    for root in range(12):
        intervals = frozenset((pc - root) % 12 for pc in pitch_classes)
        for template, suffix in _CHORD_TEMPLATES:
            matched = len(intervals & template)
            unmatched = len(intervals - template)
            score = matched - unmatched
            if matched >= len(template) and score > best_score:
                best_score = score
                best_match = f"{_NOTE_NAMES[root]}{suffix}"

    return best_match


class FreePlayView:
    name = "freeplay"
    display_name = "Free Play"

    def __init__(self) -> None:
        self._context: ViewContext | None = None
        self._pressed: set[int] = set()
        self._chord: str | None = None
        self._chord_history: list[str] = []
        self._recording: bool = False
        self._record_buffer: list[tuple[int, int, float, bool]] = []
        self._record_start: float = 0.0
        self._font: pygame.font.Font | None = None
        self._chord_font: pygame.font.Font | None = None

    def on_enter(self, context: ViewContext) -> None:
        self._context = context
        self._font = pygame.font.SysFont("monospace", 20)
        self._chord_font = pygame.font.SysFont("monospace", 48)
        self._pressed = set()
        self._chord = None
        self._chord_history = []
        self._recording = False
        self._record_buffer = []

    def on_exit(self) -> None:
        if self._context and self._context.audio:
            self._context.audio.all_notes_off()

    def handle_event(self, event: pygame.event.Event) -> ViewAction | None:
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_ESCAPE:
            return ViewAction(kind="pop")
        elif event.key == pygame.K_r:
            if self._recording:
                self._recording = False
            else:
                self._recording = True
                self._record_buffer = []
                self._record_start = time.time()

        return None

    def update(self, dt: float) -> ViewAction | None:
        if not self._context:
            return None

        # Poll MIDI
        if self._context.midi_input:
            while True:
                evt = self._context.midi_input.poll()
                if evt is None:
                    break
                if evt.is_note_on:
                    self._pressed.add(evt.pitch)
                    if self._context.audio:
                        self._context.audio.note_on(evt.pitch, evt.velocity)
                    if self._recording:
                        self._record_buffer.append(
                            (evt.pitch, evt.velocity, time.time() - self._record_start, True)
                        )
                else:
                    self._pressed.discard(evt.pitch)
                    if self._context.audio:
                        self._context.audio.note_off(evt.pitch)
                    if self._recording:
                        self._record_buffer.append(
                            (evt.pitch, 0, time.time() - self._record_start, False)
                        )

        # Chord detection
        new_chord = _detect_chord(self._pressed)
        if new_chord and new_chord != self._chord:
            self._chord = new_chord
            self._chord_history.append(new_chord)
            if len(self._chord_history) > 20:
                self._chord_history.pop(0)
        elif not self._pressed:
            self._chord = None

        return None

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(BG)
        w, h = surface.get_size()

        # Title bar
        if self._font:
            title = self._font.render("Free Play", True, NOTE_PERFECT)
            surface.blit(title, (20, 15))

            if self._recording:
                elapsed = time.time() - self._record_start
                rec_text = self._font.render(
                    f"REC {elapsed:.1f}s", True, (220, 60, 60)
                )
                surface.blit(rec_text, (w - rec_text.get_width() - 20, 15))

        # Chord display
        if self._chord and self._chord_font:
            chord_surf = self._chord_font.render(self._chord, True, NOTE_RIGHT_HAND)
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
            notes_surf = self._font.render(note_str, True, HUD_TEXT)
            surface.blit(notes_surf, (20, 200))

        # Keyboard
        render_keyboard(surface, self._pressed)

        # Controls
        if self._font:
            hint = self._font.render("R: toggle recording | Esc: back to menu", True, (80, 80, 100))
            surface.blit(hint, (20, h - 150))
