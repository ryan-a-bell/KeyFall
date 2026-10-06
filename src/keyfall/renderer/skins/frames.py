"""Plain data handed from views to skins each frame.

Views own game logic and fill these in; skins only read them and draw.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from keyfall.accessibility import NoteLabelMode
from keyfall.models import Hand, HitGrade, SessionStats, Song


def points(stats: SessionStats) -> int:
    """Display score used by the modern skins."""
    return stats.perfect * 300 + stats.good * 150 + stats.ok * 50


def grade_letter(accuracy_pct: float, total_notes: int) -> str:
    if total_notes == 0:
        return "–"
    for threshold, letter in ((95, "S"), (90, "A"), (80, "B"), (70, "C")):
        if accuracy_pct >= threshold:
            return letter
    return "D"


@dataclass
class PlayFrame:
    song: Song
    position: float
    pressed: set[int]
    stats: SessionStats
    streak: int = 0
    tempo_scale: float = 1.0
    wait_mode: bool = False
    paused: bool = False
    active_hand: Hand = Hand.BOTH
    mode: str = "Play"  # "Play" or "Practice"
    label_mode: NoteLabelMode = NoteLabelMode.NONE
    judgement: HitGrade | None = None
    judgement_age: float = 99.0  # seconds since the last judgement
    timing_offsets_ms: list[float] = field(default_factory=list)
    loop: tuple[int, int] | None = None  # active loop bars
    loop_count: int = 0
    show_notation: bool = False
    hit_results: dict | None = None
    hints: str = ""
    clock: float = 0.0  # seconds since the view opened (for animation)

    @property
    def progress(self) -> float:
        if self.song.duration <= 0:
            return 0.0
        return max(0.0, min(1.0, self.position / self.song.duration))


@dataclass
class MenuSong:
    title: str
    kind: str  # "MIDI", "MusicXML"
    best_accuracy: float | None = None


@dataclass
class SongDetails:
    duration: float
    note_count: int
    difficulty_level: int | None = None  # 1-18
    difficulty_label: str = ""


@dataclass
class MenuFrame:
    songs: list[MenuSong]
    selected: int
    modes: list[str]
    mode: int
    hand_split: str
    audio_status: str
    midi_status: str
    midi_connected: bool
    sound_ok: bool
    details: SongDetails | None = None
    output_status: str = "Off"
    output_connected: bool = False
    error: str = ""
    songs_dir: str = ""
    clock: float = 0.0


@dataclass
class SettingsRow:
    label: str
    value: str
    description: str
    adjustable: bool = True  # False for action rows like "Done"
    swatch: str = ""  # optional color key for the value: right, left, both, backing, off


@dataclass
class SettingsFrame:
    rows: list[SettingsRow]
    selected: int
    preview: object | None = None  # pygame.Surface
    theme_description: str = ""
    message: str = ""


@dataclass
class FreePlayFrame:
    pressed: set[int]
    chord: str | None
    chord_history: list[str]
    recording: bool
    label_mode: NoteLabelMode = NoteLabelMode.NOTE_NAME
    clock: float = 0.0


@dataclass
class StemsFrame:
    title: str
    rows: list[SettingsRow]
    selected: int
    song: Song | None = None  # combined result, for the piano-roll preview
    summary: list[str] = field(default_factory=list)
    message: str = ""
