"""Drawing primitives shared by all skins: gradients, rounded cards, glow, text."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pygame

Color = tuple[int, int, int]


def hex_color(value: str) -> Color:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def mix(a: Color, b: Color, t: float) -> Color:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


@lru_cache(maxsize=256)
def vgradient(size: tuple[int, int], top: Color, bottom: Color) -> pygame.Surface:
    """Vertical gradient surface (cached; do not draw onto the result)."""
    w, h = max(1, size[0]), max(1, size[1])
    t = np.linspace(0.0, 1.0, h)[None, :, None]
    arr = np.array(top)[None, None, :] * (1 - t) + np.array(bottom)[None, None, :] * t
    arr = np.repeat(arr, w, axis=0).astype(np.uint8)
    return pygame.surfarray.make_surface(arr)


@lru_cache(maxsize=64)
def _strip(top: Color, bottom: Color) -> pygame.Surface:
    return vgradient((1, 256), top, bottom)


def stretched_gradient(size: tuple[int, int], top: Color, bottom: Color) -> pygame.Surface:
    """Vertical gradient for sizes that change every frame (falling notes).

    Scales a cached 256px strip instead of building a new array per size.
    """
    return pygame.transform.scale(_strip(top, bottom), (max(1, size[0]), max(1, size[1])))


@lru_cache(maxsize=16)
def radial(size: tuple[int, int], center: tuple[int, int], radius: float, color: Color,
           strength: float = 1.0) -> pygame.Surface:
    """Soft radial light blob, meant to be added with BLEND_RGB_ADD."""
    w, h = size
    xs = np.arange(w)[:, None]
    ys = np.arange(h)[None, :]
    d = np.sqrt((xs - center[0]) ** 2 + (ys - center[1]) ** 2) / radius
    f = np.clip(1 - d, 0, 1) ** 2 * strength
    arr = (f[:, :, None] * np.array(color)[None, None, :]).astype(np.uint8)
    return pygame.surfarray.make_surface(arr)


def rrect(surf: pygame.Surface, color, rect, radius: int = 8, alpha: int | None = None,
          width: int = 0) -> None:
    """Rounded rectangle, optionally translucent."""
    rect = pygame.Rect(rect)
    if rect.w <= 0 or rect.h <= 0:
        return
    if alpha is None:
        pygame.draw.rect(surf, color, rect, width=width, border_radius=radius)
        return
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(layer, (*color[:3], alpha), layer.get_rect(), width=width,
                     border_radius=radius)
    surf.blit(layer, rect.topleft)


def blit_rounded(dst: pygame.Surface, src: pygame.Surface, pos, radius: int) -> None:
    """Blit ``src`` clipped to a rounded rectangle."""
    card = pygame.Surface(src.get_size(), pygame.SRCALPHA)
    card.blit(src, (0, 0))
    mask = pygame.Surface(src.get_size(), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    card.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    dst.blit(card, pos)


def gradient_rect(surf: pygame.Surface, rect, top: Color, bottom: Color, radius: int = 0) -> None:
    rect = pygame.Rect(rect)
    if rect.w <= 0 or rect.h <= 0:
        return
    grad = vgradient(rect.size, top, bottom)
    if radius:
        blit_rounded(surf, grad, rect.topleft, radius)
    else:
        surf.blit(grad, rect.topleft)


def glow(target: pygame.Surface, layer: pygame.Surface, scale: float = 0.125,
         passes: int = 1) -> None:
    """Blur ``layer`` (black = transparent) by down/up-scaling and add it onto ``target``."""
    w, h = layer.get_size()
    small_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    blurred = pygame.transform.smoothscale(layer, small_size)
    for _ in range(passes - 1):
        tiny = pygame.transform.smoothscale(blurred, (max(1, small_size[0] // 2),
                                                      max(1, small_size[1] // 2)))
        blurred = pygame.transform.smoothscale(tiny, small_size)
    target.blit(pygame.transform.smoothscale(blurred, (w, h)), (0, 0),
                special_flags=pygame.BLEND_RGB_ADD)


def text(surf: pygame.Surface, font: pygame.font.Font, s: str, color, pos,
         anchor: str = "topleft", alpha: int = 255) -> pygame.Rect:
    img = font.render(s, True, color)
    if alpha < 255:
        img.set_alpha(alpha)
    rect = img.get_rect(**{anchor: pos})
    surf.blit(img, rect)
    return rect


def tracked(surf: pygame.Surface, font: pygame.font.Font, s: str, color, pos,
            spacing: int = 2, anchor: str = "topleft") -> pygame.Rect:
    """Letter-spaced text, for small all-caps labels."""
    glyphs = [font.render(ch, True, color) for ch in s]
    width = sum(g.get_width() for g in glyphs) + spacing * max(0, len(s) - 1)
    rect = pygame.Rect(0, 0, width, max((g.get_height() for g in glyphs), default=0))
    setattr(rect, anchor, pos)
    x = rect.x
    for g in glyphs:
        surf.blit(g, (x, rect.y))
        x += g.get_width() + spacing
    return rect


def chevron(surf: pygame.Surface, color, center, size: int = 5, direction: str = "down",
            width: int = 2) -> None:
    x, y = center
    pts = {
        "down": [(x - size, y - size / 2), (x, y + size / 2), (x + size, y - size / 2)],
        "up": [(x - size, y + size / 2), (x, y - size / 2), (x + size, y + size / 2)],
        "left": [(x + size / 2, y - size), (x - size / 2, y), (x + size / 2, y + size)],
        "right": [(x - size / 2, y - size), (x + size / 2, y), (x - size / 2, y + size)],
    }[direction]
    pygame.draw.lines(surf, color, False, pts, width)


def shadow(surf: pygame.Surface, rect, radius: int = 12, alpha: int = 90) -> None:
    rect = pygame.Rect(rect)
    pad = 24
    layer = pygame.Surface((rect.w + pad * 2, rect.h + pad * 2), pygame.SRCALPHA)
    pygame.draw.rect(layer, (0, 0, 0, alpha), (pad, pad + 6, rect.w, rect.h), border_radius=radius)
    small = pygame.transform.smoothscale(layer, (max(1, layer.get_width() // 6),
                                                 max(1, layer.get_height() // 6)))
    surf.blit(pygame.transform.smoothscale(small, layer.get_size()), (rect.x - pad, rect.y - pad))


def star(surf: pygame.Surface, color, center, r: float) -> None:
    import math
    cx, cy = center
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    pygame.draw.polygon(surf, color, pts)
