"""Playback engine — manages song position, wait mode, tempo scaling, and metronome."""

from __future__ import annotations

from dataclasses import dataclass

from keyfall.models import Hand, NoteEvent, Song


@dataclass
class ProgressivePractice:
    """Auto-scaling tempo for progressive practice sessions."""
    start_scale: float = 0.5
    target_scale: float = 1.0
    step: float = 0.05
    accuracy_threshold: float = 90.0
    current_scale: float = 0.5

    def on_loop_complete(self, accuracy: float) -> float:
        """Adjust scale based on loop accuracy. Returns the new scale."""
        if accuracy >= self.accuracy_threshold:
            self.current_scale = min(self.target_scale, self.current_scale + self.step)
        else:
            self.current_scale = max(self.start_scale, self.current_scale - self.step)
        return self.current_scale


class Metronome:
    """Generates metronome click events at the current tempo."""

    def __init__(self, bpm: float = 120.0, beats_per_bar: int = 4) -> None:
        self.bpm = bpm
        self.beats_per_bar = beats_per_bar
        self.enabled = False
        self._beat_counter = 0
        self._time_since_last_beat = 0.0

    def update(self, dt: float, tempo_scale: float = 1.0) -> list[tuple[int, int]]:
        """Advance the metronome. Returns list of (midi_note, velocity) clicks to play.

        Uses MIDI channel 9 convention: note 37 = side stick, note 76 = hi woodblock.
        Beat 1 gets accent (higher velocity).
        """
        if not self.enabled:
            return []

        beat_duration = 60.0 / (self.bpm * tempo_scale)
        self._time_since_last_beat += dt
        clicks: list[tuple[int, int]] = []

        while self._time_since_last_beat >= beat_duration:
            self._time_since_last_beat -= beat_duration
            is_downbeat = (self._beat_counter % self.beats_per_bar) == 0
            note = 76 if is_downbeat else 37
            velocity = 100 if is_downbeat else 70
            clicks.append((note, velocity))
            self._beat_counter += 1

        return clicks

    def reset(self) -> None:
        self._beat_counter = 0
        self._time_since_last_beat = 0.0


class PlaybackEngine:
    """Drives song playback, advancing position in real-time or wait mode."""

    def __init__(self, song: Song) -> None:
        self.song = song
        self.position: float = 0.0  # seconds
        self.note_index: int = 0
        self.wait_mode: bool = False
        self.tempo_scale: float = 1.0
        self.paused: bool = False
        self.active_hand: Hand = Hand.BOTH

    def set_tempo_scale(self, scale: float) -> None:
        """Set tempo scale, clamped to [0.25, 2.0]."""
        self.tempo_scale = max(0.25, min(2.0, scale))

    def update(self, dt: float, pressed_pitches: set[int]) -> list[NoteEvent]:
        """Advance playback by dt seconds. Returns notes that became active this frame."""
        if self.paused:
            return []

        newly_active: list[NoteEvent] = []

        if self.wait_mode:
            newly_active = self._advance_wait_mode(pressed_pitches)
        else:
            self.position += dt * self.tempo_scale
            newly_active = self._collect_active_notes()

        return newly_active

    def _advance_wait_mode(self, pressed_pitches: set[int]) -> list[NoteEvent]:
        """In wait mode, only advance when the player plays the correct note(s)."""
        if self.note_index >= len(self.song.notes):
            return []

        upcoming = self._get_simultaneous_notes()
        required = {
            n.pitch for n in upcoming
            if self.active_hand == Hand.BOTH or n.hand == self.active_hand
        }

        if required and required.issubset(pressed_pitches):
            self.note_index += len(upcoming)
            if upcoming:
                self.position = upcoming[-1].start_time + upcoming[-1].duration
            return upcoming
        return []

    def _collect_active_notes(self) -> list[NoteEvent]:
        active: list[NoteEvent] = []
        while self.note_index < len(self.song.notes):
            note = self.song.notes[self.note_index]
            if note.start_time <= self.position:
                active.append(note)
                self.note_index += 1
            else:
                break
        return active

    def _get_simultaneous_notes(self, tolerance: float = 0.05) -> list[NoteEvent]:
        """Get all notes starting at approximately the same time as the current note."""
        if self.note_index >= len(self.song.notes):
            return []
        first = self.song.notes[self.note_index]
        group = [first]
        i = self.note_index + 1
        while i < len(self.song.notes):
            n = self.song.notes[i]
            if abs(n.start_time - first.start_time) <= tolerance:
                group.append(n)
                i += 1
            else:
                break
        return group

    @property
    def finished(self) -> bool:
        return self.note_index >= len(self.song.notes)


def split_hands(song: Song) -> tuple[Song, Song]:
    """Split a song into left-hand and right-hand parts."""
    left = Song(title=song.title, tempo_changes=song.tempo_changes,
                time_signatures=song.time_signatures, ticks_per_beat=song.ticks_per_beat)
    right = Song(title=song.title, tempo_changes=song.tempo_changes,
                 time_signatures=song.time_signatures, ticks_per_beat=song.ticks_per_beat)

    for note in song.notes:
        if note.hand == Hand.LEFT:
            left.notes.append(note)
        else:
            right.notes.append(note)

    for s in (left, right):
        if s.notes:
            last = s.notes[-1]
            s.duration = last.start_time + last.duration

    return left, right


def select_section(song: Song, start_bar: int, end_bar: int, beats_per_bar: float = 4.0) -> Song:
    """Extract a section of the song by bar numbers (1-indexed)."""
    start_time = (start_bar - 1) * beats_per_bar
    end_time = end_bar * beats_per_bar

    section = Song(
        title=f"{song.title} (bars {start_bar}-{end_bar})",
        tempo_changes=song.tempo_changes,
        time_signatures=song.time_signatures,
        ticks_per_beat=song.ticks_per_beat,
    )

    for note in song.notes:
        if start_time <= note.start_time < end_time:
            section.notes.append(
                NoteEvent(
                    pitch=note.pitch,
                    start_time=note.start_time - start_time,
                    duration=note.duration,
                    velocity=note.velocity,
                    hand=note.hand,
                    track=note.track,
                )
            )

    if section.notes:
        last = section.notes[-1]
        section.duration = last.start_time + last.duration

    return section
