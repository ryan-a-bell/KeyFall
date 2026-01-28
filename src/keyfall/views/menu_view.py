"""Main menu and song picker view."""

from __future__ import annotations

from pathlib import Path

import pygame

from keyfall.renderer import colors as colors_mod
from keyfall.song_loader import load_song
from keyfall.views.base import ViewAction, ViewContext


class MenuView:
    name = "menu"
    display_name = "Main Menu"

    def __init__(self) -> None:
        self._context: ViewContext | None = None
        self._song_files: list[Path] = []
        self._selected: int = 0
        self._mode: int = 0  # 0=Play, 1=Practice, 2=Free Play
        self._modes = ["Play", "Practice", "Free Play"]
        self._mode_targets = ["waterfall", "practice", "freeplay"]
        self._font: pygame.font.Font | None = None
        self._title_font: pygame.font.Font | None = None

    def on_enter(self, context: ViewContext) -> None:
        self._context = context
        self._font = pygame.font.SysFont("monospace", 20)
        self._title_font = pygame.font.SysFont("monospace", 36)
        self._scan_songs()

    def on_exit(self) -> None:
        pass

    def _scan_songs(self) -> None:
        self._song_files = []
        if not self._context or not self._context.songs_dir:
            return
        songs_path = Path(self._context.songs_dir)
        if songs_path.is_dir():
            for ext in ("*.mid", "*.midi", "*.musicxml", "*.xml"):
                self._song_files.extend(sorted(songs_path.glob(ext)))

    def handle_event(self, event: pygame.event.Event) -> ViewAction | None:
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_ESCAPE:
            return ViewAction(kind="quit")

        if event.key == pygame.K_UP:
            self._selected = max(0, self._selected - 1)
        elif event.key == pygame.K_DOWN:
            self._selected = min(len(self._song_files) - 1, self._selected + 1) if self._song_files else 0
        elif event.key == pygame.K_TAB:
            self._mode = (self._mode + 1) % len(self._modes)
        elif event.key == pygame.K_RETURN:
            return self._launch()

        return None

    def _launch(self) -> ViewAction | None:
        target = self._mode_targets[self._mode]

        if target == "freeplay":
            return ViewAction(kind="switch", target="freeplay")

        if not self._song_files:
            return None

        song_path = self._song_files[self._selected]
        try:
            song = load_song(str(song_path))
        except Exception:
            return None

        return ViewAction(
            kind="switch",
            target=target,
            context_patch={"song": song},
        )

    def update(self, dt: float) -> ViewAction | None:
        return None

    def draw(self, surface: pygame.Surface) -> None:
        if not self._font or not self._title_font:
            return

        surface.fill(colors_mod.BG)
        w, h = surface.get_size()

        # Title
        title = self._title_font.render("KeyFall", True, colors_mod.NOTE_PERFECT)
        surface.blit(title, (w // 2 - title.get_width() // 2, 30))

        # Mode selector
        mode_text = self._font.render(
            f"Mode: < {self._modes[self._mode]} >  (Tab to cycle)", True, colors_mod.NOTE_RIGHT_HAND
        )
        surface.blit(mode_text, (40, 90))

        # Song list
        if self._song_files:
            header = self._font.render("Songs:", True, colors_mod.HUD_TEXT)
            surface.blit(header, (40, 140))

            y = 175
            for i, path in enumerate(self._song_files):
                prefix = "> " if i == self._selected else "  "
                color = colors_mod.NOTE_PERFECT if i == self._selected else colors_mod.HUD_TEXT
                text = self._font.render(f"{prefix}{path.stem}", True, color)
                surface.blit(text, (40, y))
                y += 28
                if y > h - 80:
                    break
        else:
            no_songs = self._font.render("No songs found. Set songs_dir in config.", True, (180, 80, 80))
            surface.blit(no_songs, (40, 160))

        # Controls legend
        legend = self._font.render("Up/Down: select | Enter: launch | Tab: mode | Esc: quit", True, (120, 120, 140))
        surface.blit(legend, (40, h - 40))
