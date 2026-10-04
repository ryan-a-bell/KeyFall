"""Top-level application: initializes pygame, manages screens, and runs the game loop."""

from __future__ import annotations

import pygame

from keyfall.config import FPS, WINDOW_HEIGHT, WINDOW_TITLE, WINDOW_WIDTH
from keyfall.midi_input import KeyboardInput
from keyfall.views.base import ViewContext, ViewManager
from keyfall.views.freeplay_view import FreePlayView
from keyfall.views.menu_view import MenuView
from keyfall.views.practice_view import PracticeView
from keyfall.views.waterfall_view import WaterfallView


class App:
    def __init__(self, songs_dir: str = "", soundfont: str | None = None) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(WINDOW_TITLE)
        self.clock = pygame.time.Clock()

        # Build shared context — optional subsystems gracefully degrade
        midi_input = self._try_midi()
        audio, audio_status = self._try_audio(soundfont)
        progress = self._try_progress()
        plugin_manager = self._try_plugins()
        self._keyboard_input = KeyboardInput()

        context = ViewContext(
            screen_size=(WINDOW_WIDTH, WINDOW_HEIGHT),
            midi_input=midi_input,
            audio=audio,
            progress=progress,
            plugin_manager=plugin_manager,
            keyboard_input=self._keyboard_input,
            songs_dir=songs_dir,
            audio_status=audio_status,
        )

        self.views = ViewManager(context)

        # Register built-in views
        self.views.register(MenuView)
        self.views.register(WaterfallView)
        self.views.register(PracticeView)
        self.views.register(FreePlayView)

        # Register plugin views
        if plugin_manager:
            for view_cls in plugin_manager.get_view_plugins():
                self.views.register(view_cls)

        # Start on the menu
        self.views.push("menu")

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    self._keyboard_input.feed_event(event)
                    if not self.views.handle_event(event):
                        running = False
            if running:
                if not self.views.update(dt):
                    running = False
            self.views.draw(self.screen)
            pygame.display.flip()

        self._cleanup()
        pygame.quit()

    def _cleanup(self) -> None:
        while self.views.active_view:
            self.views.pop()

    @staticmethod
    def _try_midi():
        try:
            from keyfall.midi_input import MidiInput
            mi = MidiInput()
            mi.open()
            return mi
        except Exception:
            return None

    @staticmethod
    def _try_audio(soundfont: str | None = None):
        """Return (AudioEngine or None, human-readable status for the menu)."""
        try:
            from keyfall.soundfont import find_soundfont
            path = find_soundfont(soundfont)
            if path is None:
                return None, "Sound: off (no SoundFont; run `keyfall --download-soundfont`)"
            from keyfall.audio import AudioEngine
            return AudioEngine(path), f"Sound: {path.name}"
        except Exception as exc:
            return None, f"Sound: off ({exc})"

    @staticmethod
    def _try_progress():
        try:
            from keyfall.progress import ProgressTracker
            return ProgressTracker()
        except Exception:
            return None

    @staticmethod
    def _try_plugins():
        try:
            from keyfall.plugins.manager import PluginManager
            pm = PluginManager()
            pm.discover()
            return pm
        except Exception:
            return None
