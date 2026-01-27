"""Tests for core data models."""

from keyfall.models import NoteEvent, Song
from keyfall.playback import select_section, split_hands
from keyfall.models import Hand


def test_split_hands():
    song = Song(notes=[
        NoteEvent(pitch=60, start_time=0.0, duration=1.0, hand=Hand.RIGHT),
        NoteEvent(pitch=48, start_time=0.0, duration=1.0, hand=Hand.LEFT),
        NoteEvent(pitch=64, start_time=1.0, duration=1.0, hand=Hand.RIGHT),
    ])
    left, right = split_hands(song)
    assert len(left.notes) == 1
    assert len(right.notes) == 2


def test_select_section():
    song = Song(notes=[
        NoteEvent(pitch=60, start_time=0.0, duration=1.0),
        NoteEvent(pitch=62, start_time=4.0, duration=1.0),
        NoteEvent(pitch=64, start_time=8.0, duration=1.0),
    ])
    section = select_section(song, start_bar=2, end_bar=2)
    assert len(section.notes) == 1
    assert section.notes[0].pitch == 62
