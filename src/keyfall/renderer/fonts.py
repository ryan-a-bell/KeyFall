"""Bundled font loading with caching and a system-font fallback.

Fonts live in ``keyfall/assets/fonts`` (SIL Open Font License, see OFL-*.txt).
Family "mono" always uses the system monospace font (the Classic look).
"""

from __future__ import annotations

from pathlib import Path

import pygame

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# family -> available weights (files are named "<family>-<weight>.woff")
_WEIGHTS: dict[str, tuple[int, ...]] = {
    "inter": (400, 500, 600, 700, 800),
    "orbitron": (500, 700, 900),
    "rajdhani": (500, 600, 700),
}

_cache: dict[tuple[str, int, int], pygame.font.Font] = {}


def _nearest(weights: tuple[int, ...], weight: int) -> int:
    return min(weights, key=lambda w: abs(w - weight))


def get(family: str, weight: int, size: int) -> pygame.font.Font:
    """Return a cached font. Falls back to the system sans/mono font if missing."""
    key = (family, weight, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    if not pygame.font.get_init():
        pygame.font.init()

    font: pygame.font.Font | None = None
    if family in _WEIGHTS:
        path = FONT_DIR / f"{family}-{_nearest(_WEIGHTS[family], weight)}.woff"
        try:
            font = pygame.font.Font(str(path), size)
        except (OSError, FileNotFoundError):
            font = None
    if font is None:
        sys_name = "monospace" if family == "mono" else "dejavusans,freesans,arial"
        font = pygame.font.SysFont(sys_name, size, bold=weight >= 600)
    _cache[key] = font
    return font
