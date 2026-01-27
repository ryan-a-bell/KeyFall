"""Top-level application: initializes pygame, manages screens, and runs the game loop."""

import pygame

from keyfall.config import WINDOW_WIDTH, WINDOW_HEIGHT, FPS, WINDOW_TITLE


class App:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(WINDOW_TITLE)
        self.clock = pygame.time.Clock()
        self.running = True

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self._handle_events()
            self._update(dt)
            self._draw()
        pygame.quit()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

    def _update(self, dt: float) -> None:
        pass

    def _draw(self) -> None:
        self.screen.fill((18, 18, 24))
        pygame.display.flip()
