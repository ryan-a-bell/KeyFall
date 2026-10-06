"""A short built-in two-hand passage plus a mid-song PlayFrame, for theme previews."""

from __future__ import annotations

from keyfall.accessibility import NoteLabelMode
from keyfall.models import Hand, HitGrade, NoteEvent, SessionStats, Song, TempoChange
from keyfall.renderer.skins.frames import PlayFrame

_BEAT = 0.42


def demo_song() -> Song:
    """Melody in the right hand over broken chords in the left (A minor)."""
    notes: list[NoteEvent] = []
    melody = [76, 79, 81, 79, 76, 74, 72, 74, 76, 81, 84, 83, 81, 79, 77, 76,
              74, 76, 77, 79, 81, 79, 77, 76, 74, 72, 71, 72, 74, 76, 79, 81]
    lens = [1, 1, 2, 1, 1, 1, 1, 2, 1, 1, 2, 1, 1, 1, 1, 2,
            1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2]
    t = 0.0
    for pitch, n in zip(melody, lens):
        notes.append(NoteEvent(pitch, t, n * _BEAT * 0.95, 90, Hand.RIGHT, 1))
        if n == 2 and pitch > 78:
            notes.append(NoteEvent(pitch - 4, t, n * _BEAT * 0.95, 80, Hand.RIGHT, 1))
        t += n * _BEAT
    chords = [(45, 52, 57, 60), (41, 48, 53, 57), (48, 55, 60, 64), (43, 50, 55, 59)] * 3
    t = 0.0
    for chord in chords:
        root, a, b, _c = chord
        for i, pitch in enumerate((root, a, b, a)):
            notes.append(NoteEvent(pitch, t + i * _BEAT, _BEAT * (1.9 if i == 0 else 0.9), 70,
                                   Hand.LEFT, 2))
        notes.append(NoteEvent(root - 12, t, _BEAT * 3.8, 70, Hand.LEFT, 2))
        t += 4 * _BEAT
    notes.sort(key=lambda n: n.start_time)
    song = Song(title="Midnight Drive", notes=notes,
                tempo_changes=[TempoChange(0.0, 60 / _BEAT)])
    song.duration = max(n.start_time + n.duration for n in notes)
    return song


def demo_frame(song: Song | None = None, position: float = 7.15,
               label_mode: NoteLabelMode = NoteLabelMode.NONE) -> PlayFrame:
    song = song or demo_song()
    pressed = {n.pitch for n in song.notes if n.start_time <= position < n.start_time + n.duration}
    stats = SessionStats(song_title=song.title, total_notes=54, perfect=41, good=10, ok=1,
                         missed=2, max_streak=37, accuracy_pct=96.3)
    offsets = [(-1) ** i * (i * 7 % 60) - 8 for i in range(54)]
    return PlayFrame(song=song, position=position, pressed=pressed, stats=stats, streak=37,
                     tempo_scale=0.8, wait_mode=False, mode="Play", label_mode=label_mode,
                     judgement=HitGrade.PERFECT, judgement_age=0.12, timing_offsets_ms=offsets,
                     clock=position)
