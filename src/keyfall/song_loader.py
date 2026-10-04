"""Load MIDI and MusicXML files into the Song model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

import mido

from keyfall.models import Hand, NoteEvent, Song, TempoChange


class HandSplitStrategy(Enum):
    """Strategy for assigning notes to left/right hands."""
    AUTO = auto()        # Infer from track names, instruments, and pitch (default)
    BY_TRACK = auto()    # Track 0 = right, track 1 = left
    BY_PITCH = auto()    # Split at middle C (MIDI 60): >= 60 right, < 60 left
    BY_CHANNEL = auto()  # Channel 0 = right, channel 1 = left (for Type 0 MIDI)


class SongLoadError(Exception):
    """Raised when a song file cannot be parsed."""


MIDDLE_C = 60
DRUM_CHANNEL = 9  # GM percussion (channel 10, zero-indexed)
_PIANO_PROGRAMS = range(0, 8)  # GM programs 1-8: acoustic/electric pianos, harpsichord, clavinet
_PIANO_NAME_HINTS = ("piano", "keys", "keyboard")
_LEFT_NAME_HINTS = ("left", "lh", "l.h.", "bass")
_RIGHT_NAME_HINTS = ("right", "rh", "r.h.", "treble", "melody", "lead")


def load_song(
    file_path: str | Path,
    hand_split: HandSplitStrategy = HandSplitStrategy.AUTO,
) -> Song:
    """Load a MIDI or MusicXML file and return a Song.

    Args:
        file_path: Path to a .mid, .midi, .xml, .mxl, or .musicxml file.
        hand_split: Strategy for assigning notes to hands.

    Raises:
        SongLoadError: If the file cannot be parsed.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    try:
        if suffix in (".mid", ".midi"):
            return _load_midi(path, hand_split)
        elif suffix in (".xml", ".mxl", ".musicxml"):
            return _load_musicxml(path)
        else:
            raise SongLoadError(f"Unsupported file format: {path.suffix}")
    except SongLoadError:
        raise
    except Exception as exc:
        raise SongLoadError(f"Failed to load {path.name}: {exc}") from exc


@dataclass
class _TrackInfo:
    index: int
    name: str = ""
    program: int | None = None
    notes: list[tuple[NoteEvent, int]] = field(default_factory=list)  # (note, channel)

    @property
    def mean_pitch(self) -> float:
        return sum(n.pitch for n, _ in self.notes) / len(self.notes)

    @property
    def is_piano(self) -> bool:
        lowered = self.name.lower()
        if any(hint in lowered for hint in _PIANO_NAME_HINTS):
            return True
        return self.program is not None and self.program in _PIANO_PROGRAMS


def _name_matches(name: str, hints: tuple[str, ...]) -> bool:
    words = name.lower().replace("-", " ").replace("_", " ").split()
    return any(hint in words for hint in hints)


def _by_pitch(pitch: int) -> Hand:
    return Hand.RIGHT if pitch >= MIDDLE_C else Hand.LEFT


def _assign_hand(
    pitch: int, track_idx: int, channel: int, strategy: HandSplitStrategy
) -> Hand:
    if strategy == HandSplitStrategy.BY_PITCH:
        return _by_pitch(pitch)
    elif strategy == HandSplitStrategy.BY_CHANNEL:
        return Hand.LEFT if channel % 2 == 1 else Hand.RIGHT
    else:  # BY_TRACK
        return Hand.LEFT if track_idx % 2 == 1 else Hand.RIGHT


def _infer_hands(tracks: list[_TrackInfo]) -> None:
    """Assign hands in place for the AUTO strategy; drops tracks nobody plays.

    1. If any tracks are pianos, keep only those (drop band/backing parts).
    2. Tracks named like a hand ("RH", "Left", "Bass", ...) take that hand.
    3. Two tracks, one named for a hand: the other takes the opposite hand.
    4. Two unnamed tracks: higher average pitch is the right hand.
    5. Anything else (one track, or 3+): split each note at middle C.
    """
    pianos = [t for t in tracks if t.is_piano]
    if pianos and len(pianos) < len(tracks):
        tracks[:] = pianos

    unassigned: list[_TrackInfo] = []
    named_hands: set[Hand] = set()
    for track in tracks:
        if _name_matches(track.name, _LEFT_NAME_HINTS):
            hand = Hand.LEFT
        elif _name_matches(track.name, _RIGHT_NAME_HINTS):
            hand = Hand.RIGHT
        else:
            unassigned.append(track)
            continue
        named_hands.add(hand)
        for note, _ in track.notes:
            note.hand = hand

    if len(tracks) == 2 and len(unassigned) == 1 and len(named_hands) == 1:
        # One track is named for a hand; the other takes the opposite hand.
        other = Hand.RIGHT if Hand.LEFT in named_hands else Hand.LEFT
        for note, _ in unassigned[0].notes:
            note.hand = other
    elif len(unassigned) == 2 and len(tracks) == 2:
        low, high = sorted(unassigned, key=lambda t: t.mean_pitch)
        for track, hand in ((low, Hand.LEFT), (high, Hand.RIGHT)):
            for note, _ in track.notes:
                note.hand = hand
    else:
        for track in unassigned:
            for note, _ in track.notes:
                note.hand = _by_pitch(note.pitch)


def _tempo_map(mid: mido.MidiFile) -> list[tuple[int, int]]:
    """Collect (abs_tick, tempo) from every track; tempo applies song-wide."""
    changes: list[tuple[int, int]] = []
    for track in mid.tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type == "set_tempo":
                changes.append((tick, msg.tempo))
    changes.sort(key=lambda c: c[0])
    if not changes or changes[0][0] != 0:
        changes.insert(0, (0, 500_000))  # default 120 BPM
    return changes


def _ticks_to_seconds(tick: int, tempo_map: list[tuple[int, int]], tpb: int) -> float:
    seconds = 0.0
    prev_tick, prev_tempo = tempo_map[0]
    for change_tick, tempo in tempo_map[1:]:
        if change_tick >= tick:
            break
        seconds += mido.tick2second(change_tick - prev_tick, tpb, prev_tempo)
        prev_tick, prev_tempo = change_tick, tempo
    return seconds + mido.tick2second(tick - prev_tick, tpb, prev_tempo)


def _load_midi(path: Path, hand_split: HandSplitStrategy = HandSplitStrategy.AUTO) -> Song:
    mid = mido.MidiFile(str(path))
    tpb = mid.ticks_per_beat
    song = Song(title=path.stem, ticks_per_beat=tpb)

    tempos = _tempo_map(mid)
    for tick, tempo in tempos:
        song.tempo_changes.append(
            TempoChange(time=_ticks_to_seconds(tick, tempos, tpb), bpm=mido.tempo2bpm(tempo))
        )

    tracks: list[_TrackInfo] = []
    for track_idx, track in enumerate(mid.tracks):
        info = _TrackInfo(index=track_idx, name=track.name or "")
        tick = 0
        pending: dict[tuple[int, int], tuple[int, int]] = {}  # (ch, pitch) -> (start_tick, vel)

        def close(key: tuple[int, int], end_tick: int) -> None:
            start_tick, vel = pending.pop(key)
            start = _ticks_to_seconds(start_tick, tempos, tpb)
            end = _ticks_to_seconds(end_tick, tempos, tpb)
            note = NoteEvent(
                pitch=key[1], start_time=start, duration=max(end - start, 0.01),
                velocity=vel, track=track_idx,
            )
            info.notes.append((note, key[0]))

        for msg in track:
            tick += msg.time
            if msg.type == "program_change" and info.program is None:
                info.program = msg.program
            elif msg.type in ("note_on", "note_off"):
                if msg.channel == DRUM_CHANNEL:
                    continue
                key = (msg.channel, msg.note)
                if key in pending:  # note_off, or retrigger of a held note
                    close(key, tick)
                if msg.type == "note_on" and msg.velocity > 0:
                    pending[key] = (tick, msg.velocity)
        for key in list(pending):  # notes left hanging at end of track
            close(key, tick)

        if info.notes:
            tracks.append(info)

    if hand_split == HandSplitStrategy.AUTO:
        _infer_hands(tracks)
    else:
        for info in tracks:
            for note, channel in info.notes:
                note.hand = _assign_hand(note.pitch, info.index, channel, hand_split)

    song.notes = sorted((n for t in tracks for n, _ in t.notes), key=lambda n: n.start_time)
    if song.notes:
        song.duration = max(n.start_time + n.duration for n in song.notes)
    return song


def _load_musicxml(path: Path) -> Song:
    from music21 import converter, note as m21note, tempo as m21tempo

    score = converter.parse(str(path))
    song = Song(title=path.stem)

    for mm in score.flatten().getElementsByClass(m21tempo.MetronomeMark):
        song.tempo_changes.append(TempoChange(time=float(mm.offset), bpm=mm.number))

    for part_idx, part in enumerate(score.parts):
        hand = Hand.RIGHT if part_idx == 0 else Hand.LEFT
        for n in part.flatten().notes:
            pitches = n.pitches if hasattr(n, "pitches") else [n.pitch]
            for p in pitches:
                song.notes.append(
                    NoteEvent(
                        pitch=p.midi,
                        start_time=float(n.offset),
                        duration=float(n.duration.quarterLength),
                        velocity=n.volume.velocity or 80,
                        hand=hand,
                        track=part_idx,
                    )
                )

    song.notes.sort(key=lambda n: n.start_time)
    if song.notes:
        last = song.notes[-1]
        song.duration = last.start_time + last.duration
    return song
