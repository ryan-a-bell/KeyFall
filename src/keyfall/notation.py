"""Optional sheet music notation rendering (stub for future expansion)."""

from __future__ import annotations

import pygame

from keyfall.models import Song


def render_notation(
    surface: pygame.Surface,
    song: Song,
    playback_position: float,
    x: int = 0,
    y: int = 0,
    width: int = 400,
    height: int = 200,
) -> None:
    """Render a simplified staff notation view. Placeholder for full implementation."""
    # Draw staff lines
    staff_color = (80, 80, 100)
    for i in range(5):
        ly = y + 40 + i * 15
        pygame.draw.line(surface, staff_color, (x + 10, ly), (x + width - 10, ly))
