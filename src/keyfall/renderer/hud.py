"""Heads-up display — score, streak, accuracy."""

from __future__ import annotations

import pygame

from keyfall.models import SessionStats
from keyfall.renderer.colors import HUD_TEXT


def render_hud(surface: pygame.Surface, stats: SessionStats) -> None:
    font = pygame.font.SysFont("monospace", 20)

    lines = [
        f"Score: {stats.perfect * 3 + stats.good * 2 + stats.ok}",
        f"Streak: {stats.max_streak}",
        f"Accuracy: {stats.accuracy_pct:.0f}%",
    ]

    y = 10
    for line in lines:
        text = font.render(line, True, HUD_TEXT)
        surface.blit(text, (10, y))
        y += 28
