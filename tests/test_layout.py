"""Sheet music position: above the falling notes (default) or below the piano."""

import numpy as np
import pygame
import pytest

from keyfall import accessibility, settings
from keyfall.renderer.skins import SKINS, create_skin
from keyfall.renderer.skins.demo import demo_frame, demo_song
from keyfall.ui_state import UIState
from keyfall.views.base import ViewContext, ViewManager
from keyfall.views.settings_view import ROW_LAYOUT, ROW_NOTATION, SettingsView
from keyfall.views.waterfall_view import WaterfallView

SIZE = (1280, 720)


def _key_rows(surface):
    """Screen rows that look like white piano keys (mostly light pixels)."""
    arr = pygame.surfarray.array3d(surface).astype(int)  # (w, h, 3)
    light = (arr.min(axis=2) > 200).mean(axis=0)  # share of light pixels per row
    return np.nonzero(light > 0.6)[0]


@pytest.mark.parametrize("name", list(SKINS))
def test_piano_stays_at_the_bottom_with_notes_falling(name):
    pygame.init()
    skin = create_skin(name)
    for below, sheet in ((False, False), (False, True), (True, True)):
        surf = pygame.Surface(SIZE)
        frame = demo_frame(demo_song())
        frame.sheet_below, frame.show_notation = below, sheet
        skin.draw_play(surf, frame)
        rows = _key_rows(surf)
        assert len(rows), (name, below, sheet)
        assert rows.min() > SIZE[1] // 2, (name, below, sheet)  # piano in the lower half
        if below:
            assert rows.max() < SIZE[1] - 140, name  # sheet music fills the strip under it
        else:
            assert rows.max() >= SIZE[1] - 5, name  # piano reaches the bottom edge


@pytest.mark.parametrize("name", list(SKINS))
def test_sheet_below_draws_every_overlay(name):
    pygame.init()
    skin = create_skin(name, accessibility=accessibility.AccessibilitySettings(
        note_labels="NOTE_NAME"))
    frame = demo_frame(demo_song())
    frame.sheet_below = frame.show_notation = frame.paused = True
    frame.count_in = 2
    frame.loop = (3, 4)
    skin.draw_play(pygame.Surface(SIZE), frame)


def test_old_saved_layouts_are_migrated(tmp_path):
    path = tmp_path / "s.json"
    path.write_text('{"appearance": {"layout": "rising"}}')
    assert settings.load_appearance(path).layout == "below"
    path.write_text('{"appearance": {"layout": "falling"}}')
    assert settings.load_appearance(path).layout == "above"


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    monkeypatch.setattr(accessibility, "_SETTINGS_PATH", tmp_path / "s.json")
    pygame.init()
    return ViewContext(screen_size=SIZE, midi_input=None, audio=None, progress=None,
                       ui=UIState())


def test_settings_rows_move_sheet_music_and_show_it_in_play(ctx):
    vm = ViewManager(ctx)
    vm.register(SettingsView)
    vm.push("settings")
    view = vm.active_view
    view.change(ROW_LAYOUT, 1)
    view.change(ROW_NOTATION, 1)
    assert (ctx.ui.appearance.layout, ctx.ui.appearance.notation) == ("below", "always")
    saved = settings.load_appearance()
    assert (saved.layout, saved.notation) == ("below", "always")
    vm.draw(pygame.Surface(SIZE))  # preview shows the sheet music under the piano


def test_play_mode_sheet_music_follows_setting_and_n_toggles(ctx):
    ctx.ui.appearance.notation = "always"
    ctx.ui.appearance.layout = "below"
    vm = ViewManager(ctx)
    vm.register(WaterfallView)
    vm.push("waterfall", song=demo_song())
    view = vm.active_view
    assert view._show_notation
    vm.draw(pygame.Surface(SIZE))
    vm.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_n, mod=0, unicode=""))
    assert not view._show_notation
    ctx.ui.appearance.notation = "practice"
    vm.push("waterfall", song=demo_song())
    assert not vm.active_view._show_notation  # Play hides it unless "Play and Practice"
