"""Simplified sheet music notation rendering."""

from __future__ import annotations

import pygame

from keyfall.models import HitGrade, NoteEvent, Song
from keyfall.renderer.colors import (
    HUD_TEXT,
    NOTE_GOOD,
    NOTE_MISS,
    NOTE_PERFECT,
)

# Staff layout constants
_STAFF_LINE_COLOR = (80, 80, 100)
_CURSOR_COLOR = (255, 220, 60)
_LEDGER_COLOR = (60, 60, 80)
_LINE_SPACING = 10  # pixels between staff lines
_STAFF_GAP = 40  # gap between treble and bass staves
_PIXELS_PER_SECOND = 120  # horizontal scroll speed
_CURSOR_X_RATIO = 0.3  # cursor position as fraction of width

# C D E F G A B diatonic offsets from C within octave
_DIATONIC_OFFSETS = {0: 0, 2: 1, 4: 2, 5: 3, 7: 4, 9: 5, 11: 6}


def _pitch_to_staff_position(pitch: int) -> int:
    """Convert MIDI pitch to diatonic staff position relative to middle C (0).

    Middle C = 0, D4 = 1, E4 = 2, ... B4 = 6, C5 = 7, etc.
    B3 = -1, A3 = -2, etc.
    """
    octave = (pitch // 12) - 5  # octave relative to C4
    note_in_octave = pitch % 12
    # Find nearest diatonic note
    for midi_offset in (0, -1, 1):
        adjusted = (note_in_octave + midi_offset) % 12
        if adjusted in _DIATONIC_OFFSETS:
            return octave * 7 + _DIATONIC_OFFSETS[adjusted]
    return octave * 7


def _is_accidental(pitch: int) -> bool:
    return (pitch % 12) in {1, 3, 6, 8, 10}


def render_notation(
    surface: pygame.Surface,
    song: Song,
    playback_position: float,
    x: int = 0,
    y: int = 0,
    width: int = 400,
    height: int = 200,
    hit_results: dict[int, HitGrade] | None = None,
) -> None:
    """Render a simplified staff notation view with scrolling playback cursor.

    Args:
        surface: Target surface.
        song: The song to render.
        playback_position: Current time in seconds.
        x, y, width, height: Bounding rectangle.
        hit_results: Map of note index -> HitGrade for coloring played notes.
    """
    if hit_results is None:
        hit_results = {}

    clip_rect = pygame.Rect(x, y, width, height)
    surface.set_clip(clip_rect)

    # Vertical layout
    center_y = y + height // 2
    treble_bottom = center_y - _STAFF_GAP // 2  # bottom line of treble staff
    bass_top = center_y + _STAFF_GAP // 2  # top line of bass staff

    # Draw treble staff (5 lines, bottom to top)
    for i in range(5):
        ly = treble_bottom - i * _LINE_SPACING
        pygame.draw.line(surface, _STAFF_LINE_COLOR, (x, ly), (x + width, ly))

    # Draw bass staff (5 lines, top to bottom)
    for i in range(5):
        ly = bass_top + i * _LINE_SPACING
        pygame.draw.line(surface, _STAFF_LINE_COLOR, (x, ly), (x + width, ly))

    # Draw playback cursor
    cursor_x = x + int(width * _CURSOR_X_RATIO)
    pygame.draw.line(surface, _CURSOR_COLOR, (cursor_x, y + 10), (cursor_x, y + height - 10), 2)

    # Visible time window
    left_time = playback_position - (_CURSOR_X_RATIO * width / _PIXELS_PER_SECOND)
    right_time = playback_position + ((1.0 - _CURSOR_X_RATIO) * width / _PIXELS_PER_SECOND)

    # Render notes
    for idx, note in enumerate(song.notes):
        if note.start_time > right_time:
            break
        if note.start_time + note.duration < left_time:
            continue

        note_x = cursor_x + int((note.start_time - playback_position) * _PIXELS_PER_SECOND)
        if note_x < x - 20 or note_x > x + width + 20:
            continue

        staff_pos = _pitch_to_staff_position(note.pitch)

        # Y position: treble for pitch >= 60, bass otherwise
        half_space = _LINE_SPACING // 2
        if note.pitch >= 60:
            # Treble bottom line = E4 (staff_pos=2)
            note_y = treble_bottom - (staff_pos - 2) * half_space
        else:
            # Bass top line = G3 (staff_pos=-3 from C4)
            note_y = bass_top - (staff_pos - (-3)) * half_space

        # Ledger lines
        if note.pitch >= 60 and staff_pos <= 1:
            ledger_y = treble_bottom + _LINE_SPACING
            while ledger_y >= note_y - 1:
                if ledger_y > treble_bottom:
                    pygame.draw.line(surface, _LEDGER_COLOR,
                                     (note_x - 8, ledger_y), (note_x + 8, ledger_y))
                ledger_y -= _LINE_SPACING
        elif note.pitch < 60 and staff_pos >= -2:
            ledger_y = bass_top - _LINE_SPACING
            while ledger_y <= note_y + 1:
                if ledger_y < bass_top:
                    pygame.draw.line(surface, _LEDGER_COLOR,
                                     (note_x - 8, ledger_y), (note_x + 8, ledger_y))
                ledger_y += _LINE_SPACING

        # Note color
        if idx in hit_results:
            grade = hit_results[idx]
            if grade == HitGrade.PERFECT:
                color = NOTE_PERFECT
            elif grade == HitGrade.GOOD:
                color = NOTE_GOOD
            elif grade == HitGrade.MISS:
                color = NOTE_MISS
            else:
                color = HUD_TEXT
        elif note.start_time < playback_position:
            color = (100, 100, 120)
        else:
            color = HUD_TEXT

        # Note head (filled for quarter or shorter, open for half+)
        radius = 5
        filled = note.duration <= 1.0
        pygame.draw.circle(surface, color, (note_x, int(note_y)), radius, 0 if filled else 1)

        # Stem
        stem_dir = -1 if staff_pos > 0 else 1
        stem_x = note_x + (radius if stem_dir == -1 else -radius)
        stem_end_y = int(note_y) + stem_dir * 30
        pygame.draw.line(surface, color, (stem_x, int(note_y)), (stem_x, stem_end_y))

        # Accidental
        if _is_accidental(note.pitch):
            font = pygame.font.SysFont("monospace", 12)
            sharp_surf = font.render("#", True, color)
            surface.blit(sharp_surf, (note_x - radius - 10, int(note_y) - 6))

    surface.set_clip(None)
