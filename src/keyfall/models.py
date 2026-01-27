"""Core data models shared across the engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class HitGrade(Enum):
    PERFECT = auto()
    GOOD = auto()
    OK = auto()
    MISS = auto()


class Hand(Enum):
    LEFT = auto()
    RIGHT = auto()
    BOTH = auto()


@dataclass
class NoteEvent:
    """A single note in a song or from player input."""

    pitch: int  # MIDI note number 0-127
    start_time: float  # seconds from song start
    duration: float  # seconds
    velocity: int = 80
    hand: Hand = Hand.BOTH
    track: int = 0


@dataclass
class TempoChange:
    time: float  # seconds
    bpm: float


@dataclass
class TimeSignature:
    time: float  # seconds
    numerator: int
    denominator: int


@dataclass
class Song:
    """Parsed representation of a MIDI/MusicXML file."""

    title: str = "Untitled"
    notes: list[NoteEvent] = field(default_factory=list)
    tempo_changes: list[TempoChange] = field(default_factory=list)
    time_signatures: list[TimeSignature] = field(default_factory=list)
    ticks_per_beat: int = 480
    duration: float = 0.0  # total length in seconds


@dataclass
class HitResult:
    expected: NoteEvent
    played_pitch: int | None
    grade: HitGrade
    timing_offset_ms: float  # negative = early, positive = late


@dataclass
class SessionStats:
    song_title: str = ""
    total_notes: int = 0
    perfect: int = 0
    good: int = 0
    ok: int = 0
    missed: int = 0
    max_streak: int = 0
    accuracy_pct: float = 0.0
