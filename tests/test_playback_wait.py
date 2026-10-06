"""Wait mode: scroll smoothly, stop at each note until it is played."""

from keyfall.models import Hand, NoteEvent, Song
from keyfall.playback import PlaybackEngine


def _engine(*notes):
    song = Song(notes=list(notes))
    engine = PlaybackEngine(song)
    engine.wait_mode = True
    return engine


def test_scrolls_until_next_note_then_waits():
    engine = _engine(NoteEvent(60, 1.0, 0.5))
    assert engine.update(0.5, set()) == []
    assert engine.position == 0.5 and not engine.waiting
    engine.update(1.0, set())
    assert engine.position == 1.0  # stopped exactly at the note
    assert engine.waiting


def test_correct_press_releases_note_at_its_start_time():
    note = NoteEvent(60, 1.0, 2.0)
    engine = _engine(note)
    engine.update(1.0, set())
    played = engine.update(1 / 60, {60})
    assert played == [note]
    # position did not jump to the end of the (long) note
    assert engine.position < 1.1


def test_inactive_hand_notes_do_not_block():
    left = NoteEvent(48, 1.0, 0.5, hand=Hand.LEFT)
    engine = _engine(left)
    engine.active_hand = Hand.RIGHT
    played = engine.update(2.0, set())
    assert played == [left]
    assert not engine.waiting
