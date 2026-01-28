"""Load MIDI and MusicXML files into the Song model."""

from __future__ import annotations

from enum import Enum, auto
from pathlib import Path

import mido

from keyfall.models import Hand, NoteEvent, Song, TempoChange


class HandSplitStrategy(Enum):
    """Strategy for assigning notes to left/right hands."""
    BY_TRACK = auto()    # Track 0 = right, track 1 = left (default for multi-track)
    BY_PITCH = auto()    # Split at middle C (MIDI 60): >= 60 right, < 60 left
    BY_CHANNEL = auto()  # Channel 0 = right, channel 1 = left (for Type 0 MIDI)


class SongLoadError(Exception):
    """Raised when a song file cannot be parsed."""


def load_song(
    file_path: str | Path,
    hand_split: HandSplitStrategy = HandSplitStrategy.BY_TRACK,
) -> Song:
    """Load a MIDI or MusicXML file and return a Song.

    Args:
        file_path: Path to a .mid, .midi, .xml, .mxl, or .musicxml file.
        hand_split: Strategy for assigning notes to hands.

    Raises:
        SongLoadError: If the file cannot be parsed.
    """
    path = Path(file_path)
    try:
        if path.suffix in (".mid", ".midi"):
            return _load_midi(path, hand_split)
        elif path.suffix in (".xml", ".mxl", ".musicxml"):
            return _load_musicxml(path)
        else:
            raise SongLoadError(f"Unsupported file format: {path.suffix}")
    except SongLoadError:
        raise
    except Exception as exc:
        raise SongLoadError(f"Failed to load {path.name}: {exc}") from exc


def _assign_hand(
    pitch: int, track_idx: int, channel: int, strategy: HandSplitStrategy
) -> Hand:
    if strategy == HandSplitStrategy.BY_PITCH:
        return Hand.RIGHT if pitch >= 60 else Hand.LEFT
    elif strategy == HandSplitStrategy.BY_CHANNEL:
        return Hand.LEFT if channel % 2 == 1 else Hand.RIGHT
    else:  # BY_TRACK
        return Hand.LEFT if track_idx % 2 == 1 else Hand.RIGHT


def _load_midi(path: Path, hand_split: HandSplitStrategy = HandSplitStrategy.BY_TRACK) -> Song:
    mid = mido.MidiFile(str(path))
    song = Song(
        title=path.stem,
        ticks_per_beat=mid.ticks_per_beat,
    )

    tempo = 500_000  # default 120 BPM
    song.tempo_changes.append(TempoChange(time=0.0, bpm=mido.tempo2bpm(tempo)))

    for track_idx, track in enumerate(mid.tracks):
        abs_time = 0.0
        pending: dict[int, tuple[float, int, int]] = {}  # pitch -> (start_time, velocity, channel)

        for msg in track:
            abs_time += mido.tick2second(msg.time, mid.ticks_per_beat, tempo)

            if msg.type == "set_tempo":
                tempo = msg.tempo
                song.tempo_changes.append(TempoChange(time=abs_time, bpm=mido.tempo2bpm(tempo)))

            elif msg.type == "note_on" and msg.velocity > 0:
                # Close any existing note on the same pitch (overlapping notes)
                if msg.note in pending:
                    start, vel, ch = pending.pop(msg.note)
                    song.notes.append(
                        NoteEvent(
                            pitch=msg.note,
                            start_time=start,
                            duration=max(abs_time - start, 0.01),
                            velocity=vel,
                            hand=_assign_hand(msg.note, track_idx, ch, hand_split),
                            track=track_idx,
                        )
                    )
                pending[msg.note] = (abs_time, msg.velocity, getattr(msg, 'channel', 0))

            elif msg.type in ("note_off", "note_on"):
                if msg.note in pending:
                    start, vel, ch = pending.pop(msg.note)
                    song.notes.append(
                        NoteEvent(
                            pitch=msg.note,
                            start_time=start,
                            duration=max(abs_time - start, 0.01),
                            velocity=vel,
                            hand=_assign_hand(msg.note, track_idx, ch, hand_split),
                            track=track_idx,
                        )
                    )

    song.notes.sort(key=lambda n: n.start_time)
    if song.notes:
        last = song.notes[-1]
        song.duration = last.start_time + last.duration
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
