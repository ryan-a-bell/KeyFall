"""Multi-stem (Suno) import: role guessing, cleanup, combining, persistence."""

import json

import mido

from keyfall.models import Hand, NoteEvent
from keyfall.stems import StemRole, StemSet, cleanup, guess_instrument, quantize


def _stem(folder, name, notes, channel=0, bpm=120):
    """notes: list of (pitch, start_beat, beats, velocity)."""
    mid = mido.MidiFile(type=1, ticks_per_beat=480)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))
    events = []
    for pitch, start, beats, vel in notes:
        events.append((int(start * 480), 1, pitch, vel))
        events.append((int((start + beats) * 480), 0, pitch, 0))
    events.sort(key=lambda e: (e[0], e[1]))
    last = 0
    for tick, on, pitch, vel in events:
        kind = "note_on" if on else "note_off"
        track.append(mido.Message(kind, note=pitch, velocity=vel, channel=channel,
                                  time=tick - last))
        last = tick
    mid.tracks.append(track)
    mid.save(folder / f"{name}.mid")


def _band(tmp_path, with_piano=False):
    folder = tmp_path / "Neon Rain"
    folder.mkdir()
    _stem(folder, "Bass", [(36, b, 1, 90) for b in range(8)])
    _stem(folder, "Lead Synth", [(72 + b % 5, b, 1, 90) for b in range(8)])
    _stem(folder, "Guitar", [(64, b, 1, 70) for b in range(8)])
    _stem(folder, "Drums", [(36, b, 0.25, 100) for b in range(8)])
    if with_piano:
        _stem(folder, "Piano", [(48, b, 1, 80) for b in range(4)] + [(67, b, 1, 80)
                                                                    for b in range(4)])
    return folder


def test_guess_instrument_from_names():
    assert guess_instrument("Neon Rain (Bass)") == "Bass"
    assert guess_instrument("drums_stem") == "Drums"
    assert guess_instrument("Keys") == "Piano"
    assert guess_instrument("Lead Vocal") == "Vocals"
    assert guess_instrument("thing") == "Other"


def test_band_without_piano_bass_left_lead_right_rest_backing(tmp_path):
    stems = {s.name: s.role for s in StemSet.load(_band(tmp_path)).stems}
    assert stems == {"Bass": StemRole.LEFT, "Drums": StemRole.OFF,
                     "Guitar": StemRole.BACKING, "Lead Synth": StemRole.RIGHT}


def test_piano_stem_takes_both_hands(tmp_path):
    stems = {s.name: s.role for s in StemSet.load(_band(tmp_path, with_piano=True)).stems}
    assert stems["Piano"] == StemRole.BOTH
    assert stems["Bass"] == StemRole.BACKING and stems["Lead Synth"] == StemRole.BACKING


def test_combine_assigns_hands_backing_and_shared_timeline(tmp_path):
    song = StemSet.load(_band(tmp_path)).combine()
    assert song.title == "Neon Rain"
    assert {n.hand for n in song.notes if n.pitch == 36} == {Hand.LEFT}
    assert {n.hand for n in song.notes if n.pitch >= 72} == {Hand.RIGHT}
    assert [n.pitch for n in song.backing] == [64] * 8  # guitar heard, not played
    assert len(song.notes) == 16  # drums off
    assert abs(song.duration - 4.0) < 0.01  # 8 beats at 120 BPM


def test_roles_and_options_are_saved_in_the_folder(tmp_path):
    folder = _band(tmp_path)
    stem_set = StemSet.load(folder)
    guitar = next(s for s in stem_set.stems if s.name == "Guitar")
    guitar.role = StemRole.OFF
    stem_set.clean = False
    stem_set.quantize_division = 16
    stem_set.save()
    data = json.loads((folder / "keyfall-stems.json").read_text())
    assert data["roles"]["Guitar.mid"] == "OFF"
    again = StemSet.load(folder)
    assert next(s for s in again.stems if s.name == "Guitar").role == StemRole.OFF
    assert again.clean is False and again.quantize_division == 16
    assert again.combine().backing == []


def test_cleanup_drops_ghosts_and_merges_double_hits():
    notes = [
        NoteEvent(60, 0.00, 0.50, 90),
        NoteEvent(60, 0.02, 0.60, 70),  # double trigger -> merged, extends to 0.62
        NoteEvent(62, 0.50, 0.02, 90),  # too short -> dropped
        NoteEvent(64, 0.60, 0.40, 5),  # too quiet -> dropped
        NoteEvent(60, 1.00, 0.30, 80),  # real repeat -> kept
    ]
    out = cleanup(notes)
    assert [(n.pitch, round(n.start_time, 2), round(n.duration, 2)) for n in out] == [
        (60, 0.0, 0.62), (60, 1.0, 0.3)]


def test_quantize_snaps_to_sixteenth_grid():
    # 120 BPM: 1/16 note = 0.125 s
    out = quantize([NoteEvent(60, 0.13, 0.24, 80)], 120, 16)
    assert (round(out[0].start_time, 3), round(out[0].duration, 3)) == (0.125, 0.25)


class _FakeAudio:
    def __init__(self):
        self.played = []

    def play_note_event(self, note, channel=0):
        self.played.append((note.pitch, channel))


def test_backing_player_plays_once_and_rewinds_on_restart(tmp_path):
    from keyfall.playback import BackingPlayer
    song = StemSet.load(_band(tmp_path)).combine()
    audio = _FakeAudio()
    player = BackingPlayer(song)
    for i in range(1, 9):
        player.update(i * 0.25, audio)
    assert len(audio.played) == 5  # guitar notes at 0, .5, 1, 1.5, 2 s
    assert {ch for _, ch in audio.played} == {BackingPlayer.CHANNEL}
    player.update(0.0, audio)  # restart
    assert len(audio.played) == 6


def test_menu_to_stems_to_game_and_back(tmp_path):
    import pygame

    from keyfall.ui_state import UIState
    from keyfall.views.base import ViewContext, ViewManager
    from keyfall.views.menu_view import MenuView
    from keyfall.views.stems_view import StemsView
    from keyfall.views.waterfall_view import WaterfallView

    pygame.init()
    _band(tmp_path)
    ctx = ViewContext(screen_size=(1280, 720), midi_input=None, audio=None, progress=None,
                      songs_dir=str(tmp_path), ui=UIState(persist=False))
    vm = ViewManager(ctx)
    for cls in (MenuView, StemsView, WaterfallView):
        vm.register(cls)
    vm.push("menu")
    menu = vm.active_view
    assert menu._songs[0].kind == "Stems · 4"

    def key(k):
        vm.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""))

    key(pygame.K_RETURN)
    assert vm.active_view.name == "stems"
    vm.draw(pygame.Surface((1280, 720)))
    key(pygame.K_UP)  # wraps to the Start row
    key(pygame.K_RETURN)
    game = vm.active_view
    assert game.name == "waterfall"
    assert game._engine.song.title == "Neon Rain" and game._engine.song.backing
    key(pygame.K_ESCAPE)
    assert vm.active_view.name == "menu"


def test_stem_label_drops_repeated_song_title(tmp_path):
    from pathlib import Path

    from keyfall.stems import Stem
    assert Stem(Path("Neon Rain (Bass).mid"), [], "Bass").label("Neon Rain") == "Bass"
    assert Stem(Path("bass.mid"), [], "Bass").label("Neon Rain") == "bass"
