"""Starter songs, count-in/metronome, and the results screen."""

import pygame
import pytest

from keyfall import library
from keyfall.models import Hand, NoteEvent, SessionStats, Song, TempoChange
from keyfall.playback import ClickTrack, count_in_seconds
from keyfall.renderer.skins import SKINS, create_skin
from keyfall.renderer.skins.demo import demo_frame
from keyfall.renderer.skins.frames import ResultsFrame, SessionResult
from keyfall.song_loader import load_song
from keyfall.ui_state import UIState
from keyfall.views.base import ViewContext, ViewManager
from keyfall.views.menu_view import MenuView
from keyfall.views.practice_view import PracticeView
from keyfall.views.results_view import ResultsView
from keyfall.views.waterfall_view import WaterfallView

# ------------------------------------------------------------------ starter songs


def test_starter_songs_are_public_domain_and_load():
    songs = sorted(library.STARTER_DIR.glob("*.mid"))
    assert len(songs) == 10
    sources = (library.STARTER_DIR / "SOURCES.md").read_text()
    for path in songs:
        assert path.name in sources
        song = load_song(path)
        assert song.notes and {n.hand for n in song.notes} == {Hand.LEFT, Hand.RIGHT}


def test_songs_folder_created_with_starters_once(tmp_path):
    folder = library.prepare_songs_dir(tmp_path / "Songs")
    assert len(list(folder.glob("*.mid"))) == 10
    (folder / "Joplin - The Entertainer.mid").unlink()
    library.prepare_songs_dir(folder)  # next launch
    assert not (folder / "Joplin - The Entertainer.mid").exists()  # deletion respected


def test_existing_music_folder_is_left_alone(tmp_path):
    (tmp_path / "mine.mid").write_bytes(b"x")
    library.prepare_songs_dir(tmp_path)
    assert [p.name for p in tmp_path.glob("*.mid")] == ["mine.mid"]


def test_default_folder_is_in_home(monkeypatch, tmp_path):
    monkeypatch.setattr(library.Path, "home", lambda: tmp_path)
    assert library.prepare_songs_dir() == tmp_path / "KeyFall" / "Songs"

# ------------------------------------------------------------------ metronome


def _clicks(mode, start=-2.0, end=1.0, beat=0.5, step=0.05):
    track = ClickTrack()
    out = []
    t = start
    while t <= end + 1e-9:
        out += track.update(t, beat, mode)
        t += step
    return out


def test_count_in_is_one_accented_bar():
    assert _clicks("count-in") == [ClickTrack.DOWNBEAT] + [ClickTrack.BEAT] * 3


def test_always_mode_keeps_clicking_and_off_is_silent():
    assert len(_clicks("on")) == 7  # beats -4..2
    assert _clicks("off") == []


def test_restart_replays_the_count_in():
    track = ClickTrack()
    track.update(-2.0, 0.5, "count-in")
    track.update(0.5, 0.5, "count-in")
    assert track.update(-2.0, 0.5, "count-in") == [ClickTrack.DOWNBEAT]  # jumped back


def test_count_in_length_is_one_bar():
    song = Song(tempo_changes=[TempoChange(0.0, 120.0)])
    assert count_in_seconds(song, "count-in") == 2.0
    assert count_in_seconds(song, "off") == 0.0

# ------------------------------------------------------------------ results


def test_trouble_spot_is_worst_two_bar_window():
    result = SessionResult("x", "Play", SessionStats(), miss_bars={2: 1, 5: 3, 6: 2, 9: 4})
    assert result.trouble == (5, 6, 5)
    assert SessionResult("x", "Play", SessionStats()).trouble is None


@pytest.mark.parametrize("name", list(SKINS))
def test_skins_draw_results_and_count_in(name):
    pygame.init()
    skin = create_skin(name)
    surf = pygame.Surface((1280, 720))
    stats = SessionStats(total_notes=40, perfect=30, good=5, ok=1, missed=4, max_streak=22,
                         accuracy_pct=90.0)
    result = SessionResult("Für Elise", "Play", stats, [-30, 5, 12, 40], 85.0, {3: 2, 4: 2})
    skin.draw_results(surf, ResultsFrame(result, ["Play again", "Practice bars 3–4", "Menu"], 1))
    frame = demo_frame()
    frame.count_in = 3
    skin.draw_play(surf, frame)


def _song():
    # 4 bars of quarter notes at 120 BPM; pitch 67 appears only in bar 3 (missed on purpose)
    notes = []
    for i in range(16):
        pitch = 67 if 8 <= i < 12 else 60 + (i % 4)
        notes.append(NoteEvent(pitch, i * 0.5, 0.4, hand=Hand.RIGHT))
    return Song(title="Test Tune", notes=notes, tempo_changes=[TempoChange(0.0, 120.0)],
                duration=8.0)


def test_song_end_shows_results_then_practice_trouble_bars():
    pygame.init()
    ctx = ViewContext(screen_size=(1280, 720), midi_input=None, audio=None, progress=None,
                      ui=UIState(persist=False))
    vm = ViewManager(ctx)
    for cls in (MenuView, WaterfallView, PracticeView, ResultsView):
        vm.register(cls)
    vm.push("menu")
    vm.push("waterfall", song=_song())
    game = vm.active_view
    assert game._engine.position == pytest.approx(-2.0)  # count-in bar
    frame_counts = set()
    for _ in range(60 * 12):
        if vm.active_view is not game:
            break
        eng = game._engine
        t = eng.position
        game._pressed = {n.pitch for n in eng.song.notes
                         if n.start_time <= t < n.start_time + n.duration and n.pitch != 67}
        if t < 0:
            frame_counts.add((t < 0) and -int(-t // 0.5))
        vm.update(1 / 60)
    results = vm.active_view
    assert results.name == "results"
    r = results._result
    assert r.stats.missed == 4 and r.stats.perfect + r.stats.good + r.stats.ok == 12
    assert r.trouble[:2] in ((3, 4), (2, 3))
    assert r.miss_bars == {3: 4}
    vm.draw(pygame.Surface((1280, 720)))
    vm.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p, mod=0, unicode=""))
    practice = vm.active_view
    assert practice.name == "practice" and practice._looping
    assert (practice._section_start, practice._section_end) == r.trouble[:2]
    assert {n.pitch for n in practice._engine.song.notes} >= {67}
    vm.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    assert vm.active_view.name == "menu"
