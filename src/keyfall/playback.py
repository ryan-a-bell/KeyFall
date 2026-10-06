"""Playback engine — manages song position, wait mode, tempo scaling, and metronome."""

from __future__ import annotations

import math
from dataclasses import dataclass

from keyfall.models import PERCUSSION, Hand, NoteEvent, Song


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
        self.waiting: bool = False  # wait mode is holding for the player
        # share of a chord that must be held to continue in wait mode (lower for a
        # microphone, where one note of a chord can go undetected)
        self.required_fraction: float = 1.0
        self._starts = [n.start_time for n in song.notes]

    def set_tempo_scale(self, scale: float) -> None:
        """Set tempo scale, clamped to [0.25, 2.0]."""
        self.tempo_scale = max(0.25, min(2.0, scale))

    def update(self, dt: float, pressed_pitches: set[int]) -> list[NoteEvent]:
        """Advance playback by dt seconds. Returns notes that became active this frame."""
        if self.paused:
            return []

        newly_active: list[NoteEvent] = []

        if self.wait_mode:
            newly_active = self._advance_wait_mode(dt, pressed_pitches)
        else:
            self.position += dt * self.tempo_scale
            newly_active = self._collect_active_notes()

        return newly_active

    def _advance_wait_mode(self, dt: float, pressed_pitches: set[int]) -> list[NoteEvent]:
        """Scroll normally, but stop at each note until the player presses it.

        Notes for the inactive hand never block (they are auto-played).
        """
        played: list[NoteEvent] = []
        budget = dt * self.tempo_scale
        self.waiting = False
        while self.note_index < len(self.song.notes):
            group = self._get_simultaneous_notes()
            start = group[0].start_time
            if self.position + budget < start:
                break
            budget -= max(0.0, start - self.position)
            self.position = max(self.position, start)
            required = {
                n.pitch for n in group
                if self.active_hand == Hand.BOTH or n.hand == self.active_hand
            }
            held = len(required & pressed_pitches)
            needed = max(1, round(len(required) * self.required_fraction)) if required else 0
            if held < needed:
                self.waiting = True
                return played
            self.note_index += len(group)
            played.extend(group)
        if not self.waiting:
            self.position += budget
        return played

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

    def expected_pitches(self, before: float = 0.15, after: float = 0.35) -> set[int]:
        """Pitches the player should be playing around now (for guided detection)."""
        from bisect import bisect_left, bisect_right
        lo = bisect_left(self._starts, self.position - before)
        hi = bisect_right(self._starts, self.position + after)
        return {n.pitch for n in self.song.notes[lo:hi]
                if self.active_hand == Hand.BOTH or n.hand == self.active_hand}

    @property
    def finished(self) -> bool:
        return self.note_index >= len(self.song.notes)


def split_hands(song: Song) -> tuple[Song, Song]:
    """Split a song into left-hand and right-hand parts."""
    left = Song(title=song.title, tempo_changes=list(song.tempo_changes),
                time_signatures=list(song.time_signatures), ticks_per_beat=song.ticks_per_beat)
    right = Song(title=song.title, tempo_changes=list(song.tempo_changes),
                 time_signatures=list(song.time_signatures), ticks_per_beat=song.ticks_per_beat)

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


def _beats_to_seconds(beats: float, bpm: float) -> float:
    """Convert beat count to seconds at given BPM."""
    return beats * 60.0 / bpm


def select_section(
    song: Song,
    start_bar: int,
    end_bar: int,
    beats_per_bar: float = 4.0,
    bpm: float | None = None,
) -> Song:
    """Extract a section of the song by bar numbers (1-indexed).

    If bpm is None, the first tempo change is used (defaults to 120).
    """
    if bpm is None:
        bpm = song.tempo_changes[0].bpm if song.tempo_changes else 120.0
    start_time = _beats_to_seconds((start_bar - 1) * beats_per_bar, bpm)
    end_time = _beats_to_seconds(end_bar * beats_per_bar, bpm)

    section = Song(
        title=f"{song.title} (bars {start_bar}-{end_bar})",
        tempo_changes=list(song.tempo_changes),
        time_signatures=list(song.time_signatures),
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

    for note in song.backing:
        if start_time <= note.start_time < end_time:
            section.backing.append(
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


class BackingPlayer:
    """Plays a song's backing notes as playback advances, each track on its own
    channel and instrument, to the computer synth and/or the keyboard's MIDI output.

    Handles restarts and seeks: if the position jumps backwards, it rewinds.
    """

    VOLUME = 0.7
    _FREE_CHANNELS = [c for c in range(1, 16) if c != 9]  # 0 = player piano, 9 = drums

    def __init__(self, song: Song) -> None:
        self.notes = song.backing
        self._starts = [n.start_time for n in self.notes]
        self._index = 0
        self._last_position = 0.0
        self.channels: dict[int, int] = {}  # track -> MIDI channel
        self.programs: dict[int, int] = {}  # channel -> GM program (PERCUSSION for drums)
        free = iter(self._FREE_CHANNELS)
        for track in sorted({n.track for n in self.notes}):
            program = song.backing_programs.get(track, 0)
            channel = 9 if program == PERCUSSION else next(free, 15)
            self.channels[track] = channel
            self.programs[channel] = program
        self._ready: set[int] = set()  # id() of outputs already given program changes
        self._muted: set[int] = set()  # synth channels with no usable instrument (drums)

    def _setup(self, audio, midi_out) -> None:
        if audio is not None and id(audio) not in self._ready:
            for channel, program in self.programs.items():
                if program == PERCUSSION:
                    if audio.set_instrument(channel, 0, bank=128) is False:
                        self._muted.add(channel)  # no drum kit: silence beats piano thumps
                else:
                    audio.set_instrument(channel, program)
            self._ready.add(id(audio))
        if midi_out is not None and id(midi_out) not in self._ready:
            for channel, program in self.programs.items():
                if program != PERCUSSION:
                    midi_out.program_change(channel, program)
            self._ready.add(id(midi_out))

    def update(self, position: float, audio, midi_out=None) -> None:
        if not self.notes:
            return
        self._setup(audio, midi_out)
        if position < self._last_position:
            from bisect import bisect_left
            self._index = bisect_left(self._starts, position)
        self._last_position = position
        while self._index < len(self.notes) and self.notes[self._index].start_time <= position:
            note = self.notes[self._index]
            self._index += 1
            if note.start_time < position - 0.25:  # skip stale notes after a seek
                continue
            quiet = NoteEvent(note.pitch, note.start_time, note.duration,
                              max(1, int(note.velocity * self.VOLUME)), note.hand, note.track)
            channel = self.channels.get(note.track, 1)
            if audio is not None and channel not in self._muted:
                audio.play_note_event(quiet, channel=channel)
            if midi_out is not None:
                midi_out.play_note_event(quiet, channel=channel)


class KeyLights:
    """Lights the keys the player should press next, for light-up keyboards.

    Sends a note-on (velocity 1) on ``channel`` a little before each note
    arrives and a note-off when it ends. Many light-up keyboards light keys
    for notes received on a specific channel; the channel is configurable.
    """

    LEAD_TIME = 0.5  # seconds before the note reaches the hit line

    def __init__(self) -> None:
        self.lit: set[int] = set()

    def update(self, song: Song, position: float, active_hand: Hand, midi_out,
               channel: int) -> None:
        wanted = {
            n.pitch for n in song.notes
            if n.start_time - self.LEAD_TIME <= position < n.start_time + n.duration
            and (active_hand == Hand.BOTH or n.hand == active_hand)
        } if midi_out is not None else set()
        for pitch in wanted - self.lit:
            midi_out.note_on(pitch, 1, channel)
        for pitch in self.lit - wanted:
            if midi_out is not None:
                midi_out.note_off(pitch, channel)
        self.lit = wanted

    def clear(self, midi_out, channel: int) -> None:
        if midi_out is not None:
            for pitch in self.lit:
                midi_out.note_off(pitch, channel)
        self.lit = set()


class SongOutputs:
    """Everything a gameplay view sends besides the player's own notes:
    the auto-played hand, backing tracks, and key lights."""

    def __init__(self, song: Song) -> None:
        self.song = song
        self.backing = BackingPlayer(song)
        self.lights = KeyLights()

    def update(self, engine: PlaybackEngine, newly_active: list[NoteEvent], audio,
               midi_out=None, mode: str = "accompaniment", light_channel: int = 0) -> None:
        out = midi_out if (midi_out is not None and getattr(midi_out, "connected", True)) \
            else None
        accompaniment = out if mode in ("accompaniment", "both") else None
        lights = out if mode in ("lights", "both") else None
        for note in newly_active:  # the hand the player isn't practicing
            if engine.active_hand != Hand.BOTH and note.hand != engine.active_hand:
                for target in (audio, accompaniment):
                    if target is not None:
                        target.play_note_event(note)
        self.backing.update(engine.position, audio, accompaniment)
        if lights is not None or self.lights.lit:
            self.lights.update(engine.song, engine.position, engine.active_hand, lights,
                               light_channel)
        for target in (audio, out):
            if target is not None:
                target.flush_pending_offs()

    def stop(self, audio, midi_out=None, light_channel: int = 0) -> None:
        self.lights.clear(midi_out, light_channel)
        for target in (audio, midi_out):
            if target is not None:
                target.all_notes_off()


def beat_length(song: Song) -> float:
    """Seconds per beat at the song's opening tempo."""
    bpm = song.tempo_changes[0].bpm if song.tempo_changes else 120.0
    return 60.0 / bpm if bpm > 0 else 0.5


BEATS_PER_BAR = 4  # matches select_section's default bar math


def bar_of(time_s: float, song: Song, first_bar: int = 1) -> int:
    """1-based bar number containing ``time_s`` (4/4 at the opening tempo)."""
    return int(max(0.0, time_s) // (beat_length(song) * BEATS_PER_BAR)) + first_bar


class ClickTrack:
    """Metronome clicks locked to song position (so wait mode and tempo just work).

    ``mode``: "off", "count-in" (only the bar before the song starts, where the
    position is negative), or "on" (every beat). Downbeats are accented.
    """

    DOWNBEAT = (76, 110)  # GM hi wood block
    BEAT = (77, 80)  # GM low wood block
    CHANNEL = 9

    def __init__(self) -> None:
        self._prev: float | None = None
        self._kit: dict[int, bool] = {}  # id(audio) -> drum kit available

    def reset(self) -> None:
        self._prev = None

    def update(self, position: float, beat: float, mode: str) -> list[tuple[int, int]]:
        if mode == "off" or beat <= 0:
            self._prev = position
            return []
        prev = self._prev
        self._prev = position
        if prev is None or position < prev:  # start / restart: include a beat landing now
            prev = position - 1e-6
        clicks = []
        first = math.floor(prev / beat) + 1
        last = math.floor(position / beat + 1e-9)
        for k in range(first, last + 1):
            if mode == "count-in" and k >= 0:
                continue
            clicks.append(self.DOWNBEAT if k % BEATS_PER_BAR == 0 else self.BEAT)
        return clicks

    def play(self, audio, clicks: list[tuple[int, int]]) -> None:
        if audio is None or not clicks:
            return
        has_kit = self._kit.get(id(audio))
        if has_kit is None:
            has_kit = self._kit[id(audio)] = audio.set_instrument(self.CHANNEL, 0, bank=128) \
                is not False
        for pitch, velocity in clicks:
            if has_kit:
                audio.play_note_event(NoteEvent(pitch, 0.0, 0.08, velocity), channel=self.CHANNEL)
            else:  # piano-only sound: a short high note instead of a wood block
                audio.play_note_event(NoteEvent(pitch + 20, 0.0, 0.06, velocity // 2), channel=0)


def count_in_seconds(song: Song, mode: str) -> float:
    """How far before the song to start: one bar, unless the metronome is off."""
    return 0.0 if mode == "off" else beat_length(song) * BEATS_PER_BAR
