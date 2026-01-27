"""Load MIDI and MusicXML files into the Song model."""

from __future__ import annotations

from pathlib import Path

import mido

from keyfall.models import Hand, NoteEvent, Song, TempoChange


def load_song(file_path: str | Path) -> Song:
    """Load a MIDI or MusicXML file and return a Song."""
    path = Path(file_path)
    if path.suffix in (".mid", ".midi"):
        return _load_midi(path)
    elif path.suffix in (".xml", ".mxl", ".musicxml"):
        return _load_musicxml(path)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")


def _load_midi(path: Path) -> Song:
    mid = mido.MidiFile(str(path))
    song = Song(
        title=path.stem,
        ticks_per_beat=mid.ticks_per_beat,
    )

    tempo = 500_000  # default 120 BPM
    song.tempo_changes.append(TempoChange(time=0.0, bpm=mido.tempo2bpm(tempo)))

    for track_idx, track in enumerate(mid.tracks):
        abs_time = 0.0
        pending: dict[int, tuple[float, int]] = {}  # pitch -> (start_time, velocity)

        for msg in track:
            abs_time += mido.tick2second(msg.time, mid.ticks_per_beat, tempo)

            if msg.type == "set_tempo":
                tempo = msg.tempo
                song.tempo_changes.append(TempoChange(time=abs_time, bpm=mido.tempo2bpm(tempo)))

            elif msg.type == "note_on" and msg.velocity > 0:
                pending[msg.note] = (abs_time, msg.velocity)

            elif msg.type in ("note_off", "note_on"):
                if msg.note in pending:
                    start, vel = pending.pop(msg.note)
                    song.notes.append(
                        NoteEvent(
                            pitch=msg.note,
                            start_time=start,
                            duration=max(abs_time - start, 0.01),
                            velocity=vel,
                            hand=Hand.LEFT if track_idx % 2 == 1 else Hand.RIGHT,
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
