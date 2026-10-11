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
    # Accompaniment that is heard but not played or scored (e.g. Suno backing stems)
    backing: list[NoteEvent] = field(default_factory=list)
    # GM program per backing track (NoteEvent.track); PERCUSSION = drum kit
    backing_programs: dict[int, int] = field(default_factory=dict)
    # SHA-256 of the file it was loaded from ("" if unknown); identifies it across devices
    source_hash: str = ""


PERCUSSION = -1  # backing_programs value meaning "GM drum kit on channel 10"


@dataclass
class HitResult:
    expected: NoteEvent
    played_pitch: int | None
    grade: HitGrade
    timing_offset_ms: float  # negative = early, positive = late


@dataclass
class SessionStats:
    song_title: str = ""
    song_hash: str = ""  # Song.source_hash
    total_notes: int = 0
    perfect: int = 0
    good: int = 0
    ok: int = 0
    missed: int = 0
    max_streak: int = 0
    accuracy_pct: float = 0.0
