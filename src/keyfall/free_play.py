"""Free play mode — standalone logic for chord detection, recording, and MIDI export."""

from __future__ import annotations

import time
from pathlib import Path

import mido

from keyfall.models import NoteEvent, Song


_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_CHORD_TEMPLATES: list[tuple[frozenset[int], str]] = [
    (frozenset({0, 4, 7}), ""),
    (frozenset({0, 3, 7}), "m"),
    (frozenset({0, 3, 6}), "dim"),
    (frozenset({0, 4, 8}), "aug"),
    (frozenset({0, 4, 7, 10}), "7"),
    (frozenset({0, 4, 7, 11}), "maj7"),
    (frozenset({0, 3, 7, 10}), "m7"),
    (frozenset({0, 3, 6, 10}), "m7b5"),
    (frozenset({0, 3, 6, 9}), "dim7"),
    (frozenset({0, 5, 7}), "sus4"),
    (frozenset({0, 2, 7}), "sus2"),
]


def detect_chord(pitches: set[int]) -> str | None:
    """Detect chord name from a set of MIDI pitches."""
    if len(pitches) < 2:
        return None

    pitch_classes = frozenset(p % 12 for p in pitches)
    if len(pitch_classes) < 2:
        return None

    best_match: str | None = None
    best_score = 0

    for root in range(12):
        intervals = frozenset((pc - root) % 12 for pc in pitch_classes)
        for template, suffix in _CHORD_TEMPLATES:
            matched = len(intervals & template)
            unmatched = len(intervals - template)
            score = matched - unmatched
            if matched >= len(template) and score > best_score:
                best_score = score
                best_match = f"{_NOTE_NAMES[root]}{suffix}"

    return best_match


class FreePlayMode:
    """Standalone free play logic: chord detection, recording, and MIDI export."""

    def __init__(self) -> None:
        self._pressed: set[int] = set()
        self._chord: str | None = None
        self._recording = False
        self._record_start: float = 0.0
        self._note_ons: dict[int, tuple[float, int]] = {}  # pitch -> (start_time, velocity)
        self._recorded_notes: list[NoteEvent] = []

    def note_on(self, pitch: int, velocity: int = 80) -> None:
        self._pressed.add(pitch)
        self._chord = detect_chord(self._pressed)
        if self._recording:
            self._note_ons[pitch] = (time.time() - self._record_start, velocity)

    def note_off(self, pitch: int) -> None:
        self._pressed.discard(pitch)
        if not self._pressed:
            self._chord = None
        else:
            self._chord = detect_chord(self._pressed)
        if self._recording and pitch in self._note_ons:
            start, vel = self._note_ons.pop(pitch)
            elapsed = time.time() - self._record_start
            self._recorded_notes.append(NoteEvent(
                pitch=pitch,
                start_time=start,
                duration=max(elapsed - start, 0.01),
                velocity=vel,
            ))

    def get_active_chord(self) -> str | None:
        return self._chord

    def start_recording(self) -> None:
        self._recording = True
        self._record_start = time.time()
        self._note_ons.clear()
        self._recorded_notes.clear()

    def stop_recording(self) -> Song:
        """Stop recording and return the recorded notes as a Song."""
        self._recording = False
        # Close any still-held notes
        elapsed = time.time() - self._record_start
        for pitch, (start, vel) in self._note_ons.items():
            self._recorded_notes.append(NoteEvent(
                pitch=pitch,
                start_time=start,
                duration=max(elapsed - start, 0.01),
                velocity=vel,
            ))
        self._note_ons.clear()

        notes = sorted(self._recorded_notes, key=lambda n: n.start_time)
        duration = 0.0
        if notes:
            last = notes[-1]
            duration = last.start_time + last.duration

        return Song(title="Recording", notes=notes, duration=duration)

    @property
    def is_recording(self) -> bool:
        return self._recording

    def update(self, dt: float) -> None:
        """Per-frame update (placeholder for future expansion)."""
        pass


def export_midi(song: Song, output_path: Path) -> None:
    """Export a Song to a standard MIDI file."""
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)

    track.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(120)))

    # Build a list of (time, type, pitch, velocity) events
    events: list[tuple[float, str, int, int]] = []
    for note in song.notes:
        events.append((note.start_time, "note_on", note.pitch, note.velocity))
        events.append((note.start_time + note.duration, "note_off", note.pitch, 0))
    events.sort(key=lambda e: e[0])

    prev_time = 0.0
    ticks_per_beat = mid.ticks_per_beat
    tempo = 500_000  # 120 BPM

    for t, msg_type, pitch, velocity in events:
        delta_sec = t - prev_time
        delta_ticks = int(mido.second2tick(delta_sec, ticks_per_beat, tempo))
        track.append(mido.Message(msg_type, note=pitch, velocity=velocity, time=delta_ticks))
        prev_time = t

    mid.save(str(output_path))
