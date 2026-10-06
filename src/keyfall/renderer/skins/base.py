"""Skin base class: shared helpers plus the Settings and Free Play screens.

A skin draws whole screens from the frame dataclasses in ``frames.py``.
Subclasses must implement ``draw_play`` and ``draw_menu`` and may override
anything else (``draw_backdrop`` and ``draw_keyboard`` especially).
"""

from __future__ import annotations

import pygame

from keyfall.accessibility import (
    PALETTE_COLORS,
    AccessibilitySettings,
    ColorPalette,
    NoteLabelMode,
)
from keyfall.models import PERCUSSION, Hand, Song
from keyfall.notation import render_notation
from keyfall.renderer import fonts
from keyfall.renderer.draw import Color, chevron, mix, rrect, text, tracked
from keyfall.renderer.skins.frames import (
    FreePlayFrame,
    MenuFrame,
    PlayFrame,
    SettingsFrame,
    SettingsRow,
    StemsFrame,
)
from keyfall.renderer.skins.keys import KeyLayout, NoteIndex, fit_range, is_black, note_name
from keyfall.renderer.theme import Theme


class Skin:
    theme: Theme

    def __init__(self, effects: str = "full",
                 accessibility: AccessibilitySettings | None = None) -> None:
        self.effects = effects
        self.accessibility = accessibility or AccessibilitySettings()
        self.p = self.theme.palette
        self.right, self.left = self._hand_colors()
        if self._high_contrast:
            self.p = type(self.p)(**{**self.p.__dict__, "bg": (0, 0, 0), "bg2": (0, 0, 0),
                                     "text": (255, 255, 255), "muted": (220, 220, 220)})
        self._index: NoteIndex | None = None
        self._backing_index: NoteIndex | None = None
        self._range_cache: tuple[int, tuple[int, int]] | None = None

    # ------------------------------------------------------------ settings-derived
    @property
    def _high_contrast(self) -> bool:
        a = self.accessibility
        return a.high_contrast or a.get_palette() == ColorPalette.HIGH_CONTRAST

    def _hand_colors(self) -> tuple[Color, Color]:
        palette = self.accessibility.get_palette()
        if self.accessibility.high_contrast:
            palette = ColorPalette.HIGH_CONTRAST
        if palette != ColorPalette.DEFAULT:
            rh, lh, _bg = PALETTE_COLORS[palette]
            return rh, lh
        return self.theme.palette.right, self.theme.palette.left

    @property
    def glow_on(self) -> bool:
        return self.theme.glow and self.effects != "off"

    @property
    def particles_on(self) -> bool:
        return self.theme.particles and self.effects == "full"

    @property
    def beams_on(self) -> bool:
        return self.theme.light_beams and self.effects != "off"

    @property
    def label_mode(self) -> NoteLabelMode:
        return self.accessibility.get_label_mode()

    # ------------------------------------------------------------ fonts
    def ui(self, weight: int, size: int) -> pygame.font.Font:
        return fonts.get(self.theme.ui_font, weight, size)

    def display(self, weight: int, size: int) -> pygame.font.Font:
        return fonts.get(self.theme.display_font, weight, size)

    def label(self, weight: int, size: int) -> pygame.font.Font:
        return fonts.get(self.theme.label_font, weight, size)

    # ------------------------------------------------------------ song helpers
    def hand_color(self, hand: Hand) -> Color:
        return self.left if hand == Hand.LEFT else self.right

    def note_index(self, song: Song) -> NoteIndex:
        if self._index is None or self._index.song is not song:
            self._index = NoteIndex(song)
        return self._index

    def backing_window(self, song: Song, t0: float, t1: float, layout: KeyLayout):
        """Pitched backing notes (no drums) overlapping [t0, t1] that fit the keyboard."""
        if not song.backing:
            return []
        idx = self._backing_index
        if idx is None or idx.notes is not song.backing:
            idx = self._backing_index = NoteIndex(song, song.backing)
        drums = {t for t, prog in song.backing_programs.items() if prog == PERCUSSION}
        return [n for n in idx.window(t0, t1) if n.track not in drums and layout.contains(n.pitch)]

    def draw_backing(self, surface: pygame.Surface, frame: PlayFrame, layout: KeyLayout,
                     area: pygame.Rect, look_ahead: float, color: Color, fill_alpha: int = 26,
                     edge_alpha: int = 90, clip: pygame.Rect | None = None) -> None:
        """Faint outlined "ghost" bars for accompaniment: heard, never played.

        ``area`` is the falling-note field (its bottom is the hit line and its
        height spans ``look_ahead`` seconds); ``clip`` limits drawing if smaller.
        """
        pps = area.h / look_ahead
        clip = clip or area
        for n in self.backing_window(frame.song, frame.position - 0.05,
                                     frame.position + look_ahead, layout):
            x, lw = layout.lane(n.pitch)
            inset = lw * 0.2
            y0 = area.bottom - (n.start_time + n.duration - frame.position) * pps
            y1 = area.bottom - (n.start_time - frame.position) * pps
            r = pygame.Rect(int(x + inset), int(y0), max(2, int(lw - 2 * inset)),
                            int(y1 - y0)).clip(clip)
            if r.h <= 0:
                continue
            rrect(surface, color, r, 4, alpha=fill_alpha)
            rrect(surface, color, r, 4, alpha=edge_alpha, width=1)

    def song_range(self, song: Song) -> tuple[int, int]:
        if self._range_cache is None or self._range_cache[0] != id(song):
            self._range_cache = (id(song), fit_range(song))
        return self._range_cache[1]

    def pressed_hands(self, frame: PlayFrame, layout: KeyLayout) -> dict[int, Hand]:
        idx = self.note_index(frame.song)
        return {p: idx.hand_at(p, frame.position) for p in frame.pressed if layout.contains(p)}

    # ------------------------------------------------------------ screens
    def draw_play(self, surface: pygame.Surface, frame: PlayFrame) -> None:
        raise NotImplementedError

    def draw_menu(self, surface: pygame.Surface, frame: MenuFrame) -> None:
        raise NotImplementedError

    def draw_backdrop(self, surface: pygame.Surface) -> None:
        surface.fill(self.p.bg)

    def draw_keyboard(self, surface: pygame.Surface, layout: KeyLayout,
                      pressed: dict[int, Hand]) -> None:
        """Flat keyboard; modern skins override."""
        for black in (False, True):
            for p in range(layout.lo, layout.hi + 1):
                if is_black(p) != black:
                    continue
                r = layout.key_rect(p)
                if p in pressed:
                    color = self.hand_color(pressed[p])
                else:
                    color = (30, 30, 30) if black else (240, 240, 240)
                if not black:
                    r.w -= 1
                pygame.draw.rect(surface, color, r)

    def draw_notation_panel(self, surface: pygame.Surface, frame: PlayFrame,
                            rect: pygame.Rect) -> None:
        rrect(surface, self.p.panel, rect, 0)
        render_notation(surface, frame.song, frame.position, x=rect.x, y=rect.y, width=rect.w,
                        height=rect.h, hit_results=frame.hit_results)
        surface.set_clip(None)
        pygame.draw.line(surface, self.p.line, (rect.x, rect.bottom - 1),
                         (rect.right, rect.bottom - 1))

    def swatch_color(self, key: str) -> Color:
        return {"right": self.right, "left": self.left, "both": self.p.accent,
                "backing": self.p.muted, "off": self.p.faint}.get(key, self.p.text)

    def _draw_row(self, surface: pygame.Surface, row: SettingsRow, selected: bool, x: int,
                  y: int, width: int, height: int = 68) -> pygame.Rect:
        """One adjustable "label ‹ value ›" row (shared by Settings and Stems)."""
        p = self.p
        r = pygame.Rect(x, y, width, height if row.adjustable else 52)
        rrect(surface, p.panel2 if selected else p.panel, r, 12, alpha=235)
        if selected:
            rrect(surface, p.accent, r, 12, width=2)
        label_font = self.ui(700, 17)
        label = row.label
        while len(label) > 4 and label_font.size(label)[0] > width - 330:
            label = label[:-2] + "…"
        text(surface, label_font, label, p.text, (r.x + 20, r.y + 12))
        if row.adjustable:
            text(surface, self.ui(400, 13), row.description, p.muted, (r.x + 20, r.y + 38))
            val_font = self.ui(700, 16)
            value = row.value
            while len(value) > 4 and val_font.size(value)[0] > 250:
                value = value[:-2] + "…"
            vw = val_font.size(value)[0]
            vx = r.right - 44 - vw
            color = self.swatch_color(row.swatch) if row.swatch else (
                p.accent if selected else p.text)
            if row.swatch:
                pygame.draw.circle(surface, color, (vx - 34, r.y + 24), 5)
            text(surface, val_font, value, color, (vx, r.y + 14))
            col = p.accent if selected else p.faint
            chevron(surface, col, (vx - 16, r.y + 24), 5, "left")
            chevron(surface, col, (r.right - 28, r.y + 24), 5, "right")
        return r

    def draw_settings(self, surface: pygame.Surface, frame: SettingsFrame) -> None:
        p = self.p
        w, h = surface.get_size()
        self.draw_backdrop(surface)
        text(surface, self.display(800, 32), "Settings", p.text, (60, 40))
        text(surface, self.ui(400, 15), "Changes apply instantly and are saved automatically.",
             p.muted, (60, 86))

        y = 124
        compact = len(frame.rows) > 6
        for i, row in enumerate(frame.rows):
            r = self._draw_row(surface, row, i == frame.selected, 48, y, 560,
                               58 if compact else 68)
            y = r.bottom + (6 if compact else 10)

        # Live preview of the selected theme
        pv = pygame.Rect(650, 130, w - 650 - 48, 0)
        pv.h = int(pv.w * 9 / 16)
        tracked(surface, self.label(700, 12), "PREVIEW", p.muted, (pv.x, pv.y - 22), 2)
        if frame.preview is not None:
            img = pygame.transform.smoothscale(frame.preview, pv.size)
            surface.blit(img, pv.topleft)
        rrect(surface, p.line, pv.inflate(4, 4), 6, width=2)
        if frame.theme_description:
            text(surface, self.ui(400, 14), frame.theme_description, p.muted,
                 (pv.x, pv.bottom + 16))
        if frame.message:
            text(surface, self.ui(600, 14), frame.message, p.good, (pv.x, pv.bottom + 42))

        hints = "Up/Down: choose setting   Left/Right: change   Esc: back"
        text(surface, self.ui(500, 13), hints, p.faint, (60, h - 34))

    def draw_stems(self, surface: pygame.Surface, frame: StemsFrame) -> None:
        p = self.p
        w, h = surface.get_size()
        self.draw_backdrop(surface)
        text(surface, self.display(800, 30), frame.title, p.text, (60, 36))
        text(surface, self.ui(400, 15),
             "Choose who plays each stem. Your choices are saved with the song.",
             p.muted, (60, 80))

        row_h, top = 62, 122
        visible = max(1, (h - top - 64) // row_h)
        start = max(0, min(frame.selected - visible // 2, len(frame.rows) - visible))
        y = top
        for i in range(start, min(len(frame.rows), start + visible)):
            r = self._draw_row(surface, frame.rows[i], i == frame.selected, 48, y, 600, 56)
            y = r.bottom + 6
        if start > 0:
            chevron(surface, p.muted, (348, top - 10), 6, "up")
        if start + visible < len(frame.rows):
            chevron(surface, p.muted, (348, h - 54), 6, "down")

        roll = pygame.Rect(690, 150, w - 690 - 48, 300)
        tracked(surface, self.label(700, 12), "RESULT", p.muted, (roll.x, roll.y - 24), 2)
        rrect(surface, p.panel, roll, 12)
        if frame.song is not None:
            self._draw_roll(surface, frame.song, roll.inflate(-20, -20))
        rrect(surface, p.line, roll, 12, width=1)
        lx = roll.x
        for key, label in (("right", "Right hand"), ("left", "Left hand"),
                           ("backing", "Backing (heard, not played)")):
            pygame.draw.circle(surface, self.swatch_color(key), (lx + 6, roll.bottom + 22), 5)
            r = text(surface, self.ui(500, 13), label, p.muted, (lx + 18, roll.bottom + 13))
            lx = r.right + 22
        for i, line in enumerate(frame.summary):
            text(surface, self.ui(500 if i else 700, 14), line, p.text if i == 0 else p.muted,
                 (roll.x, roll.bottom + 50 + i * 24))
        if frame.message:
            text(surface, self.ui(600, 14), frame.message, p.miss,
                 (roll.x, roll.bottom + 54 + len(frame.summary) * 24))
        text(surface, self.ui(500, 13),
             "Up/Down: choose   Left/Right: change   Enter on Start: play   Esc: back",
             p.faint, (60, h - 34))

    def _draw_roll(self, surface: pygame.Surface, song: Song, rect: pygame.Rect) -> None:
        """Tiny piano roll of the whole song: time across, pitch up."""
        drums = {t for t, prog in song.backing_programs.items() if prog == PERCUSSION}
        backing = [n for n in song.backing if n.track not in drums]
        notes = song.notes + backing
        if not notes or song.duration <= 0:
            text(surface, self.ui(500, 14), "No notes to play", self.p.faint, rect.center,
                 "center")
            return
        lo = min(n.pitch for n in notes) - 1
        hi = max(n.pitch for n in notes) + 1
        sx = rect.w / song.duration
        sy = rect.h / max(1, hi - lo)
        backing_col = mix(self.p.muted, self.p.panel, 0.45)
        for group, is_backing in ((backing, True), (song.notes, False)):
            for n in group:
                color = backing_col if is_backing else self.hand_color(n.hand)
                x = rect.x + n.start_time * sx
                y = rect.bottom - (n.pitch - lo) * sy
                pygame.draw.rect(surface, color, (int(x), int(y - max(2, sy)),
                                                  max(2, int(n.duration * sx)), max(2, int(sy))))
        if lo < 60 < hi:
            y = rect.bottom - (60 - lo) * sy
            text(surface, self.ui(600, 10), "C4", self.p.faint, (rect.x - 8, int(y)), "midright")

    def draw_freeplay(self, surface: pygame.Surface, frame: FreePlayFrame) -> None:
        p = self.p
        w, h = surface.get_size()
        self.draw_backdrop(surface)
        layout = KeyLayout(36, 96, 0, w, h - 150, 150)
        hands = {pp: (Hand.RIGHT if pp >= 60 else Hand.LEFT) for pp in frame.pressed
                 if layout.contains(pp)}

        text(surface, self.display(800, 26), "Free Play", p.text, (40, 30))
        text(surface, self.ui(400, 14), "Play anything. Chords are named as you play.",
             p.muted, (40, 68))
        if frame.recording:
            dot_x = w - 120
            pygame.draw.circle(surface, p.miss, (dot_x, 46), 8)
            text(surface, self.ui(700, 16), "REC", p.miss, (dot_x + 16, 46), "midleft")

        chord = frame.chord or ("" if frame.pressed else "Play some keys")
        big = self.display(800, 72 if frame.chord else 28)
        text(surface, big, chord, p.text if frame.chord else p.faint, (w // 2, 230), "center")
        if frame.pressed:
            names = "  ".join(note_name(pp) for pp in sorted(frame.pressed))
            text(surface, self.ui(600, 18), names, p.muted, (w // 2, 300), "center")

        if frame.chord_history:
            tracked(surface, self.label(700, 12), "RECENT CHORDS", p.faint, (40, 360), 2)
            x = 40
            for name in frame.chord_history[-10:]:
                f = self.ui(600, 15)
                cw = f.size(name)[0] + 24
                rrect(surface, p.panel2, (x, 384, cw, 32), 16)
                text(surface, f, name, p.text, (x + cw // 2, 400), "center")
                x += cw + 8

        self.draw_keyboard(surface, layout, hands)
        hint = "R: start/stop recording   Esc: back"
        text(surface, self.ui(500, 13), hint, mix(p.faint, p.bg, 0.2), (40, h - 178))
