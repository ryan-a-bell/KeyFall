"""Render UI style mockups with pygame (the engine KeyFall already uses).

Two directions, each with a menu and a gameplay screen:
  A. "Studio": modern, professional, calm
  B. "Neon Arcade": modern rhythm-game feel

Usage:
    python docs/mockups/style_mockups.py FONTS_DIR OUT_DIR

FONTS_DIR must contain (all SIL Open Font License, from Google Fonts / Fontsource):
    inter-{400,500,600,700,800}.woff, orbitron-{500,700,900}.woff,
    Rajdhani-{Medium,SemiBold,Bold}.ttf
"""

from __future__ import annotations

import math
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np  # noqa: E402
import pygame  # noqa: E402

W, H = 1280, 720
FONTS = sys.argv[1] if len(sys.argv) > 1 else "fonts"
OUT = sys.argv[2] if len(sys.argv) > 2 else "."

pygame.init()
pygame.display.set_mode((1, 1))
_font_cache: dict[tuple[str, int], pygame.font.Font] = {}


def font(name: str, size: int) -> pygame.font.Font:
    key = (name, size)
    if key not in _font_cache:
        _font_cache[key] = pygame.font.Font(os.path.join(FONTS, name), size)
    return _font_cache[key]


def inter(weight: int, size: int) -> pygame.font.Font:
    return font(f"inter-{weight}.woff", size)


def orbitron(weight: int, size: int) -> pygame.font.Font:
    return font(f"orbitron-{weight}.woff", size)


def rajdhani(style: str, size: int) -> pygame.font.Font:
    return font(f"Rajdhani-{style}.ttf", size)


# --------------------------------------------------------------------------- helpers


def hex2rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def mix(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vgradient(size, top, bottom) -> pygame.Surface:
    w, h = size
    t = np.linspace(0.0, 1.0, h)[None, :, None]
    arr = np.array(top)[None, None, :] * (1 - t) + np.array(bottom)[None, None, :] * t
    arr = np.repeat(arr, w, axis=0).astype(np.uint8)
    return pygame.surfarray.make_surface(arr)


def radial(size, center, radius, color, strength=1.0) -> pygame.Surface:
    """Additive radial light blob."""
    w, h = size
    xs = np.arange(w)[:, None]
    ys = np.arange(h)[None, :]
    d = np.sqrt((xs - center[0]) ** 2 + (ys - center[1]) ** 2) / radius
    f = np.clip(1 - d, 0, 1) ** 2 * strength
    arr = (f[:, :, None] * np.array(color)[None, None, :]).astype(np.uint8)
    return pygame.surfarray.make_surface(arr)


def rrect(surf, color, rect, radius=8, alpha=None, width=0):
    rect = pygame.Rect(rect)
    if alpha is None and len(color) == 3:
        pygame.draw.rect(surf, color, rect, width=width, border_radius=radius)
        return
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    c = (*color[:3], alpha if alpha is not None else color[3])
    pygame.draw.rect(layer, c, layer.get_rect(), width=width, border_radius=radius)
    surf.blit(layer, rect.topleft)


def blit_rounded(dst, src, pos, radius):
    """Blit `src` with rounded corners."""
    card = pygame.Surface(src.get_size(), pygame.SRCALPHA)
    card.blit(src, (0, 0))
    mask = pygame.Surface(src.get_size(), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    card.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    dst.blit(card, pos)


def chevron(surf, color, center, size=4, down=True, width=2):
    x, y = center
    d = size if down else -size
    pygame.draw.lines(
        surf, color, False, [(x - size, y - d / 2), (x, y + d / 2), (x + size, y - d / 2)], width
    )


def text(surf, fnt, s, color, pos, anchor="topleft", alpha=255):
    img = fnt.render(s, True, color)
    if alpha < 255:
        img.set_alpha(alpha)
    r = img.get_rect(**{anchor: pos})
    surf.blit(img, r)
    return r


def tracked(surf, fnt, s, color, pos, spacing=2, anchor="topleft"):
    """Letter-spaced text (for small caps labels)."""
    glyphs = [fnt.render(ch, True, color) for ch in s]
    width = sum(g.get_width() for g in glyphs) + spacing * (len(s) - 1)
    height = max(g.get_height() for g in glyphs)
    r = pygame.Rect(0, 0, width, height)
    setattr(r, anchor, pos)
    x = r.x
    for g in glyphs:
        surf.blit(g, (x, r.y))
        x += g.get_width() + spacing
    return r


def glow(target, layer, scale=0.12, passes=2):
    """Blur `layer` (black background) and add it onto `target`."""
    w, h = layer.get_size()
    blurred = layer
    for _ in range(passes):
        small = pygame.transform.smoothscale(
            blurred, (max(1, int(w * scale)), max(1, int(h * scale)))
        )
        blurred = pygame.transform.smoothscale(small, (w, h))
    target.blit(blurred, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def shadow(surf, rect, radius=12, spread=18, alpha=90):
    rect = pygame.Rect(rect)
    layer = pygame.Surface((rect.w + spread * 4, rect.h + spread * 4), pygame.SRCALPHA)
    pygame.draw.rect(
        layer, (0, 0, 0, alpha), (spread * 2, spread * 2 + 6, rect.w, rect.h), border_radius=radius
    )
    small = pygame.transform.smoothscale(layer, (layer.get_width() // 6, layer.get_height() // 6))
    layer = pygame.transform.smoothscale(small, layer.get_size())
    surf.blit(layer, (rect.x - spread * 2, rect.y - spread * 2))


# --------------------------------------------------------------------------- keyboard + song

BLACK = {1, 3, 6, 8, 10}
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def is_black(p):
    return p % 12 in BLACK


def note_name(p):
    return f"{NAMES[p % 12]}{p // 12 - 1}"


class Keys:
    """Keyboard geometry for a pitch range spread across a width."""

    def __init__(self, lo, hi, x0, width, y, height):
        self.lo, self.hi, self.y, self.h = lo, hi, y, height
        whites = [p for p in range(lo, hi + 1) if not is_black(p)]
        self.ww = width / len(whites)
        self.bw = self.ww * 0.6
        self.x = {}
        i = 0
        for p in range(lo, hi + 1):
            if is_black(p):
                self.x[p] = x0 + i * self.ww - self.bw / 2
            else:
                self.x[p] = x0 + i * self.ww
                i += 1

    def rect(self, p):
        if is_black(p):
            return pygame.Rect(round(self.x[p]), self.y, round(self.bw), int(self.h * 0.62))
        return pygame.Rect(round(self.x[p]), self.y, round(self.ww), self.h)

    def lane(self, p):
        """(x, width) of the falling-note lane for a pitch."""
        if is_black(p):
            return self.x[p] + 1, self.bw - 2
        return self.x[p] + 2, self.ww - 4


def make_song():
    """A two-hand passage in A minor with a C-major lift: melody RH, broken chords LH."""
    notes = []  # (pitch, start, dur, hand)
    beat = 0.42
    melody = [
        76,
        79,
        81,
        79,
        76,
        74,
        72,
        74,
        76,
        81,
        84,
        83,
        81,
        79,
        77,
        76,
        74,
        76,
        77,
        79,
        81,
        79,
        77,
        76,
        74,
        72,
        71,
        72,
        74,
        76,
        79,
        81,
    ]
    lens = [
        1,
        1,
        2,
        1,
        1,
        1,
        1,
        2,
        1,
        1,
        2,
        1,
        1,
        1,
        1,
        2,
        1,
        1,
        1,
        1,
        2,
        1,
        1,
        1,
        1,
        1,
        1,
        1,
        1,
        1,
        2,
        2,
    ]
    t = 0.0
    for p, n in zip(melody, lens):
        notes.append((p, t, n * beat * 0.95, "R"))
        if n == 2 and p > 78:
            notes.append((p - 4, t, n * beat * 0.95, "R"))
        t += n * beat
    chords = [(45, 52, 57, 60), (41, 48, 53, 57), (48, 55, 60, 64), (43, 50, 55, 59)] * 3
    t = 0.0
    for root, a, b, c in chords:
        for i, p in enumerate((root, a, b, a)):
            notes.append((p, t + i * beat, beat * (1.9 if i == 0 else 0.9), "L"))
        notes.append((root - 12, t, beat * 3.8, "L"))
        t += 4 * beat
    return notes, beat


SONG, BEAT = make_song()
NOW = 7.15  # playback position in the screenshot


def visible(look_ahead):
    for p, s, d, hand in SONG:
        if s - NOW < look_ahead and s + d > NOW - 0.05:
            yield p, s, d, hand


def pressed_now():
    return {(p, hand) for p, s, d, hand in SONG if s <= NOW < s + d}


# =========================================================================== A. STUDIO

A = {
    "bg": hex2rgb("#0D0F13"),
    "panel": hex2rgb("#15181E"),
    "panel2": hex2rgb("#1B1F27"),
    "line": hex2rgb("#262B35"),
    "text": hex2rgb("#E8EAEE"),
    "muted": hex2rgb("#8B93A3"),
    "faint": hex2rgb("#5A6272"),
    "accent": hex2rgb("#6E8BFF"),
    "green": hex2rgb("#34C38F"),
    "right": hex2rgb("#5B8DEF"),
    "left": hex2rgb("#F2A541"),
    "felt": hex2rgb("#7B1E2C"),
}


def a_icon(surf, kind, x, y, color):
    if kind == "library":
        for i in range(3):
            rrect(surf, color, (x + i * 6, y + 2, 4, 14), 1)
    elif kind == "practice":
        pygame.draw.circle(surf, color, (x + 8, y + 9), 8, 2)
        pygame.draw.line(surf, color, (x + 8, y + 9), (x + 8, y + 4), 2)
        pygame.draw.line(surf, color, (x + 8, y + 9), (x + 12, y + 11), 2)
    elif kind == "free":
        for i in range(4):
            rrect(surf, color, (x + i * 5, y + 3, 4, 13), 1, width=0 if i % 2 else 1)
    elif kind == "progress":
        for i, hgt in enumerate((6, 10, 15)):
            rrect(surf, color, (x + i * 6, y + 17 - hgt, 4, hgt), 1)
    elif kind == "settings":
        pygame.draw.circle(surf, color, (x + 8, y + 9), 7, 2)
        pygame.draw.circle(surf, color, (x + 8, y + 9), 2)
    elif kind == "search":
        pygame.draw.circle(surf, color, (x + 6, y + 6), 6, 2)
        pygame.draw.line(surf, color, (x + 10, y + 10), (x + 15, y + 15), 2)


def a_logo(surf, x, y):
    for i, (hh, c) in enumerate(((22, A["accent"]), (15, A["right"]), (26, A["left"]))):
        rrect(surf, c, (x + i * 8, y + 26 - hh, 6, hh), 2)
    text(surf, inter(800, 21), "KeyFall", A["text"], (x + 32, y + 2))


def a_difficulty(surf, x, y, level):
    for i in range(5):
        c = A["accent"] if i < level else A["line"]
        rrect(surf, c, (x + i * 9, y, 7, 7), 2)


def studio_menu() -> pygame.Surface:
    s = pygame.Surface((W, H))
    s.fill(A["bg"])
    s.blit(
        radial((W, H), (900, -100), 900, (18, 22, 40)), (0, 0), special_flags=pygame.BLEND_RGB_ADD
    )

    # Sidebar
    rrect(s, A["panel"], (0, 0, 236, H), 0)
    pygame.draw.line(s, A["line"], (236, 0), (236, H))
    a_logo(s, 24, 24)
    nav = [
        ("library", "Library", True),
        ("practice", "Practice", False),
        ("free", "Free Play", False),
        ("progress", "Progress", False),
        ("settings", "Settings", False),
    ]
    y = 96
    for icon, label, active in nav:
        if active:
            rrect(s, A["accent"], (12, y - 8, 212, 38), 8, alpha=34)
            rrect(s, A["accent"], (12, y - 2, 3, 26), 2)
        col = A["text"] if active else A["muted"]
        a_icon(s, icon, 30, y + 1, col)
        text(s, inter(600 if active else 500, 15), label, col, (60, y + 1))
        y += 46

    # Device status cards
    tracked(s, inter(600, 11), "DEVICES", A["faint"], (24, 470), 1)
    for i, (title, sub, ok) in enumerate(
        (
            ("Roland FP-30X", "MIDI in · out", True),
            ("YDP Grand Piano", "Sound · 4 ms latency", True),
            ("Light-up keys", "Not connected", False),
        )
    ):
        cy = 494 + i * 62
        rrect(s, A["panel2"], (12, cy, 212, 52), 10)
        pygame.draw.circle(s, A["green"] if ok else A["faint"], (32, cy + 26), 5)
        text(s, inter(600, 14), title, A["text"] if ok else A["muted"], (48, cy + 9))
        text(s, inter(400, 12), sub, A["muted"], (48, cy + 28))

    # Header + search
    x0 = 268
    text(s, inter(700, 28), "Library", A["text"], (x0, 28))
    text(s, inter(400, 14), "42 songs · 6 imported from Suno", A["muted"], (x0, 66))
    rrect(s, A["panel"], (W - 392, 30, 360, 40), 10)
    rrect(s, A["line"], (W - 392, 30, 360, 40), 10, width=1)
    a_icon(s, "search", W - 376, 42, A["faint"])
    text(s, inter(400, 14), "Search songs, composers, tags…", A["faint"], (W - 350, 41))
    rrect(s, A["line"], (W - 90, 40, 48, 20), 5)
    text(s, inter(600, 11), "Ctrl K", A["muted"], (W - 66, 50), "center")

    # Filter chips
    cx = x0
    for i, chip in enumerate(
        ("All", "Recently played", "Suno imports", "Classical", "Beginner", "Difficulty    ")
    ):
        fw = inter(500, 13).size(chip)[0] + 28
        if i == 0:
            rrect(s, A["text"], (cx, 100, fw, 30), 15)
            text(s, inter(600, 13), chip, A["bg"], (cx + fw // 2, 115), "center")
        else:
            rrect(s, A["line"], (cx, 100, fw, 30), 15, width=1)
            text(s, inter(500, 13), chip, A["muted"], (cx + fw // 2, 115), "center")
            if chip.startswith("Difficulty"):
                chevron(s, A["muted"], (cx + fw - 16, 116))
        cx += fw + 8

    # Continue card
    card = pygame.Rect(x0, 150, W - x0 - 32, 128)
    shadow(s, card)
    blit_rounded(s, vgradient(card.size, (32, 38, 70), (22, 25, 36)), card.topleft, 14)
    rrect(s, (255, 255, 255), card, 14, alpha=18, width=1)
    # mini waterfall thumbnail
    th = pygame.Rect(card.x + 20, card.y + 18, 150, 92)
    rrect(s, (12, 14, 20), th, 10)
    rnd = random.Random(3)
    for k in range(14):
        lx = th.x + 10 + rnd.randint(0, 120)
        ly = th.y + rnd.randint(-10, 70)
        lh = rnd.randint(10, 26)
        c = A["right"] if lx > th.centerx - 10 else A["left"]
        rrect(s, c, pygame.Rect(lx, max(th.y + 4, ly), 9, lh).clip(th.inflate(-8, -8)), 3)
    tracked(s, inter(600, 11), "CONTINUE PRACTICING", A["accent"], (card.x + 192, card.y + 22), 1)
    text(s, inter(700, 22), "Midnight Drive", A["text"], (card.x + 192, card.y + 40))
    text(
        s,
        inter(400, 14),
        "Suno · piano stem  ·  Bars 17–32 loop  ·  72% tempo",
        A["muted"],
        (card.x + 192, card.y + 72),
    )
    bar = pygame.Rect(card.x + 192, card.y + 100, 420, 6)
    rrect(s, (255, 255, 255), bar, 3, alpha=25)
    rrect(s, A["accent"], (bar.x, bar.y, int(bar.w * 0.64), 6), 3)
    text(s, inter(500, 12), "64% mastered", A["muted"], (bar.right + 12, bar.y - 5))
    btn = pygame.Rect(card.right - 150, card.centery - 22, 126, 44)
    rrect(s, A["accent"], btn, 10)
    pygame.draw.polygon(
        s,
        (255, 255, 255),
        [(btn.x + 26, btn.y + 14), (btn.x + 26, btn.y + 30), (btn.x + 38, btn.y + 22)],
    )
    text(s, inter(600, 15), "Resume", (255, 255, 255), (btn.x + 48, btn.centery), "midleft")

    # Song table
    ty = 302
    cols = [
        (x0 + 16, "TITLE"),
        (x0 + 400, "SOURCE"),
        (x0 + 560, "DIFFICULTY"),
        (x0 + 700, "LENGTH"),
        (x0 + 790, "BEST"),
        (x0 + 880, "HANDS"),
    ]
    for cxp, label in cols:
        tracked(s, inter(600, 11), label, A["faint"], (cxp, ty), 1)
    pygame.draw.line(s, A["line"], (x0, ty + 24), (W - 32, ty + 24))
    rows = [
        ("Für Elise", "Beethoven", "Built-in", 2, "2:55", "96%", "Auto"),
        ("Midnight Drive", "Your Suno track", "Suno stem", 3, "3:12", "88%", "Pitch split"),
        ("Gymnopédie No. 1", "Satie", "Built-in", 2, "3:30", "—", "Auto"),
        ("Clair de Lune", "Debussy", "MusicXML", 5, "5:04", "61%", "Tracks"),
        ("Neon Rain", "Your Suno track", "Suno 2 stems", 4, "2:48", "74%", "Bass = LH"),
        ("The Entertainer", "Joplin", "Built-in", 3, "3:41", "90%", "Auto"),
    ]
    ry = ty + 34
    for i, (title, sub, src, diff, length, best, hands) in enumerate(rows):
        r = pygame.Rect(x0, ry - 6, W - x0 - 32, 52)
        if i == 1:
            rrect(s, A["accent"], r, 10, alpha=26)
            rrect(s, A["accent"], r, 10, alpha=90, width=1)
        rnd = random.Random(i)
        tile = pygame.Rect(x0 + 16, ry + 2, 36, 36)
        hue = [A["accent"], A["left"], A["green"], A["right"]][i % 4]
        art = vgradient(tile.size, mix(hue, (255, 255, 255), 0.15), mix(hue, (0, 0, 0), 0.5))
        for k in range(3):
            pygame.draw.rect(
                art,
                mix(hue, (255, 255, 255), 0.55),
                (8 + k * 8, 26 - (6, 14, 10)[k], 5, (6, 14, 10)[k]),
                border_radius=2,
            )
        blit_rounded(s, art, tile.topleft, 8)
        text(s, inter(600, 15), title, A["text"], (x0 + 64, ry + 1))
        text(s, inter(400, 12), sub, A["muted"], (x0 + 64, ry + 22))
        is_suno = src.startswith("Suno")
        fw = inter(500, 12).size(src)[0] + 18
        rrect(
            s,
            A["left"] if is_suno else A["line"],
            (x0 + 400, ry + 8, fw, 22),
            11,
            alpha=40 if is_suno else None,
        )
        text(
            s,
            inter(500, 12),
            src,
            A["left"] if is_suno else A["muted"],
            (x0 + 400 + fw // 2, ry + 19),
            "center",
        )
        a_difficulty(s, x0 + 560, ry + 15, diff)
        text(s, inter(500, 14), length, A["muted"], (x0 + 700, ry + 10))
        text(
            s,
            inter(600, 14),
            best,
            A["green"] if best != "—" and int(best[:-1]) >= 85 else A["muted"],
            (x0 + 790, ry + 10),
        )
        text(s, inter(500, 13), hands, A["muted"], (x0 + 880, ry + 11))
        _ = rnd
        ry += 56

    # Footer hints
    hint_x = x0
    for key, label in (
        ("↑↓", "Select"),
        ("Enter", "Play"),
        ("P", "Practice"),
        ("H", "Hands"),
        ("I", "Import"),
    ):
        kw = inter(600, 11).size(key)[0] + 14
        rrect(s, A["line"], (hint_x, H - 34, kw, 20), 5)
        text(s, inter(600, 11), key, A["text"], (hint_x + kw // 2, H - 24), "center")
        r = text(s, inter(500, 12), label, A["muted"], (hint_x + kw + 8, H - 32))
        hint_x = r.right + 20
    return s


def studio_keyboard(s, keys, pressed):
    # felt strip
    pygame.draw.rect(s, A["felt"], (0, keys.y - 5, W, 5))
    pygame.draw.line(s, mix(A["felt"], (0, 0, 0), 0.4), (0, keys.y - 1), (W, keys.y - 1))
    pressed_pitch = {p: hand for p, hand in pressed}
    for p in range(keys.lo, keys.hi + 1):
        if is_black(p):
            continue
        r = keys.rect(p)
        if p in pressed_pitch:
            c = A["right"] if pressed_pitch[p] == "R" else A["left"]
            s.blit(vgradient((r.w - 1, r.h), mix(c, (255, 255, 255), 0.35), c), r.topleft)
        else:
            s.blit(vgradient((r.w - 1, r.h), (232, 234, 238), (250, 250, 252)), r.topleft)
        pygame.draw.line(s, (180, 184, 192), (r.right - 1, r.y), (r.right - 1, r.bottom))
        if p % 12 == 0:
            text(
                s,
                inter(600, 10),
                note_name(p),
                (140, 146, 158),
                (r.centerx, r.bottom - 12),
                "center",
            )
    for p in range(keys.lo, keys.hi + 1):
        if not is_black(p):
            continue
        r = keys.rect(p)
        if p in pressed_pitch:
            c = A["right"] if pressed_pitch[p] == "R" else A["left"]
            s.blit(vgradient(r.size, mix(c, (0, 0, 0), 0.2), c), r.topleft)
        else:
            s.blit(vgradient(r.size, (16, 17, 20), (52, 55, 62)), r.topleft)
            pygame.draw.rect(s, (70, 74, 82), (r.x + 2, r.bottom - 8, r.w - 4, 5), border_radius=2)
    # top shadow on keys
    sh = vgradient((W, 10), (0, 0, 0), (40, 40, 40))
    s.blit(sh, (0, keys.y), special_flags=pygame.BLEND_RGB_MULT)


def studio_play() -> pygame.Surface:
    s = pygame.Surface((W, H))
    keys = Keys(29, 96, 0, W, H - 128, 128)
    top = 64
    area = pygame.Rect(0, top, W, keys.y - 5 - top)
    s.blit(vgradient((W, H), (13, 15, 19), (20, 23, 30)), (0, 0))

    # octave lanes and beat lines
    for p in range(keys.lo, keys.hi + 1):
        if p % 12 in (0, 5):
            x = int(keys.x[p])
            pygame.draw.line(
                s, (30, 34, 42) if p % 12 == 0 else (22, 25, 32), (x, area.y), (x, area.bottom)
            )
    look = 2.6
    pps = area.h / look
    first_bar = math.floor(NOW / (BEAT * 4))
    for b in range(first_bar, first_bar + 3):
        for q in range(4):
            t = (b * 4 + q) * BEAT
            y = area.bottom - (t - NOW) * pps
            if area.y < y < area.bottom:
                pygame.draw.line(
                    s, (40, 45, 56) if q == 0 else (24, 27, 34), (0, int(y)), (W, int(y))
                )
                if q == 0:
                    text(s, inter(600, 11), str(b + 17), A["faint"], (8, int(y) - 16))

    # notes
    for p, st, d, hand in sorted(visible(look), key=lambda n: is_black(n[0])):
        x, w = keys.lane(p)
        y0 = area.bottom - (st + d - NOW) * pps
        y1 = area.bottom - (st - NOW) * pps
        r = pygame.Rect(
            int(x), int(max(y0, area.y)), int(w), int(min(y1, area.bottom) - max(y0, area.y))
        )
        if r.h <= 0:
            continue
        c = A["right"] if hand == "R" else A["left"]
        if is_black(p):
            c = mix(c, (0, 0, 0), 0.25)
        rrect(s, c, r, 5)
        pygame.draw.line(
            s, mix(c, (255, 255, 255), 0.35), (r.x + 4, r.y + 1), (r.right - 5, r.y + 1)
        )
        if r.h > 24 and w > 14:
            text(
                s,
                inter(700, 10),
                NAMES[p % 12],
                mix(c, (0, 0, 0), 0.6),
                (r.centerx, r.bottom - 9),
                "center",
            )

    # top bar
    rrect(s, A["panel"], (0, 0, W, top), 0)
    pygame.draw.line(s, A["line"], (0, top - 1), (W, top - 1))
    pygame.draw.lines(s, A["muted"], False, [(30, 24), (22, 32), (30, 40)], 2)
    text(s, inter(700, 16), "Midnight Drive", A["text"], (48, 13))
    text(s, inter(400, 12), "Suno piano stem · Practice", A["muted"], (48, 35))
    # timeline with loop region
    tl = pygame.Rect(330, 30, 520, 4)
    rrect(s, A["line"], tl, 2)
    loop = pygame.Rect(tl.x + 150, tl.y - 6, 150, 16)
    rrect(s, A["accent"], loop, 4, alpha=40)
    rrect(s, A["accent"], loop, 4, alpha=140, width=1)
    rrect(s, A["accent"], (tl.x, tl.y, 228, 4), 2)
    pygame.draw.circle(s, (255, 255, 255), (tl.x + 228, tl.centery), 7)
    text(s, inter(500, 11), "1:12", A["muted"], (tl.x - 10, tl.centery), "midright")
    text(s, inter(500, 11), "3:12", A["muted"], (tl.right + 10, tl.centery), "midleft")
    text(s, inter(600, 10), "LOOP 17–32", A["accent"], (loop.centerx, loop.y - 9), "center")
    chips = [("72%", "Tempo"), ("Wait", "Mode"), ("Both", "Hands"), ("On", "Metronome")]
    cx = W - 24
    for val, label in reversed(chips):
        fw = max(inter(700, 13).size(val)[0], inter(500, 10).size(label)[0]) + 22
        cx -= fw
        rrect(s, A["panel2"], (cx, 12, fw, 40), 8)
        text(s, inter(700, 13), val, A["text"], (cx + fw // 2, 25), "center")
        text(s, inter(500, 10), label, A["muted"], (cx + fw // 2, 42), "center")
        cx -= 8

    # stats card
    card = pygame.Rect(W - 236, top + 16, 212, 150)
    rrect(s, (21, 24, 31), card, 12, alpha=235)
    rrect(s, (255, 255, 255), card, 12, alpha=16, width=1)
    tracked(s, inter(600, 10), "ACCURACY", A["faint"], (card.x + 16, card.y + 14), 1)
    text(s, inter(700, 30), "94.2%", A["text"], (card.x + 16, card.y + 28))
    tracked(s, inter(600, 10), "STREAK", A["faint"], (card.x + 140, card.y + 14), 1)
    text(s, inter(700, 30), "37", A["green"], (card.x + 140, card.y + 28))
    tracked(s, inter(600, 10), "TIMING", A["faint"], (card.x + 16, card.y + 78), 1)
    hist = [1, 2, 4, 9, 15, 19, 14, 8, 4, 2, 1]
    for i, v in enumerate(hist):
        c = A["green"] if 3 <= i <= 7 else A["muted"]
        rrect(s, c, (card.x + 16 + i * 17, card.y + 130 - v * 2, 12, v * 2), 2)
    text(s, inter(500, 10), "early", A["faint"], (card.x + 16, card.y + 134))
    text(s, inter(500, 10), "late", A["faint"], (card.right - 16, card.y + 134), "topright")

    # hit line
    pygame.draw.line(s, (255, 255, 255), (0, area.bottom - 1), (W, area.bottom - 1), 1)
    studio_keyboard(s, keys, pressed_now())
    return s


# =========================================================================== B. NEON ARCADE

N = {
    "bg_top": hex2rgb("#07031A"),
    "bg_bot": hex2rgb("#1C0838"),
    "cyan": hex2rgb("#18E7FF"),
    "pink": hex2rgb("#FF2FD0"),
    "gold": hex2rgb("#FFD23F"),
    "text": hex2rgb("#F4F0FF"),
    "muted": hex2rgb("#A49BC8"),
    "grid": hex2rgb("#7A2CFF"),
    "green": hex2rgb("#4BFF9B"),
}


def neon_backdrop(s, horizon=430):
    s.blit(vgradient((W, H), N["bg_top"], N["bg_bot"]), (0, 0))
    rnd = random.Random(7)
    for _ in range(140):
        x, y = rnd.randint(0, W), rnd.randint(0, horizon)
        c = rnd.randint(90, 220)
        s.set_at((x, y), (c, c, min(255, c + 30)))
    # synthwave grid floor
    layer = pygame.Surface((W, H))
    vx = W // 2
    for i in range(-14, 15):
        pygame.draw.line(layer, N["grid"], (vx + i * 18, horizon), (vx + i * 160, H), 1)
    for k in range(1, 12):
        y = horizon + (H - horizon) * (k / 11) ** 2
        pygame.draw.line(layer, N["grid"], (0, int(y)), (W, int(y)), 1)
    fade = vgradient((W, H - horizon), (0, 0, 0), (110, 110, 110))
    sub = layer.subsurface((0, horizon, W, H - horizon))
    sub.blit(fade, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    layer.fill((0, 0, 0), (0, 0, W, horizon))
    s.blit(layer, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    glow(s, layer, 0.1, 1)
    s.blit(
        radial((W, H), (W // 2, horizon), 520, (120, 30, 160), 0.8),
        (0, 0),
        special_flags=pygame.BLEND_RGB_ADD,
    )


def neon_text(s, fnt, msg, color, pos, anchor="center", glow_strength=1):
    layer = pygame.Surface((W, H))
    r = text(layer, fnt, msg, color, pos, anchor)
    for _ in range(glow_strength):
        glow(s, layer, 0.15, 2)
    text(s, fnt, msg, mix(color, (255, 255, 255), 0.55), pos, anchor)
    return r


def album_art(size, seed, a, b) -> pygame.Surface:
    art = vgradient(size, a, b)
    rnd = random.Random(seed)
    w, h = size
    pygame.draw.circle(art, mix(a, (255, 255, 255), 0.4), (w // 2, int(h * 0.62)), int(w * 0.28))
    for k in range(6):
        y = int(h * 0.62) + k * 7 - 6
        pygame.draw.line(art, b, (0, y), (w, y), 3)
    for _ in range(18):
        x = rnd.randint(0, w)
        bh = rnd.randint(10, h // 3)
        pygame.draw.rect(art, mix(b, (0, 0, 0), 0.5), (x, h - bh, rnd.randint(8, 18), bh))
    return art


def neon_menu() -> pygame.Surface:
    s = pygame.Surface((W, H))
    neon_backdrop(s, horizon=470)

    # profile + streak
    pygame.draw.circle(s, N["pink"], (52, 46), 24, 3)
    pygame.draw.circle(s, (60, 20, 90), (52, 46), 20)
    text(s, rajdhani("Bold", 20), "RB", N["text"], (52, 46), "center")
    text(s, rajdhani("Bold", 20), "RYAN", N["text"], (88, 24))
    text(s, rajdhani("SemiBold", 15), "LV 12  ·  PIANIST", N["muted"], (88, 46))
    bar = pygame.Rect(88, 66, 180, 6)
    rrect(s, (255, 255, 255), bar, 3, alpha=30)
    layer = pygame.Surface((W, H))
    rrect(layer, N["cyan"], (bar.x, bar.y, 128, 6), 3)
    glow(s, layer, 0.15, 1)
    rrect(s, N["cyan"], (bar.x, bar.y, 128, 6), 3)
    # streak / gems
    for i, (val, label, c) in enumerate(
        (("7", "DAY STREAK", N["gold"]), ("12,480", "XP", N["cyan"]))
    ):
        x = W - 300 + i * 150
        rrect(s, (255, 255, 255), (x, 22, 136, 48), 12, alpha=14)
        rrect(s, c, (x, 22, 136, 48), 12, alpha=120, width=1)
        text(s, orbitron(900, 20), val, c, (x + 14, 26))
        text(s, rajdhani("SemiBold", 13), label, N["muted"], (x + 14, 50))

    # title
    neon_text(s, orbitron(900, 54), "KEYFALL", N["pink"], (W // 2, 70), glow_strength=2)

    # mode tabs
    tabs = ["CLASSIC", "PRACTICE", "FREE PLAY", "CHALLENGES"]
    tx = W // 2 - 270
    for i, t in enumerate(tabs):
        r = text(s, rajdhani("Bold", 22), t, N["text"] if i == 0 else N["muted"], (tx, 126))
        if i == 0:
            layer = pygame.Surface((W, H))
            pygame.draw.rect(layer, N["cyan"], (r.x, r.bottom + 2, r.w, 3))
            glow(s, layer, 0.15, 1)
            pygame.draw.rect(s, N["cyan"], (r.x, r.bottom + 2, r.w, 3))
        tx = r.right + 46

    # carousel
    cards = [
        ("FÜR ELISE", "Beethoven", 2, "S", (40, 120, 255), (20, 10, 60)),
        ("THE ENTERTAINER", "Joplin", 3, "A", (255, 140, 40), (80, 10, 60)),
        ("MIDNIGHT DRIVE", "Suno · Your track", 3, "A", (255, 47, 208), (40, 8, 90)),
        ("NEON RAIN", "Suno · Your track", 4, "B", (24, 231, 255), (30, 10, 80)),
        ("CLAIR DE LUNE", "Debussy", 5, "—", (120, 90, 255), (10, 10, 40)),
    ]
    center = 2
    cy = 330
    for idx in (0, 4, 1, 3, 2):
        off = idx - center
        scale = 1.0 if off == 0 else 0.78 if abs(off) == 1 else 0.6
        cw, ch = int(250 * scale), int(310 * scale)
        cx = W // 2 + off * 250 - (0 if off == 0 else int(math.copysign(30 * abs(off), off)))
        rect = pygame.Rect(0, 0, cw, ch)
        rect.center = (cx, cy)
        title, artist, diff, rank, ca, cb = cards[idx]
        if off == 0:
            layer = pygame.Surface((W, H))
            rrect(layer, N["pink"], rect.inflate(8, 8), 20)
            glow(s, layer, 0.08, 2)
        art = album_art((cw, int(ch * 0.62)), idx, ca, cb)
        card = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(card, (24, 12, 48, 255), card.get_rect(), border_radius=18)
        card.blit(art, (0, 0))
        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=18)
        card.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        if off != 0:
            dim = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(
                dim, (8, 3, 26, 120 if abs(off) == 1 else 170), dim.get_rect(), border_radius=18
            )
            card.blit(dim, (0, 0))
        s.blit(card, rect.topleft)
        pygame.draw.rect(s, N["pink"] if off == 0 else (90, 60, 140), rect, 2, border_radius=18)
        if abs(off) <= 1:
            ty = rect.y + int(ch * 0.62) + 10
            fs = 22 if off == 0 else 17
            text(s, rajdhani("Bold", fs), title, N["text"], (rect.x + 14, ty))
            text(s, rajdhani("Medium", fs - 6), artist, N["muted"], (rect.x + 14, ty + fs + 2))
            for k in range(5):
                c = N["gold"] if k < diff else (70, 50, 110)
                px = rect.x + 16 + k * (16 if off == 0 else 13)
                py = rect.bottom - (24 if off == 0 else 18)
                rr = 6 if off == 0 else 5
                pts = [
                    (
                        px + rr * math.cos(a) * (1 if j % 2 == 0 else 0.45),
                        py + rr * math.sin(a) * (1 if j % 2 == 0 else 0.45),
                    )
                    for j, a in enumerate(-math.pi / 2 + i * math.pi / 5 for i in range(10))
                ]
                pygame.draw.polygon(s, c, pts)
            if rank != "—":
                rc = {"S": N["gold"], "A": N["cyan"], "B": N["green"]}[rank]
                badge = (rect.right - 30, rect.y + 30)
                pygame.draw.circle(s, (10, 4, 30), badge, 20 if off == 0 else 16)
                pygame.draw.circle(s, rc, badge, 20 if off == 0 else 16, 2)
                text(s, orbitron(900, 18 if off == 0 else 14), rank, rc, badge, "center")
    # arrows
    for sx, pts in (
        (W // 2 - 590, [(12, -16), (0, 0), (12, 16)]),
        (W // 2 + 590, [(-12, -16), (0, 0), (-12, 16)]),
    ):
        pygame.draw.lines(s, N["muted"], False, [(sx + x, cy + y) for x, y in pts], 3)

    # play button
    btn = pygame.Rect(0, 0, 260, 58)
    btn.center = (W // 2, 552)
    layer = pygame.Surface((W, H))
    rrect(layer, N["cyan"], btn, 29)
    glow(s, layer, 0.1, 2)
    blit_rounded(s, vgradient(btn.size, (90, 245, 255), (10, 170, 230)), btn.topleft, 29)
    pygame.draw.rect(s, N["bg_top"], btn.inflate(4, 4), 3, border_radius=31)
    pts = [(btn.x + 72, btn.y + 17), (btn.x + 72, btn.y + 41), (btn.x + 92, btn.y + 29)]
    pygame.draw.polygon(s, N["bg_top"], pts)
    text(s, orbitron(900, 24), "PLAY", N["bg_top"], (btn.x + 106, btn.centery), "midleft")
    text(
        s,
        rajdhani("SemiBold", 16),
        "BEST 412,880  ·  ACCURACY 91%  ·  HANDS: AUTO",
        N["muted"],
        (W // 2, 600),
        "center",
    )

    # key hints
    hx = W // 2 - 300
    for key, label in (
        ("ARROWS", "SELECT"),
        ("ENTER", "PLAY"),
        ("TAB", "MODE"),
        ("H", "HANDS"),
        ("I", "IMPORT SUNO"),
    ):
        kw = rajdhani("Bold", 15).size(key)[0] + 18
        rrect(s, (255, 255, 255), (hx, 660, kw, 26), 6, alpha=28)
        rrect(s, N["muted"], (hx, 660, kw, 26), 6, alpha=120, width=1)
        text(s, rajdhani("Bold", 15), key, N["text"], (hx + kw // 2, 673), "center")
        r = text(s, rajdhani("SemiBold", 15), label, N["muted"], (hx + kw + 8, 663))
        hx = r.right + 22
    return s


def neon_play() -> pygame.Surface:
    s = pygame.Surface((W, H))
    keys = Keys(29, 96, 0, W, H - 118, 118)
    hit_y = keys.y - 4
    s.blit(vgradient((W, H), (6, 2, 20), (26, 8, 50)), (0, 0))
    # lane shading per octave
    for p in range(keys.lo, keys.hi + 1, 12):
        if (p // 12) % 2 == 0:
            x0 = keys.x[p]
            x1 = keys.x.get(p + 12, W)
            rrect(s, (255, 255, 255), (int(x0), 0, int(x1 - x0), hit_y), 0, alpha=6)
    look = 2.2
    pps = hit_y / look
    for b in range(-1, 12):
        t = math.floor(NOW / BEAT) * BEAT + b * BEAT
        y = hit_y - (t - NOW) * pps
        if 0 < y < hit_y:
            rrect(s, N["grid"], (0, int(y), W, 1), 0, alpha=60 if round(t / BEAT) % 4 == 0 else 22)

    pressed = pressed_now()
    # light beams from pressed keys
    for p, hand in pressed:
        x, w = keys.lane(p)
        c = N["cyan"] if hand == "R" else N["pink"]
        beam = vgradient((int(w) + 10, hit_y), (0, 0, 0), mix(c, (0, 0, 0), 0.45))
        s.blit(beam, (int(x) - 5, 0), special_flags=pygame.BLEND_RGB_ADD)

    # notes with glow
    glow_layer = pygame.Surface((W, H))
    note_rects = []
    for p, st, d, hand in sorted(visible(look), key=lambda n: is_black(n[0])):
        x, w = keys.lane(p)
        y0 = hit_y - (st + d - NOW) * pps
        y1 = min(hit_y, hit_y - (st - NOW) * pps)
        r = pygame.Rect(int(x), int(max(y0, 0)), int(w), int(y1 - max(y0, 0)))
        if r.h <= 2:
            continue
        c = N["cyan"] if hand == "R" else N["pink"]
        rrect(glow_layer, c, r, 6)
        note_rects.append((r, c, p))
    glow(s, glow_layer, 0.08, 2)
    glow(s, glow_layer, 0.2, 1)
    for r, c, p in note_rects:
        body = vgradient(r.size, mix(c, (0, 0, 0), 0.35), c)
        card = pygame.Surface(r.size, pygame.SRCALPHA)
        card.blit(body, (0, 0))
        mask = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=6)
        card.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        s.blit(card, r.topleft)
        pygame.draw.rect(s, mix(c, (255, 255, 255), 0.7), r, 2, border_radius=6)
        if r.h > 22 and r.w > 14:
            text(
                s,
                rajdhani("Bold", 13),
                NAMES[p % 12],
                (255, 255, 255),
                (r.centerx, r.bottom - 10),
                "center",
            )

    # hit line + sparks
    layer = pygame.Surface((W, H))
    pygame.draw.rect(layer, (200, 120, 255), (0, hit_y - 2, W, 4))
    rnd = random.Random(11)
    for p, hand in pressed:
        x, w = keys.lane(p)
        cxp = int(x + w / 2)
        c = N["cyan"] if hand == "R" else N["pink"]
        pygame.draw.circle(layer, c, (cxp, hit_y), 18)
        for _ in range(9):
            ang = rnd.uniform(math.pi * 1.05, math.pi * 1.95)
            ln = rnd.uniform(14, 46)
            ex, ey = cxp + math.cos(ang) * ln, hit_y + math.sin(ang) * ln
            pygame.draw.line(layer, mix(c, (255, 255, 255), 0.5), (cxp, hit_y), (ex, ey), 2)
            pygame.draw.circle(s, (255, 255, 255), (int(ex), int(ey)), 2)
    glow(s, layer, 0.12, 2)
    s.blit(layer, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    pygame.draw.line(s, (255, 235, 255), (0, hit_y), (W, hit_y), 2)

    # keyboard
    pressed_pitch = {p: hand for p, hand in pressed}
    for p in range(keys.lo, keys.hi + 1):
        if is_black(p):
            continue
        r = keys.rect(p)
        if p in pressed_pitch:
            c = N["cyan"] if pressed_pitch[p] == "R" else N["pink"]
            s.blit(vgradient((r.w - 1, r.h), (255, 255, 255), c), r.topleft)
        else:
            s.blit(vgradient((r.w - 1, r.h), (206, 200, 228), (246, 244, 255)), r.topleft)
        pygame.draw.line(s, (120, 100, 160), (r.right - 1, r.y), (r.right - 1, r.bottom))
    for p in range(keys.lo, keys.hi + 1):
        if not is_black(p):
            continue
        r = keys.rect(p)
        if p in pressed_pitch:
            c = N["cyan"] if pressed_pitch[p] == "R" else N["pink"]
            s.blit(vgradient(r.size, mix(c, (0, 0, 0), 0.3), c), r.topleft)
        else:
            s.blit(vgradient(r.size, (10, 6, 22), (48, 36, 78)), r.topleft)
    s.blit(
        vgradient((W, 12), (60, 30, 90), (255, 255, 255)),
        (0, keys.y),
        special_flags=pygame.BLEND_RGB_MULT,
    )

    # HUD: progress, title, score, combo, judgement, accuracy ring
    scrim = vgradient((W, 150), (90, 90, 90), (255, 255, 255))
    s.blit(scrim, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    rrect(s, (255, 255, 255), (0, 0, W, 4), 0, alpha=25)
    layer = pygame.Surface((W, H))
    pygame.draw.rect(layer, N["cyan"], (0, 0, int(W * 0.38), 4))
    glow(s, layer, 0.2, 1)
    pygame.draw.rect(s, N["cyan"], (0, 0, int(W * 0.38), 4))

    text(s, rajdhani("Bold", 22), "MIDNIGHT DRIVE", N["text"], (104, 22))
    text(
        s,
        rajdhani("SemiBold", 15),
        "SUNO · YOUR TRACK   ·   NORMAL   ·   1:12 / 3:12",
        N["muted"],
        (104, 46),
    )
    text(s, rajdhani("Bold", 15), "96.3% ACCURACY", N["green"], (104, 66))

    text(s, orbitron(900, 30), "482,150", N["text"], (W - 24, 16), "topright")
    rrect(s, N["gold"], (W - 92, 56, 68, 26), 13, alpha=50)
    text(s, orbitron(900, 15), "x4", N["gold"], (W - 58, 69), "center")
    text(s, rajdhani("SemiBold", 15), "MULTIPLIER", N["muted"], (W - 100, 61), "topright")

    neon_text(s, orbitron(900, 64), "128", N["cyan"], (W // 2, 56), glow_strength=1)
    tracked(s, rajdhani("Bold", 18), "COMBO", N["muted"], (W // 2, 96), 6, "midtop")

    plate = pygame.Rect(0, 0, 250, 78)
    plate.center = (W // 2 + 20, hit_y - 170)
    rrect(s, (8, 3, 24), plate, 16, alpha=170)
    neon_text(
        s, orbitron(900, 34), "PERFECT", N["gold"], (plate.centerx, plate.y + 30), glow_strength=2
    )
    text(s, orbitron(700, 16), "+300", N["gold"], (plate.centerx, plate.y + 60), "center")

    # accuracy ring (grade)
    c = (56, 50)
    pygame.draw.circle(s, (60, 40, 100), c, 30, 5)
    pygame.draw.arc(
        s,
        N["green"],
        (c[0] - 30, c[1] - 30, 60, 60),
        math.pi / 2,
        math.pi / 2 + 2 * math.pi * 0.963,
        5,
    )
    text(s, orbitron(900, 24), "S", N["gold"], c, "center")
    # groove meter
    gm = pygame.Rect(W - 40, 130, 12, 300)
    rrect(s, (255, 255, 255), gm, 6, alpha=20)
    fill_h = int(gm.h * 0.78)
    s.blit(vgradient((gm.w, fill_h), N["gold"], N["pink"]), (gm.x, gm.bottom - fill_h))
    pygame.draw.rect(s, N["bg_top"], gm.inflate(2, 2), 2, border_radius=7)
    text(s, rajdhani("Bold", 13), "GROOVE", N["muted"], (gm.centerx, gm.bottom + 8), "midtop")
    return s


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (
        ("style_a_studio_menu", studio_menu),
        ("style_a_studio_play", studio_play),
        ("style_b_neon_menu", neon_menu),
        ("style_b_neon_play", neon_play),
    ):
        pygame.image.save(fn(), os.path.join(OUT, f"{name}.png"))
        print("wrote", name)


if __name__ == "__main__":
    main()
