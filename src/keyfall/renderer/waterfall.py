"""Falling-note waterfall visualization."""

from __future__ import annotations

import pygame

from keyfall.config import NOTE_FALL_SPEED
from keyfall.models import Hand, NoteEvent, Song
from keyfall.renderer.colors import NOTE_LEFT_HAND, NOTE_RIGHT_HAND
from keyfall.renderer.keyboard import KEYBOARD_Y, is_black_key, key_width, key_x_position


def render_waterfall(
    surface: pygame.Surface,
    song: Song,
    playback_position: float,
    look_ahead: float = 3.0,
) -> None:
    """Draw falling note bars above the keyboard."""
    for note in song.notes:
        dt = note.start_time - playback_position
        if dt > look_ahead:
            break
        if dt + note.duration < -0.5:
            continue

        _draw_note_bar(surface, note, playback_position, look_ahead)


def _draw_note_bar(
    surface: pygame.Surface,
    note: NoteEvent,
    position: float,
    look_ahead: float,
) -> None:
    dt = note.start_time - position
    pixels_per_sec = KEYBOARD_Y / look_ahead

    y_bottom = KEYBOARD_Y - dt * pixels_per_sec
    bar_h = max(note.duration * pixels_per_sec, 6)
    y_top = y_bottom - bar_h

    x_center = key_x_position(note.pitch)
    w = key_width(note.pitch) * 0.85
    x = x_center - w / 2

    color = NOTE_LEFT_HAND if note.hand == Hand.LEFT else NOTE_RIGHT_HAND

    rect = pygame.Rect(int(x), int(y_top), int(w), int(bar_h))
    pygame.draw.rect(surface, color, rect, border_radius=3)
