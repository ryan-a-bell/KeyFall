"""Keyboard geometry, visible-note lookup, and note label text."""

from __future__ import annotations

from bisect import bisect_right

import pygame

from keyfall.accessibility import NoteLabelMode
from keyfall.config import MIDI_NOTE_MAX, MIDI_NOTE_MIN
from keyfall.models import Hand, NoteEvent, Song

_BLACK = {1, 3, 6, 8, 10}
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_SOLFEGE = ["Do", "Di", "Re", "Ri", "Mi", "Fa", "Fi", "Sol", "Si", "La", "Li", "Ti"]


def is_black(pitch: int) -> bool:
    return pitch % 12 in _BLACK


def note_name(pitch: int, octave: bool = True) -> str:
    name = NOTE_NAMES[pitch % 12]
    return f"{name}{pitch // 12 - 1}" if octave else name


def label_for(pitch: int, mode: NoteLabelMode) -> str:
    if mode == NoteLabelMode.NOTE_NAME:
        return NOTE_NAMES[pitch % 12]
    if mode == NoteLabelMode.SOLFEGE:
        return _SOLFEGE[pitch % 12]
    if mode == NoteLabelMode.MIDI_NUMBER:
        return str(pitch)
    return ""


class KeyLayout:
    """Pixel geometry for a keyboard spanning ``lo..hi`` across ``width`` pixels."""

    def __init__(self, lo: int, hi: int, x0: float, width: float, y: int, height: int) -> None:
        self.lo, self.hi, self.y, self.height = lo, hi, y, height
        whites = [p for p in range(lo, hi + 1) if not is_black(p)]
        self.white_w = width / max(1, len(whites))
        self.black_w = self.white_w * 0.6
        self._x: dict[int, float] = {}
        i = 0
        for p in range(lo, hi + 1):
            if is_black(p):
                self._x[p] = x0 + i * self.white_w - self.black_w / 2
            else:
                self._x[p] = x0 + i * self.white_w
                i += 1

    def contains(self, pitch: int) -> bool:
        return self.lo <= pitch <= self.hi

    def key_rect(self, pitch: int) -> pygame.Rect:
        x = self._x[pitch]
        if is_black(pitch):
            return pygame.Rect(round(x), self.y, round(self.black_w), int(self.height * 0.62))
        return pygame.Rect(round(x), self.y, round(x + self.white_w) - round(x), self.height)

    def lane(self, pitch: int) -> tuple[float, float]:
        """(x, width) of the falling-note column for a pitch."""
        x = self._x[pitch]
        if is_black(pitch):
            return x + 1, self.black_w - 2
        return x + 2, self.white_w - 4

    def x_of(self, pitch: int) -> float:
        return self._x[pitch]


def fit_range(song: Song | None, min_span: int = 36) -> tuple[int, int]:
    """Smallest keyboard (white key to white key) covering the song, at least ``min_span``."""
    if song is None or not song.notes:
        return 36, 96
    lo = min(n.pitch for n in song.notes) - 2
    hi = max(n.pitch for n in song.notes) + 2
    while hi - lo < min_span:
        lo -= 1
        hi += 1
    lo, hi = max(MIDI_NOTE_MIN, lo), min(MIDI_NOTE_MAX, hi)
    while is_black(lo) and lo > MIDI_NOTE_MIN:
        lo -= 1
    while is_black(hi) and hi < MIDI_NOTE_MAX:
        hi += 1
    return lo, hi


class NoteIndex:
    """Fast lookup of notes overlapping a time window (songs are sorted by start)."""

    def __init__(self, song: Song, notes: list[NoteEvent] | None = None) -> None:
        self.song = song
        self.notes = song.notes if notes is None else notes
        self.starts = [n.start_time for n in self.notes]
        self.max_dur = max((n.duration for n in self.notes), default=0.0)

    def window(self, t0: float, t1: float) -> list[NoteEvent]:
        """Notes with any part in [t0, t1]."""
        notes = self.notes
        i = bisect_right(self.starts, t0 - self.max_dur)
        j = bisect_right(self.starts, t1)
        return [n for n in notes[i:j] if n.start_time + n.duration >= t0]

    def hand_at(self, pitch: int, t: float) -> Hand:
        """Which hand owns ``pitch`` around time ``t`` (falls back to a middle-C split)."""
        for n in self.window(t - 0.25, t + 0.25):
            if n.pitch == pitch:
                return n.hand
        return Hand.RIGHT if pitch >= 60 else Hand.LEFT


def beat_seconds(song: Song) -> float:
    bpm = song.tempo_changes[0].bpm if song.tempo_changes else 120.0
    return 60.0 / bpm if bpm > 0 else 0.5


def beats_per_bar(song: Song) -> int:
    return song.time_signatures[0].numerator if song.time_signatures else 4
