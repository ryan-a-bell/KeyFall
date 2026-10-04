"""Tests for MIDI loading: tempo map, drum filtering, and automatic hand assignment."""

from pathlib import Path

import mido
import pytest

from keyfall.models import Hand
from keyfall.song_loader import HandSplitStrategy, load_song


def _track(name: str, notes: list[int], program: int = 0, channel: int = 0) -> mido.MidiTrack:
    """Build a track that plays each pitch for one beat, back to back."""
    track = mido.MidiTrack()
    if name:
        track.append(mido.MetaMessage("track_name", name=name))
    track.append(mido.Message("program_change", program=program, channel=channel))
    for pitch in notes:
        track.append(mido.Message("note_on", note=pitch, velocity=90, channel=channel, time=0))
        track.append(mido.Message("note_off", note=pitch, velocity=0, channel=channel, time=480))
    return track


def _write(tmp_path: Path, *tracks: mido.MidiTrack, tempo: int | None = None) -> Path:
    mid = mido.MidiFile(type=1, ticks_per_beat=480)
    conductor = mido.MidiTrack()
    if tempo is not None:
        conductor.append(mido.MetaMessage("set_tempo", tempo=tempo))
    mid.tracks.append(conductor)
    mid.tracks.extend(tracks)
    path = tmp_path / "song.mid"
    mid.save(path)
    return path


def _hands(song) -> dict[int, set[Hand]]:
    by_track: dict[int, set[Hand]] = {}
    for note in song.notes:
        by_track.setdefault(note.track, set()).add(note.hand)
    return by_track


def test_auto_two_unnamed_piano_tracks_higher_is_right(tmp_path):
    # Lower track listed first, so BY_TRACK would get this backwards.
    path = _write(tmp_path, _track("", [40, 43, 47]), _track("", [72, 74, 76]))
    song = load_song(path)
    assert _hands(song) == {1: {Hand.LEFT}, 2: {Hand.RIGHT}}


def test_auto_uses_track_name_hints(tmp_path):
    path = _write(tmp_path, _track("RH", [50, 52]), _track("Left Hand", [70, 72]))
    song = load_song(path)
    assert _hands(song) == {1: {Hand.RIGHT}, 2: {Hand.LEFT}}


def test_auto_one_named_track_other_gets_opposite_hand(tmp_path):
    bass = _track("Bass", [36, 38], program=33)
    strings = _track("Strings", [80, 82], program=48)
    path = _write(tmp_path, bass, strings)
    song = load_song(path)
    assert _hands(song) == {1: {Hand.LEFT}, 2: {Hand.RIGHT}}


def test_auto_single_track_splits_at_middle_c(tmp_path):
    # e.g. a single Suno piano stem exported to MIDI
    path = _write(tmp_path, _track("Piano", [48, 55, 60, 67]))
    song = load_song(path)
    assert [(n.pitch, n.hand) for n in song.notes] == [
        (48, Hand.LEFT), (55, Hand.LEFT), (60, Hand.RIGHT), (67, Hand.RIGHT),
    ]


def test_auto_keeps_only_piano_tracks_in_band_arrangement(tmp_path):
    path = _write(
        tmp_path,
        _track("Guitar", [64, 67], program=25),
        _track("Piano", [72, 48], program=0),
        _track("Synth Pad", [60], program=88),
    )
    song = load_song(path)
    assert {n.track for n in song.notes} == {2}


def test_drum_channel_is_dropped(tmp_path):
    path = _write(tmp_path, _track("Piano", [60]), _track("Drums", [36, 38], channel=9))
    song = load_song(path, HandSplitStrategy.BY_TRACK)
    assert [n.pitch for n in song.notes] == [60]


def test_tempo_from_conductor_track_applies_to_other_tracks(tmp_path):
    # 60 BPM: each one-beat note lasts one second
    path = _write(tmp_path, _track("Piano", [60, 62]), tempo=1_000_000)
    song = load_song(path)
    assert song.notes[1].start_time == pytest.approx(1.0)
    assert song.notes[0].duration == pytest.approx(1.0)
    assert song.tempo_changes[0].bpm == pytest.approx(60.0)


def test_explicit_by_track_strategy_still_available(tmp_path):
    path = _write(tmp_path, _track("", [40]), _track("", [72]))
    song = load_song(path, HandSplitStrategy.BY_TRACK)
    assert _hands(song) == {1: {Hand.LEFT}, 2: {Hand.RIGHT}}
