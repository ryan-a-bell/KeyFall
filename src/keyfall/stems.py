"""Multi-stem songs: several per-instrument MIDI files played as one song.

Suno Studio can split a song into instrument stems and export each one as
MIDI. Put a song's stems in their own folder inside the songs directory::

    songs/Neon Rain/piano.mid
    songs/Neon Rain/bass.mid
    songs/Neon Rain/lead.mid
    songs/Neon Rain/drums.mid

Each stem gets a role (right hand, left hand, both hands, backing, or off).
Roles are guessed from file names and can be changed on the Stems screen;
choices are saved next to the stems in ``keyfall-stems.json``.

Stem MIDI exported from audio is a transcription, so an optional cleanup pass
removes ghost notes and merges double-triggered notes, and an optional grid
snap quantizes timing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from keyfall.models import PERCUSSION, Hand, NoteEvent, Song, TempoChange
from keyfall.song_loader import HandSplitStrategy, load_song

CONFIG_NAME = "keyfall-stems.json"
MIDI_SUFFIXES = (".mid", ".midi")
MIDDLE_C = 60

MIN_DURATION = 0.05  # seconds; shorter notes are transcription noise
MIN_VELOCITY = 12
MERGE_WINDOW = 0.04  # same pitch re-triggered within this many seconds = one note


class StemRole(Enum):
    RIGHT = "Right hand"
    LEFT = "Left hand"
    BOTH = "Both hands"
    BACKING = "Backing"
    OFF = "Off"


ROLE_ORDER = [StemRole.RIGHT, StemRole.LEFT, StemRole.BOTH, StemRole.BACKING, StemRole.OFF]
QUANTIZE_OPTIONS = [0, 8, 16]  # 0 = off, else grid of 1/8 or 1/16 notes

# (keywords, instrument label) checked in order against the lower-cased file name
_INSTRUMENTS: list[tuple[tuple[str, ...], str]] = [
    (("drum", "perc", "kick", "snare", "hat", "cymbal", "beat"), "Drums"),
    (("bass",), "Bass"),
    (("piano", "keys", "keyboard", "rhodes", "organ", "epiano"), "Piano"),
    (("vocal", "vox", "voice", "sing"), "Vocals"),
    (("lead", "melody", "flute", "violin", "sax", "trumpet", "whistle"), "Lead"),
    (("guitar", "gtr"), "Guitar"),
    (("string",), "Strings"),
    (("pad", "synth", "brass", "choir", "horn", "fx"), "Synth / pad"),
]


# General MIDI program used when a stem plays as backing
GM_PROGRAMS: dict[str, int] = {
    "Drums": PERCUSSION,
    "Bass": 33,  # Electric Bass (finger)
    "Piano": 0,  # Acoustic Grand Piano
    "Vocals": 53,  # Voice Oohs
    "Lead": 81,  # Lead 2 (sawtooth)
    "Guitar": 25,  # Acoustic Guitar (steel)
    "Strings": 48,  # String Ensemble 1
    "Synth / pad": 89,  # Pad 2 (warm)
    "Other": 0,
}
GM_NAMES: dict[int, str] = {
    PERCUSSION: "Drum kit", 0: "Grand piano", 25: "Steel guitar", 33: "Finger bass",
    48: "String ensemble", 53: "Voice oohs", 81: "Saw lead", 89: "Warm pad",
}


def guess_instrument(name: str) -> str:
    lowered = name.lower()
    for keywords, label in _INSTRUMENTS:
        if any(k in lowered for k in keywords):
            return label
    return "Other"


@dataclass
class Stem:
    path: Path
    notes: list[NoteEvent]
    instrument: str
    role: StemRole = StemRole.BACKING
    bpm: float = 120.0

    @property
    def name(self) -> str:
        return self.path.stem

    def label(self, song_title: str) -> str:
        """Display name without a repeated song title: "Neon Rain (Bass)" -> "Bass"."""
        name = self.name
        if song_title and name.lower().startswith(song_title.lower()):
            trimmed = name[len(song_title):].strip(" -_()[]")
            if trimmed:
                return trimmed
        return name

    @property
    def program(self) -> int:
        return GM_PROGRAMS.get(self.instrument, 0)

    @property
    def mean_pitch(self) -> float:
        return sum(n.pitch for n in self.notes) / len(self.notes) if self.notes else 0.0

    @property
    def pitch_range(self) -> tuple[int, int] | None:
        if not self.notes:
            return None
        return min(n.pitch for n in self.notes), max(n.pitch for n in self.notes)


def guess_roles(stems: list[Stem]) -> None:
    """Pick sensible default roles in place.

    - Empty stems are off; drums are backing (heard, never played).
    - A piano stem is played with both hands; everything else becomes backing.
    - Otherwise bass is the left hand and the lead/vocal line the right hand
      (or, with no obvious lead, the highest-pitched remaining stem).
    """
    for s in stems:
        s.role = StemRole.BACKING if s.notes else StemRole.OFF
    live = [s for s in stems if s.role != StemRole.OFF and s.instrument != "Drums"]
    piano = next((s for s in live if s.instrument == "Piano"), None)
    if piano:
        piano.role = StemRole.BOTH
        return
    bass = next((s for s in live if s.instrument == "Bass"), None)
    if bass:
        bass.role = StemRole.LEFT
    melodic = [s for s in live if s is not bass]
    lead = next((s for s in melodic if s.instrument in ("Lead", "Vocals")), None)
    if lead is None and melodic:
        lead = max(melodic, key=lambda s: s.mean_pitch)
    if lead:
        lead.role = StemRole.RIGHT
    if bass is None and lead is not None and len(live) == 1:
        lead.role = StemRole.BOTH  # a single melodic stem: split it across both hands


def cleanup(notes: list[NoteEvent]) -> list[NoteEvent]:
    """Remove ghost notes and merge double-triggered notes from transcribed MIDI."""
    kept: list[NoteEvent] = []
    last_by_pitch: dict[int, NoteEvent] = {}
    for n in sorted(notes, key=lambda n: (n.start_time, n.pitch)):
        if n.duration < MIN_DURATION or n.velocity < MIN_VELOCITY:
            continue
        prev = last_by_pitch.get(n.pitch)
        if prev is not None and n.start_time - prev.start_time <= MERGE_WINDOW:
            end = max(prev.start_time + prev.duration, n.start_time + n.duration)
            prev.duration = end - prev.start_time
            prev.velocity = max(prev.velocity, n.velocity)
            continue
        copy = NoteEvent(n.pitch, n.start_time, n.duration, n.velocity, n.hand, n.track)
        kept.append(copy)
        last_by_pitch[n.pitch] = copy
    return kept


def quantize(notes: list[NoteEvent], bpm: float, division: int) -> list[NoteEvent]:
    """Snap starts and ends to a 1/``division`` note grid (division 8 or 16)."""
    if division <= 0 or bpm <= 0:
        return notes
    grid = 60.0 / bpm * 4.0 / division
    out = []
    for n in notes:
        start = round(n.start_time / grid) * grid
        end = round((n.start_time + n.duration) / grid) * grid
        out.append(NoteEvent(n.pitch, start, max(grid, end - start), n.velocity, n.hand, n.track))
    return out


def is_stem_folder(path: Path) -> bool:
    return path.is_dir() and any(f.suffix.lower() in MIDI_SUFFIXES for f in path.iterdir())


@dataclass
class StemSet:
    folder: Path
    stems: list[Stem] = field(default_factory=list)
    clean: bool = True
    quantize_division: int = 0
    removed_notes: int = 0  # by the last cleanup pass

    @classmethod
    def load(cls, folder: str | Path) -> StemSet:
        folder = Path(folder)
        stems: list[Stem] = []
        files = sorted((f for f in folder.iterdir() if f.suffix.lower() in MIDI_SUFFIXES),
                       key=lambda f: f.name.lower())
        for f in files:
            try:
                song = load_song(f, HandSplitStrategy.BY_PITCH, keep_drums=True)
                notes = song.notes
                bpm = song.tempo_changes[0].bpm if song.tempo_changes else 120.0
            except Exception:
                notes, bpm = [], 120.0
            stems.append(Stem(path=f, notes=notes, instrument=guess_instrument(f.stem), bpm=bpm))
        stem_set = cls(folder=folder, stems=stems)
        guess_roles(stems)
        stem_set._apply_saved()
        return stem_set

    @property
    def config_path(self) -> Path:
        return self.folder / CONFIG_NAME

    def _apply_saved(self) -> None:
        try:
            data = json.loads(self.config_path.read_text())
        except Exception:
            return
        roles = data.get("roles", {}) if isinstance(data, dict) else {}
        for stem in self.stems:
            saved = roles.get(stem.path.name)
            if saved in StemRole.__members__:
                stem.role = StemRole[saved]
        self.clean = bool(data.get("cleanup", self.clean))
        q = data.get("quantize", 0)
        self.quantize_division = q if q in QUANTIZE_OPTIONS else 0

    def save(self) -> None:
        data = {
            "roles": {s.path.name: s.role.name for s in self.stems},
            "cleanup": self.clean,
            "quantize": self.quantize_division,
        }
        self.config_path.write_text(json.dumps(data, indent=2))

    def combine(self) -> Song:
        """Merge the stems into one Song on a shared timeline."""
        song = Song(title=self.folder.name)
        bpm = next((s.bpm for s in self.stems if s.role != StemRole.OFF and s.notes), 120.0)
        song.tempo_changes = [TempoChange(0.0, bpm)]
        removed = 0
        for index, stem in enumerate(self.stems):
            if stem.role == StemRole.OFF:
                continue
            notes = stem.notes
            if stem.role == StemRole.BACKING:
                song.backing_programs[index] = stem.program
            if self.clean and stem.instrument != "Drums":
                cleaned = cleanup(notes)
                removed += len(notes) - len(cleaned)
                notes = cleaned
            notes = quantize(notes, bpm, self.quantize_division)
            if self.quantize_division and self.clean and stem.instrument != "Drums":
                notes = cleanup(notes)  # snapping can create new duplicates
            for n in notes:
                note = NoteEvent(n.pitch, n.start_time, n.duration, n.velocity, n.hand, index)
                if stem.role == StemRole.BACKING:
                    note.hand = Hand.BOTH
                    song.backing.append(note)
                    continue
                if stem.role == StemRole.RIGHT:
                    note.hand = Hand.RIGHT
                elif stem.role == StemRole.LEFT:
                    note.hand = Hand.LEFT
                else:
                    note.hand = Hand.RIGHT if n.pitch >= MIDDLE_C else Hand.LEFT
                song.notes.append(note)
        self.removed_notes = removed
        song.notes.sort(key=lambda n: (n.start_time, n.pitch))
        song.backing.sort(key=lambda n: n.start_time)
        ends = [n.start_time + n.duration for n in song.notes + song.backing]
        song.duration = max(ends, default=0.0)
        return song
