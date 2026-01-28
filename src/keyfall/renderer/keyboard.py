"""Render the piano keyboard at the bottom of the screen."""

from __future__ import annotations

import pygame

from keyfall.config import MIDI_NOTE_MAX, MIDI_NOTE_MIN, WINDOW_HEIGHT, WINDOW_WIDTH
from keyfall.renderer.colors import BLACK_KEY, NOTE_PERFECT, WHITE_KEY

KEYBOARD_HEIGHT = 120
KEYBOARD_Y = WINDOW_HEIGHT - KEYBOARD_HEIGHT

# Which MIDI pitches are black keys (within an octave)
_BLACK_OFFSETS = {1, 3, 6, 8, 10}


def is_black_key(pitch: int) -> bool:
    return (pitch % 12) in _BLACK_OFFSETS


def _white_key_count() -> int:
    return sum(1 for p in range(MIDI_NOTE_MIN, MIDI_NOTE_MAX + 1) if not is_black_key(p))


def key_x_position(pitch: int) -> float:
    """Return the x center of a given MIDI pitch on the rendered keyboard."""
    white_w = WINDOW_WIDTH / _white_key_count()
    white_idx = 0
    for p in range(MIDI_NOTE_MIN, pitch):
        if not is_black_key(p):
            white_idx += 1

    if is_black_key(pitch):
        # Match render loop: bx = wx - bw/2 - white_w*0.15, center = bx + bw/2
        bw = white_w * 0.6
        bx = white_idx * white_w - bw / 2 - white_w * 0.15
        return bx + bw / 2
    return white_idx * white_w + white_w / 2


def key_width(pitch: int) -> float:
    white_w = WINDOW_WIDTH / _white_key_count()
    return white_w * 0.6 if is_black_key(pitch) else white_w


def render_keyboard(surface: pygame.Surface, pressed: set[int]) -> None:
    """Draw an 88-key piano keyboard along the bottom of the screen."""
    white_w = WINDOW_WIDTH / _white_key_count()
    # White keys first
    wx = 0.0
    for p in range(MIDI_NOTE_MIN, MIDI_NOTE_MAX + 1):
        if not is_black_key(p):
            color = NOTE_PERFECT if p in pressed else WHITE_KEY
            rect = pygame.Rect(int(wx), KEYBOARD_Y, int(white_w) - 1, KEYBOARD_HEIGHT)
            pygame.draw.rect(surface, color, rect)
            wx += white_w

    # Black keys on top
    wx = 0.0
    for p in range(MIDI_NOTE_MIN, MIDI_NOTE_MAX + 1):
        if not is_black_key(p):
            wx += white_w
        else:
            bw = white_w * 0.6
            bx = wx - bw / 2 - white_w * 0.15
            color = NOTE_PERFECT if p in pressed else BLACK_KEY
            rect = pygame.Rect(int(bx), KEYBOARD_Y, int(bw), int(KEYBOARD_HEIGHT * 0.6))
            pygame.draw.rect(surface, color, rect)
