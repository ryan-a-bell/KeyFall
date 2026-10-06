"""Themes, skins, settings persistence, and the Settings screen."""

import time

import pygame
import pytest

from keyfall import accessibility, settings
from keyfall.accessibility import AccessibilitySettings, NoteLabelMode
from keyfall.renderer import fonts
from keyfall.renderer.skins import SKINS, create_skin
from keyfall.renderer.skins.demo import demo_frame, demo_song
from keyfall.renderer.skins.frames import (
    FreePlayFrame,
    MenuFrame,
    MenuSong,
    SettingsFrame,
    SettingsRow,
    SongDetails,
)
from keyfall.ui_state import UIState
from keyfall.views.base import ViewContext, ViewManager
from keyfall.views.menu_view import MenuView
from keyfall.views.settings_view import SettingsView

SIZE = (1280, 720)


@pytest.fixture(autouse=True)
def _pygame(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(accessibility, "_SETTINGS_PATH", tmp_path / "settings.json")
    pygame.init()
    yield


def _menu_frame():
    songs = [MenuSong("Für Elise", "MIDI", 96.0), MenuSong("Clair de Lune", "MusicXML"),
             MenuSong("A very long song title that keeps going and going", "MIDI", 71.0)]
    return MenuFrame(songs=songs, selected=1, modes=["Play", "Practice", "Free Play"], mode=0,
                     hand_split="Auto", audio_status="Sound: YDP.sf2", midi_status="Connected",
                     midi_connected=True, sound_ok=True,
                     details=SongDetails(200.0, 900, 7, "Intermediate"))


@pytest.mark.parametrize("name", list(SKINS))
@pytest.mark.parametrize("effects", ["full", "reduced", "off"])
def test_every_skin_draws_every_screen(name, effects):
    skin = create_skin(name, effects, AccessibilitySettings(note_labels="NOTE_NAME"))
    surf = pygame.Surface(SIZE)
    frame = demo_frame(label_mode=NoteLabelMode.NOTE_NAME)
    skin.draw_play(surf, frame)
    frame.paused = True
    frame.show_notation = True
    frame.loop = (2, 4)
    skin.draw_play(surf, frame)
    skin.draw_menu(surf, _menu_frame())
    empty = _menu_frame()
    empty.songs, empty.selected, empty.details = [], 0, None
    skin.draw_menu(surf, empty)
    skin.draw_settings(surf, SettingsFrame(rows=[SettingsRow("Theme", "Studio", "x")],
                                           selected=0, preview=pygame.Surface(SIZE)))
    skin.draw_freeplay(surf, FreePlayFrame({60, 64, 67}, "C", ["Am", "F"], True))


def test_skins_look_different():
    frame = demo_frame()
    shots = {}
    for name in SKINS:
        surf = pygame.Surface(SIZE)
        create_skin(name).draw_play(surf, frame)
        shots[name] = pygame.image.tobytes(surf, "RGB")
    assert len(set(shots.values())) == len(SKINS)


def test_colorblind_palette_overrides_theme_hand_colors():
    skin = create_skin("neon", accessibility=AccessibilitySettings(color_palette="TRITANOPIA"))
    assert (skin.right, skin.left) == accessibility.PALETTE_COLORS[
        accessibility.ColorPalette.TRITANOPIA][:2]
    default = create_skin("neon")
    assert default.right == default.theme.palette.right


def test_unknown_theme_falls_back_to_default():
    assert type(create_skin("nope")).__name__ == "StudioSkin"


def test_bundled_fonts_load():
    for family in ("inter", "orbitron", "rajdhani"):
        assert (fonts.FONT_DIR / f"{family}-700.woff").exists()
        assert fonts.get(family, 700, 20).size("Hi")[0] > 0


def test_appearance_saved_without_clobbering_accessibility(tmp_path):
    path = tmp_path / "settings.json"
    accessibility.save_settings(AccessibilitySettings(color_palette="PROTANOPIA"))
    settings.save_appearance(settings.AppearanceSettings(theme="neon", effects="reduced"))
    assert settings.load_appearance().theme == "neon"
    assert settings.load_appearance().effects == "reduced"
    assert accessibility.load_settings().color_palette == "PROTANOPIA"
    path.write_text("not json")
    assert settings.load_appearance() == settings.AppearanceSettings()


def _manager(ui):
    ctx = ViewContext(screen_size=SIZE, midi_input=None, audio=None, progress=None, ui=ui)
    vm = ViewManager(ctx)
    for cls in (MenuView, SettingsView):
        vm.register(cls)
    vm.push("menu")
    return vm


def _key(vm, key):
    vm.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))


def test_settings_screen_switches_theme_everywhere_and_saves():
    ui = UIState()
    vm = _manager(ui)
    _key(vm, pygame.K_s)
    assert vm.active_view.name == "settings"
    _key(vm, pygame.K_RIGHT)  # studio -> neon
    assert ui.appearance.theme == "neon"
    assert type(ui.skin).__name__ == "NeonSkin"
    vm.draw(pygame.Surface(SIZE))
    _key(vm, pygame.K_DOWN)
    _key(vm, pygame.K_DOWN)
    _key(vm, pygame.K_RIGHT)  # note labels: letters
    assert ui.accessibility.get_label_mode() == NoteLabelMode.NOTE_NAME
    _key(vm, pygame.K_ESCAPE)
    assert vm.active_view.name == "menu"
    # the menu (a different view with its own context copy) sees the new skin
    assert type(vm.active_view._context.skin).__name__ == "NeonSkin"
    assert settings.load_appearance().theme == "neon"
    assert accessibility.load_settings().note_labels == "NOTE_NAME"


def test_neon_frame_time_budget():
    """Full-effects Neon must stay well within a 60 fps frame on the demo song."""
    skin = create_skin("neon", "full")
    surf = pygame.Surface(SIZE)
    song = demo_song()
    skin.draw_play(surf, demo_frame(song))  # warm caches
    start = time.perf_counter()
    for i in range(30):
        skin.draw_play(surf, demo_frame(song, position=5.0 + i / 60))
    per_frame_ms = (time.perf_counter() - start) / 30 * 1000
    assert per_frame_ms < 33, f"{per_frame_ms:.1f} ms per frame"
