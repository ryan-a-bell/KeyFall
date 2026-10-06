"""Screen layout: notes falling onto a piano at the bottom, or rising to one on top."""

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
def test_keyboard_moves_to_the_top_when_rising(name):
    pygame.init()
    skin = create_skin(name)
    for rising, sheet in ((False, False), (True, False), (True, True)):
        surf = pygame.Surface(SIZE)
        frame = demo_frame(demo_song())
        frame.rising, frame.show_notation = rising, sheet
        skin.draw_play(surf, frame)
        rows = _key_rows(surf)
        assert len(rows), (name, rising)
        if rising:
            assert rows.max() < SIZE[1] // 2, (name, sheet)  # piano in the upper half
        else:
            assert rows.min() > SIZE[1] // 2, name  # piano in the lower half


@pytest.mark.parametrize("name", list(SKINS))
def test_rising_draws_every_overlay(name):
    pygame.init()
    skin = create_skin(name, accessibility=accessibility.AccessibilitySettings(
        note_labels="NOTE_NAME"))
    surf = pygame.Surface(SIZE)
    frame = demo_frame(demo_song())
    frame.rising = frame.show_notation = frame.paused = True
    frame.count_in = 2
    frame.loop = (3, 4)
    skin.draw_play(surf, frame)
    assert skin._deferred is None  # held-back field text was drawn and released


def test_flip_rect_and_text_anchor_swap():
    pygame.init()
    skin = create_skin("studio")
    field = pygame.Rect(0, 234, 1280, 486)  # under top bar + sheet music
    assert skin.flip_rect(pygame.Rect(0, 234, 1280, 100), field, 64) == pygame.Rect(
        0, 64 + 386, 1280, 100)
    surf = pygame.Surface(SIZE)
    buf = skin.begin_field(surf, True)
    font = pygame.font.Font(None, 20)
    skin.field_text(buf, font, "C4", (255, 255, 255), (100, 700), "topleft")
    assert skin._deferred == [(font, "C4", (255, 255, 255), (100, 700), "topleft")]
    skin.end_field(surf, buf, field, 64)
    assert skin._deferred is None


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    monkeypatch.setattr(accessibility, "_SETTINGS_PATH", tmp_path / "s.json")
    pygame.init()
    return ViewContext(screen_size=SIZE, midi_input=None, audio=None, progress=None,
                       ui=UIState())


def test_settings_rows_switch_layout_and_sheet_music(ctx):
    vm = ViewManager(ctx)
    vm.register(SettingsView)
    vm.push("settings")
    view = vm.active_view
    view.change(ROW_LAYOUT, 1)
    view.change(ROW_NOTATION, 1)
    assert (ctx.ui.appearance.layout, ctx.ui.appearance.notation) == ("rising", "always")
    saved = settings.load_appearance()
    assert (saved.layout, saved.notation) == ("rising", "always")
    vm.draw(pygame.Surface(SIZE))  # preview renders the rising layout with sheet music


def test_play_mode_sheet_music_follows_setting_and_n_toggles(ctx):
    ctx.ui.appearance.notation = "always"
    ctx.ui.appearance.layout = "rising"
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
