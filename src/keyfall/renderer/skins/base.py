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
    CoachFrame,
    FreePlayFrame,
    MenuFrame,
    PlayFrame,
    ResultsFrame,
    SettingsFrame,
    SettingsRow,
    StemsFrame,
    grade_letter,
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
        self._deferred: list | None = None  # field text held back while drawing flipped
        self._field_buf: pygame.Surface | None = None
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
        text(surface, label_font, label, p.text, (r.x + 20, r.y + (8 if r.h < 56 else 12)))
        if row.adjustable and row.button:
            desc_y = r.y + (r.h - 22 if r.h < 64 else 38)
            text(surface, self.ui(400, 13), row.description, p.muted, (r.x + 20, desc_y))
            bf = self.ui(700, 14)
            bw = bf.size(row.value)[0] + 32
            btn = pygame.Rect(r.right - 20 - bw, 0, bw, 30)
            btn.centery = r.centery
            if row.progress is not None:
                rrect(surface, p.line, btn, 15)
                old_clip = surface.get_clip()
                surface.set_clip(pygame.Rect(btn.x, btn.y, int(btn.w * row.progress), btn.h))
                rrect(surface, p.accent, btn, 15)  # clipped so the fill keeps the pill shape
                surface.set_clip(old_clip)
                text(surface, bf, row.value, p.text, btn.center, "center")
            elif row.value.startswith("Installed"):
                text(surface, bf, row.value, p.good, (btn.right, btn.centery), "midright")
            else:
                if selected:
                    rrect(surface, p.accent, btn, 15)
                else:
                    rrect(surface, p.accent, btn, 15, width=2)
                text(surface, bf, row.value, (255, 255, 255) if selected else p.accent,
                     btn.center, "center")
        elif row.adjustable:
            desc_y = r.y + (r.h - 22 if r.h < 64 else 38)
            text(surface, self.ui(400, 13), row.description, p.muted, (r.x + 20, desc_y))
            val_font = self.ui(700, 16)
            value = row.value
            while len(value) > 4 and val_font.size(value)[0] > 250:
                value = value[:-2] + "…"
            vw = val_font.size(value)[0]
            vx = r.right - 44 - vw
            color = self.swatch_color(row.swatch) if row.swatch else (
                p.accent if selected else p.text)
            cy = r.y + (20 if r.h < 56 else 24)
            if row.swatch:
                pygame.draw.circle(surface, color, (vx - 34, cy), 5)
            text(surface, val_font, value, color, (vx, cy - 10))
            col = p.accent if selected else p.faint
            chevron(surface, col, (vx - 16, cy), 5, "left")
            chevron(surface, col, (r.right - 28, cy), 5, "right")
        return r

    def draw_settings(self, surface: pygame.Surface, frame: SettingsFrame) -> None:
        p = self.p
        w, h = surface.get_size()
        self.draw_backdrop(surface)
        text(surface, self.display(800, 32), "Settings", p.text, (60, 40))
        text(surface, self.ui(400, 15), "Changes apply instantly and are saved automatically.",
             p.muted, (60, 86))

        y = top = 120
        n = len(frame.rows)
        row_h, gap = (68, 10) if n <= 6 else (58, 6) if n <= 8 else (52, 5)
        visible = max(1, (h - top - 50) // (row_h + gap))
        start = max(0, min(frame.selected - visible // 2, n - visible))
        for i in range(start, min(n, start + visible)):
            r = self._draw_row(surface, frame.rows[i], i == frame.selected, 48, y, 560, row_h)
            y = r.bottom + gap
        if start > 0:
            chevron(surface, p.muted, (328, top - 9), 6, "up")
        if start + visible < n:
            chevron(surface, p.muted, (328, y + 4), 6, "down")

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

    # ------------------------------------------------------------ rising layout
    # The playing field (notes, lanes, hit line, keyboard, sparks) is drawn exactly
    # as in the falling layout, into an off-screen buffer, then flipped vertically
    # onto the screen. Text inside the field is held back and drawn upright at its
    # mirrored position, so labels never appear upside down.
    def field_text(self, surface: pygame.Surface, font: pygame.font.Font, s: str, color,
                   pos, anchor: str = "topleft") -> None:
        if self._deferred is not None:
            self._deferred.append((font, s, color, pos, anchor))
        else:
            text(surface, font, s, color, pos, anchor)

    def begin_field(self, surface: pygame.Surface, rising: bool) -> pygame.Surface:
        """Where to draw the field: the screen, or a buffer to flip afterwards."""
        if not rising:
            self._deferred = None
            return surface
        if self._field_buf is None or self._field_buf.get_size() != surface.get_size():
            self._field_buf = pygame.Surface(surface.get_size())
        self._deferred = []
        return self._field_buf

    def end_field(self, surface: pygame.Surface, buf: pygame.Surface, field: pygame.Rect,
                  dest_y: int) -> None:
        """Flip ``field`` (drawn into ``buf``) vertically onto ``surface`` at ``dest_y``."""
        if buf is surface:
            return
        surface.blit(pygame.transform.flip(buf.subsurface(field), False, True),
                     (field.x, dest_y))
        swap = {"top": "bottom", "bottom": "top"}
        for font, s, color, (x, y), anchor in self._deferred or []:
            for a, b in swap.items():
                if anchor.startswith(a):
                    anchor = b + anchor[len(a):]
                    break
            text(surface, font, s, color, (x, dest_y + (field.bottom - y)), anchor)
        self._deferred = None

    @staticmethod
    def flip_rect(rect: pygame.Rect, field: pygame.Rect, dest_y: int) -> pygame.Rect:
        """Where ``rect`` (inside ``field``) ends up after the field is flipped."""
        return pygame.Rect(rect.x, dest_y + (field.bottom - rect.bottom), rect.w, rect.h)

    # ------------------------------------------------------------ shared overlays
    def draw_grade(self, surface: pygame.Surface, letter: str, center, size: int) -> None:
        """Big grade letter; skins can override for effects (Neon glows)."""
        color = self.p.gold if letter == "S" else self.p.accent if letter in "AB" else self.p.text
        text(surface, self.display(900, size), letter, color, center, "center")

    def draw_count_in(self, surface: pygame.Surface, frame: PlayFrame,
                      area: pygame.Rect) -> None:
        """Large "4 3 2 1" during the count-in bar."""
        if frame.count_in is None or frame.count_in <= 0:
            return
        box = pygame.Rect(0, 0, 150, 150)
        box.center = area.center
        rrect(surface, self.p.bg, box, 75, alpha=170)
        rrect(surface, self.p.accent, box, 75, alpha=200, width=3)
        text(surface, self.display(800, 72), str(frame.count_in), self.p.text, box.center,
             "center")
        text(surface, self.ui(600, 14), "Get ready", self.p.muted, (box.centerx, box.bottom + 16),
             "center")

    def draw_results(self, surface: pygame.Surface, frame: ResultsFrame) -> None:
        p = self.p
        w, h = surface.get_size()
        r = frame.result
        st = r.stats
        self.draw_backdrop(surface)
        tracked(surface, self.label(700, 13), f"{r.mode.upper()} COMPLETE", p.muted, (60, 40), 2)
        title = r.title if len(r.title) < 48 else r.title[:46] + "…"
        text(surface, self.display(800, 32), title, p.text, (60, 62))

        # grade card
        card = pygame.Rect(60, 128, 360, 330)
        rrect(surface, p.panel, card, 16, alpha=235)
        letter = grade_letter(st.accuracy_pct, st.total_notes)
        self.draw_grade(surface, letter, (card.centerx, card.y + 100), 120)
        acc = f"{st.accuracy_pct:.1f}%" if st.total_notes else "—"
        text(surface, self.display(800, 36), acc, p.text, (card.centerx, card.y + 200), "center")
        text(surface, self.ui(500, 14), "accuracy", p.muted, (card.centerx, card.y + 230), "center")
        if r.best_before is None:
            line, color = "First time playing this song", p.muted
        elif st.accuracy_pct > r.best_before + 0.05:
            line, color = f"New best!  +{st.accuracy_pct - r.best_before:.1f}%", p.good
        else:
            line, color = f"Best {r.best_before:.1f}%", p.muted
        text(surface, self.ui(700, 16), line, color, (card.centerx, card.y + 272), "center")
        text(surface, self.ui(500, 14), f"Longest streak {st.max_streak}", p.muted,
             (card.centerx, card.y + 298), "center")

        # hit breakdown
        x0 = 460
        tracked(surface, self.label(700, 12), "NOTES", p.muted, (x0, 130), 2)
        total = max(1, st.total_notes)
        rows = [("Perfect", st.perfect, p.good), ("Good", st.good, p.accent),
                ("OK", st.ok, p.gold), ("Missed", st.missed, p.miss)]
        bar_w = w - x0 - 60 - 160
        for i, (label, count, color) in enumerate(rows):
            y = 156 + i * 34
            text(surface, self.ui(600, 15), label, p.text, (x0, y))
            track = pygame.Rect(x0 + 90, y + 4, bar_w, 12)
            rrect(surface, p.panel2, track, 6)
            rrect(surface, color, (track.x, track.y, int(track.w * count / total), track.h), 6)
            text(surface, self.ui(700, 15), str(count), p.text, (track.right + 16, y))

        # timing histogram
        tracked(surface, self.label(700, 12), "TIMING", p.muted, (x0, 304), 2)
        bins = [0] * 21
        for off in r.timing_offsets_ms:
            bins[max(0, min(20, int((off + 210) / 20)))] += 1
        peak = max(bins) or 1
        hist = pygame.Rect(x0, 328, w - x0 - 60, 90)
        bw = hist.w / len(bins)
        for i, v in enumerate(bins):
            bh = max(2, int(hist.h * v / peak)) if v else 2
            color = p.good if 7 <= i <= 13 else p.muted
            rrect(surface, color, (int(hist.x + i * bw + 2), hist.bottom - bh, int(bw - 4), bh), 3)
        pygame.draw.line(surface, p.line, (hist.centerx, hist.y), (hist.centerx, hist.bottom))
        text(surface, self.ui(500, 12), "early", p.faint, (hist.x, hist.bottom + 6))
        text(surface, self.ui(500, 12), "on time", p.faint, (hist.centerx, hist.bottom + 6),
             "midtop")
        text(surface, self.ui(500, 12), "late", p.faint, (hist.right, hist.bottom + 6),
             "topright")
        if r.timing_offsets_ms:
            avg = sum(r.timing_offsets_ms) / len(r.timing_offsets_ms)
            lean = "on time" if abs(avg) < 15 else ("late" if avg > 0 else "early")
            text(surface, self.ui(500, 13), f"Average {abs(avg):.0f} ms {lean}", p.muted,
                 (hist.right, 304), "topright")

        # trouble spot
        trouble = r.trouble
        tip_y = 478
        if trouble:
            tip = f"Most misses in bars {trouble[0]}–{trouble[1]} ({trouble[2]} missed)."
            tip += " A short loop there is the fastest way to improve."
        elif st.total_notes and st.missed == 0:
            tip = "No missed notes. Try a faster tempo next time."
        else:
            tip = ""
        if tip:
            text(surface, self.ui(500, 15), tip, p.text, (60, tip_y))

        # buttons
        bx = 60
        for i, label in enumerate(frame.buttons):
            f = self.ui(700, 16)
            bw2 = f.size(label)[0] + 48
            btn = pygame.Rect(bx, h - 150, bw2, 50)
            if i == frame.selected:
                rrect(surface, p.accent, btn, 25)
                text(surface, f, label, (255, 255, 255), btn.center, "center")
            else:
                rrect(surface, p.line, btn, 25, width=2)
                text(surface, f, label, p.text, btn.center, "center")
            bx = btn.right + 14
        hints = "Left/Right: choose   Enter: go   R: play again"
        if any(b.startswith("Practice") for b in frame.buttons):
            hints += "   P: practice bars"
        text(surface, self.ui(500, 13), hints + "   Esc: menu", p.faint, (60, h - 60))

    def draw_coach(self, surface: pygame.Surface, frame: CoachFrame) -> None:
        p = self.p
        w, h = surface.get_size()
        self.draw_backdrop(surface)
        tracked(surface, self.label(700, 13), "PRACTICE COACH", p.accent, (60, 36), 2)
        title = frame.title if len(frame.title) < 46 else frame.title[:44] + "…"
        text(surface, self.display(800, 30), title, p.text, (60, 58))

        # overall mastery ring + today
        c = (w - 110, 82)
        pygame.draw.circle(surface, p.panel2, c, 46, 8)
        if frame.mastery > 0:
            import math as _m
            pygame.draw.arc(surface, p.good, (c[0] - 46, c[1] - 46, 92, 92), _m.pi / 2,
                            _m.pi / 2 + 2 * _m.pi * frame.mastery, 8)
        text(surface, self.display(800, 22), f"{frame.mastery:.0%}", p.text, c, "center")
        text(surface, self.ui(500, 12), "learned", p.muted, (c[0], c[1] + 58), "center")
        today = f"Today: {frame.today_passes} pass{'es' if frame.today_passes != 1 else ''}" \
                f" · {frame.today_minutes:.0f} min"
        text(surface, self.ui(500, 13), today, p.muted, (w - 190, 150), "topright")

        # section map
        tracked(surface, self.label(700, 12), "SECTIONS", p.muted, (60, 120), 2)
        tile_w, gap = 74, 8
        per_row = max(1, (w - 120 - 200) // (tile_w + gap))
        for k, sec in enumerate(frame.sections[: per_row * 2]):
            x = 60 + (k % per_row) * (tile_w + gap)
            y = 144 + (k // per_row) * 70
            r = pygame.Rect(x, y, tile_w, 60)
            rrect(surface, p.panel, r, 10)
            fill_h = int(r.h * sec.progress)
            if fill_h:
                color = p.good if sec.mastered else p.accent
                rrect(surface, color, (r.x, r.bottom - fill_h, r.w, fill_h), 10, alpha=110)
            if sec.current:
                rrect(surface, p.accent, r.inflate(4, 4), 12, width=2)
            text(surface, self.ui(700, 13), f"{sec.first_bar}–{sec.last_bar}", p.text,
                 (r.centerx, r.y + 18), "center")
            stage = ("Done" if sec.mastered else
                     f"{sec.tempo_pct}%" if sec.rung == "tempo" else
                     {"right": "R hand", "left": "L hand", "together": "Both"}.get(sec.rung, ""))
            text(surface, self.ui(500, 11), stage, p.muted, (r.centerx, r.y + 40), "center")
        rows = min(2, max(1, -(-len(frame.sections) // per_row)))
        top = 144 + rows * 70 + 16
        if len(frame.sections) > per_row * 2:
            text(surface, self.ui(500, 12), f"+{len(frame.sections) - per_row * 2} more",
                 p.faint, (60, top - 10))
            top += 12

        # next step card
        card = pygame.Rect(60, max(top, 230), w - 120 - 340, 150)
        rrect(surface, p.panel, card, 14, alpha=240)
        rrect(surface, p.accent, (card.x, card.y + 16, 4, card.h - 32), 2)
        tracked(surface, self.label(700, 12), "NEXT STEP", p.accent, (card.x + 24, card.y + 18), 2)
        text(surface, self.display(800, 22), frame.step_label, p.text, (card.x + 24, card.y + 42))
        text(surface, self.ui(400, 14), frame.step_why, p.muted, (card.x + 24, card.y + 80))
        if frame.verdict:
            text(surface, self.ui(700, 15), frame.verdict,
                 p.good if frame.verdict_good else p.gold, (card.x + 24, card.y + 112))

        # tips + progress chart
        side = pygame.Rect(card.right + 20, card.y, w - 60 - card.right - 20, 150)
        rrect(surface, p.panel, side, 14, alpha=240)
        tracked(surface, self.label(700, 12), "PROGRESS BY DAY", p.muted,
                (side.x + 18, side.y + 16), 2)
        chart = pygame.Rect(side.x + 18, side.y + 44, side.w - 36, side.h - 66)
        if frame.daily:
            bw = min(26, chart.w // max(1, len(frame.daily)) - 4)
            for k, (_day, acc) in enumerate(frame.daily):
                bh = max(3, int(chart.h * acc / 100))
                color = p.good if acc >= 90 else p.accent if acc >= 60 else p.miss
                rrect(surface, color, (chart.x + k * (bw + 4), chart.bottom - bh, bw, bh), 3)
        else:
            text(surface, self.ui(500, 13), "Your daily accuracy will appear here.", p.faint,
                 chart.center, "center")

        y = card.bottom + 22
        if frame.tips:
            tracked(surface, self.label(700, 12), "TECHNIQUE", p.muted, (60, y), 2)
            for k, tip in enumerate(frame.tips):
                text(surface, self.ui(500, 14), f"•  {tip}", p.text, (60, y + 22 + k * 22))

        bx = 60
        for k, label in enumerate(frame.buttons):
            f = self.ui(700, 16)
            btn = pygame.Rect(bx, h - 110, f.size(label)[0] + 48, 50)
            if k == frame.selected:
                rrect(surface, p.accent, btn, 25)
                text(surface, f, label, (255, 255, 255), btn.center, "center")
            else:
                rrect(surface, p.line, btn, 25, width=2)
                text(surface, f, label, p.text, btn.center, "center")
            bx = btn.right + 14
        text(surface, self.ui(500, 13), "Left/Right: choose   Enter: go   Esc: menu", p.faint,
             (60, h - 40))

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
