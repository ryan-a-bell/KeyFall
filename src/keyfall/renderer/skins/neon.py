"""Neon Arcade skin: rhythm-game look with glow, combos, sparks and light beams.

Effects scale with the "effects" setting: ``full`` (glow, beams, sparks),
``reduced`` (glow and beams, no sparks) and ``off`` (flat neon colors only).
"""

from __future__ import annotations

import math
import random

import pygame

from keyfall.models import Hand, HitGrade
from keyfall.renderer.draw import (
    Color,
    blit_rounded,
    chevron,
    glow,
    mix,
    radial,
    rrect,
    star,
    stretched_gradient,
    text,
    tracked,
    vgradient,
)
from keyfall.renderer.skins.base import Skin
from keyfall.renderer.skins.frames import MenuFrame, PlayFrame, grade_letter, points
from keyfall.renderer.skins.keys import KeyLayout, beat_seconds, is_black, label_for
from keyfall.renderer.theme import NEON

KEYBOARD_HEIGHT = 118
LOOK_AHEAD = 2.2
GRID = (122, 44, 255)
_JUDGEMENT_TEXT = {HitGrade.PERFECT: ("PERFECT", 300), HitGrade.GOOD: ("GREAT", 150),
                   HitGrade.OK: ("GOOD", 50), HitGrade.MISS: ("MISS", 0)}


class NeonSkin(Skin):
    theme = NEON

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._backdrop_cache: dict[tuple, pygame.Surface] = {}

    # ------------------------------------------------------------------ helpers
    def glow_text(self, surface, font, s: str, color: Color, pos, anchor="center",
                  strength: int = 1) -> pygame.Rect:
        """Text with a local bloom (blurs only the text's own box, not the screen)."""
        img = font.render(s, True, color)
        pad = max(12, font.get_height() // 2)
        box = pygame.Surface((img.get_width() + pad * 2, img.get_height() + pad * 2))
        box.blit(img, (pad, pad))
        rect = img.get_rect(**{anchor: pos})
        if self.glow_on:
            for _ in range(strength):
                small = pygame.transform.smoothscale(box, (max(1, box.get_width() // 6),
                                                           max(1, box.get_height() // 6)))
                surface.blit(pygame.transform.smoothscale(small, box.get_size()),
                             (rect.x - pad, rect.y - pad), special_flags=pygame.BLEND_RGB_ADD)
        surface.blit(font.render(s, True, mix(color, (255, 255, 255), 0.55)), rect)
        return rect

    def _glow_rect(self, surface, rect: pygame.Rect, color: Color, radius: int) -> None:
        if not self.glow_on:
            return
        pad = 24
        box = pygame.Surface((rect.w + pad * 2, rect.h + pad * 2))
        pygame.draw.rect(box, color, (pad, pad, rect.w, rect.h), border_radius=radius)
        small = pygame.transform.smoothscale(box, (max(1, box.get_width() // 8),
                                                   max(1, box.get_height() // 8)))
        surface.blit(pygame.transform.smoothscale(small, box.get_size()),
                     (rect.x - pad, rect.y - pad), special_flags=pygame.BLEND_RGB_ADD)

    def draw_backdrop(self, surface: pygame.Surface, horizon: int | None = None) -> None:
        """Night sky with stars and a synthwave grid floor (cached per size)."""
        w, h = surface.get_size()
        horizon = horizon if horizon is not None else int(h * 0.62)
        key = (w, h, horizon, self.glow_on)
        bg = self._backdrop_cache.get(key)
        if bg is None:
            bg = vgradient((w, h), self.p.bg, self.p.bg2).copy()
            rnd = random.Random(7)
            for _ in range(140):
                x, y = rnd.randint(0, w - 1), rnd.randint(0, horizon)
                c = rnd.randint(90, 220)
                bg.set_at((x, y), (c, c, min(255, c + 30)))
            layer = pygame.Surface((w, h))
            vx = w // 2
            for i in range(-14, 15):
                pygame.draw.line(layer, GRID, (vx + i * 18, horizon), (vx + i * 160, h), 1)
            for k in range(1, 12):
                y = horizon + (h - horizon) * (k / 11) ** 2
                pygame.draw.line(layer, GRID, (0, int(y)), (w, int(y)), 1)
            fade = vgradient((w, h - horizon), (0, 0, 0), (110, 110, 110))
            layer.subsurface((0, horizon, w, h - horizon)).blit(
                fade, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            layer.fill((0, 0, 0), (0, 0, w, horizon))
            bg.blit(layer, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
            if self.glow_on:
                glow(bg, layer, 0.1)
            bg.blit(radial((w, h), (w // 2, horizon), 520, (120, 30, 160), 0.8), (0, 0),
                    special_flags=pygame.BLEND_RGB_ADD)
            self._backdrop_cache[key] = bg
        surface.blit(bg, (0, 0))

    # ================================================================== gameplay
    def draw_play(self, surface: pygame.Surface, frame: PlayFrame) -> None:
        w, h = surface.get_size()
        lo, hi = self.song_range(frame.song)
        layout = KeyLayout(lo, hi, 0, w, h - KEYBOARD_HEIGHT, KEYBOARD_HEIGHT)
        hit_y = layout.y - 4
        top = 150 if frame.show_notation else 0

        self._draw_field(surface, frame, layout, hit_y)
        pressed = self.pressed_hands(frame, layout)
        if self.beams_on:
            for pitch, hand in pressed.items():
                x, lw = layout.lane(pitch)
                beam = stretched_gradient((int(lw) + 10, hit_y), (0, 0, 0),
                                 mix(self.hand_color(hand), (0, 0, 0), 0.45))
                surface.blit(beam, (int(x) - 5, 0), special_flags=pygame.BLEND_RGB_ADD)
        self.draw_backing(surface, frame, layout, pygame.Rect(0, 0, w, hit_y), LOOK_AHEAD,
                          (150, 110, 230), fill_alpha=30, edge_alpha=130,
                          clip=pygame.Rect(0, top, w, hit_y - top))
        self._draw_notes(surface, frame, layout, hit_y, top)
        self._draw_hit_line(surface, frame, layout, hit_y, pressed)
        self.draw_keyboard(surface, layout, pressed)
        if frame.show_notation:
            self.draw_notation_panel(surface, frame, pygame.Rect(0, 0, w, top))
        self._draw_hud(surface, frame, hit_y, top)

    def _draw_field(self, surface, frame: PlayFrame, layout: KeyLayout, hit_y: int) -> None:
        w, h = surface.get_size()
        key = ("field", w, h, layout.lo, layout.hi)
        field = self._backdrop_cache.get(key)
        if field is None:
            field = vgradient((w, h), (6, 2, 20), (26, 8, 50)).copy()
            for pitch in range(layout.lo - layout.lo % 12, layout.hi + 1, 12):
                if (pitch // 12) % 2 == 0 and layout.contains(pitch):
                    x0 = layout.x_of(pitch)
                    x1 = layout.x_of(pitch + 12) if layout.contains(pitch + 12) else w
                    rrect(field, (255, 255, 255), (int(x0), 0, int(x1 - x0), hit_y), 0, alpha=6)
            self._backdrop_cache[key] = field
        surface.blit(field, (0, 0))
        beat = beat_seconds(frame.song)
        pps = hit_y / LOOK_AHEAD
        first = math.floor(frame.position / beat)
        for b in range(first, first + int(LOOK_AHEAD / beat) + 2):
            y = hit_y - (b * beat - frame.position) * pps
            if 0 < y < hit_y:
                rrect(surface, GRID, (0, int(y), w, 1), 0, alpha=60 if b % 4 == 0 else 22)

    def _draw_notes(self, surface, frame: PlayFrame, layout: KeyLayout, hit_y: int,
                    top: int) -> None:
        w, h = surface.get_size()
        pps = hit_y / LOOK_AHEAD
        area = pygame.Rect(0, top, w, hit_y - top)
        dim = frame.active_hand != Hand.BOTH
        rects = []
        for n in sorted(self.note_index(frame.song).window(frame.position - 0.05,
                                                            frame.position + LOOK_AHEAD),
                        key=lambda n: is_black(n.pitch)):
            if not layout.contains(n.pitch):
                continue
            x, lw = layout.lane(n.pitch)
            y0 = hit_y - (n.start_time + n.duration - frame.position) * pps
            y1 = hit_y - (n.start_time - frame.position) * pps
            r = pygame.Rect(int(x), int(y0), int(lw), int(y1 - y0)).clip(area)
            if r.h <= 2:
                continue
            c = self.hand_color(n.hand)
            if dim and n.hand != frame.active_hand:
                c = mix(c, (20, 8, 40), 0.6)
            rects.append((r, c, n.pitch))
        if self.glow_on and rects:
            layer = pygame.Surface((w, h))
            for r, c, _ in rects:
                rrect(layer, c, r, 6)
            glow(surface, layer, 0.1)
        label_font = self.label(700, 13)
        for r, c, pitch in rects:
            gradient_card = stretched_gradient(r.size, mix(c, (0, 0, 0), 0.35), c)
            blit_rounded(surface, gradient_card, r.topleft, 6)
            pygame.draw.rect(surface, mix(c, (255, 255, 255), 0.7), r, 2, border_radius=6)
            lbl = label_for(pitch, self.label_mode)
            if lbl and r.h > 22 and r.w > 12:
                text(surface, label_font, lbl, (255, 255, 255), (r.centerx, r.bottom - 10),
                     "center")

    def _draw_hit_line(self, surface, frame: PlayFrame, layout: KeyLayout, hit_y: int,
                       pressed: dict[int, Hand]) -> None:
        w = surface.get_width()
        strip = pygame.Rect(0, hit_y - 70, w, 80)
        if self.glow_on:
            layer = pygame.Surface(strip.size)
            pygame.draw.rect(layer, (200, 120, 255), (0, 68, w, 4))
            for pitch, hand in pressed.items():
                x, lw = layout.lane(pitch)
                pygame.draw.circle(layer, self.hand_color(hand), (int(x + lw / 2), 70), 18)
            glow(surface.subsurface(strip), layer, 0.12)
        if self.particles_on:
            for pitch, hand in pressed.items():
                self._sparks(surface, layout, pitch, hand, hit_y, frame.clock)
        pygame.draw.line(surface, (255, 235, 255), (0, hit_y), (w, hit_y), 2)

    def _sparks(self, surface, layout: KeyLayout, pitch: int, hand: Hand, hit_y: int,
                clock: float) -> None:
        """Deterministic looping spark burst above a held key (no per-frame state)."""
        x, lw = layout.lane(pitch)
        cx = x + lw / 2
        c = mix(self.hand_color(hand), (255, 255, 255), 0.5)
        rnd = random.Random(pitch)
        for _ in range(9):
            ang = rnd.uniform(math.pi * 1.08, math.pi * 1.92)
            speed = rnd.uniform(40, 90)
            phase = (clock * 2.2 + rnd.random()) % 1.0
            ln = 8 + speed * phase
            ex, ey = cx + math.cos(ang) * ln, hit_y + math.sin(ang) * ln
            tail = max(4, ln - 14)
            sx, sy = cx + math.cos(ang) * tail, hit_y + math.sin(ang) * tail
            pygame.draw.line(surface, mix(c, (40, 10, 60), phase), (sx, sy), (ex, ey), 2)

    def _draw_hud(self, surface, frame: PlayFrame, hit_y: int, top: int) -> None:
        p = self.p
        w = surface.get_width()
        y0 = top
        scrim = vgradient((w, 140), (90, 90, 90), (255, 255, 255))
        surface.blit(scrim, (0, y0), special_flags=pygame.BLEND_RGB_MULT)
        rrect(surface, (255, 255, 255), (0, y0, w, 4), 0, alpha=25)
        bar = pygame.Rect(0, y0, int(w * frame.progress), 4)
        self._glow_rect(surface, bar, p.accent, 2)
        pygame.draw.rect(surface, p.accent, bar)

        # grade ring + title
        st = frame.stats
        c = (56, y0 + 50)
        pygame.draw.circle(surface, (60, 40, 100), c, 30, 5)
        if st.total_notes:
            pygame.draw.arc(surface, p.good, (c[0] - 30, c[1] - 30, 60, 60), math.pi / 2,
                            math.pi / 2 + 2 * math.pi * st.accuracy_pct / 100, 5)
        text(surface, self.display(900, 24), grade_letter(st.accuracy_pct, st.total_notes),
             p.gold, c, "center")
        text(surface, self.label(700, 22), frame.song.title.upper()[:30], p.text, (104, y0 + 22))
        mode = "WAIT MODE" if frame.wait_mode else f"TEMPO {frame.tempo_scale:.0%}"
        hands = {Hand.BOTH: "BOTH HANDS", Hand.RIGHT: "RIGHT HAND",
                 Hand.LEFT: "LEFT HAND"}[frame.active_hand]
        text(surface, self.label(600, 15), f"{frame.mode.upper()}   ·   {mode}   ·   {hands}",
             p.muted, (104, y0 + 46))
        acc = f"{st.accuracy_pct:.1f}% ACCURACY" if st.total_notes else "READY"
        text(surface, self.label(700, 15), acc, p.good, (104, y0 + 66))
        if frame.loop:
            text(surface, self.label(700, 15),
                 f"LOOP BARS {frame.loop[0]}-{frame.loop[1]}  ·  PASS {frame.loop_count + 1}",
                 p.gold, (104, y0 + 86))

        # score + combo
        text(surface, self.display(900, 30), f"{points(st):,}", p.text, (w - 24, y0 + 16),
             "topright")
        text(surface, self.label(600, 15), "SCORE", p.muted, (w - 24, y0 + 54), "topright")
        if frame.streak >= 2:
            self.glow_text(surface, self.display(900, 60), str(frame.streak), p.accent,
                           (w // 2, y0 + 52))
            tracked(surface, self.label(700, 18), "COMBO", p.muted, (w // 2, y0 + 90), 6, "midtop")

        # judgement pop-up
        if frame.judgement is not None and frame.judgement_age < 0.7:
            label, pts = _JUDGEMENT_TEXT[frame.judgement]
            color = p.miss if frame.judgement == HitGrade.MISS else p.gold
            lift = int(frame.judgement_age * 40)
            plate = pygame.Rect(0, 0, 250, 78)
            plate.center = (w // 2, hit_y - 170 - lift)
            rrect(surface, (8, 3, 24), plate, 16, alpha=150)
            self.glow_text(surface, self.display(900, 34), label, color,
                           (plate.centerx, plate.y + 30), strength=2)
            if pts:
                text(surface, self.display(700, 16), f"+{pts}", color,
                     (plate.centerx, plate.y + 60), "center")

        # groove meter (accuracy)
        gm = pygame.Rect(w - 40, y0 + 130, 12, max(60, hit_y - y0 - 220))
        rrect(surface, (255, 255, 255), gm, 6, alpha=20)
        fill_h = int(gm.h * (st.accuracy_pct / 100 if st.total_notes else 0))
        if fill_h > 0:
            surface.blit(vgradient((gm.w, fill_h), p.gold, p.accent2), (gm.x, gm.bottom - fill_h))
        pygame.draw.rect(surface, p.bg, gm.inflate(2, 2), 2, border_radius=7)
        text(surface, self.label(700, 13), "GROOVE", p.muted, (gm.centerx, gm.bottom + 8), "midtop")

        if frame.paused:
            self._draw_paused(surface, frame, hit_y)

    def _draw_paused(self, surface, frame: PlayFrame, hit_y: int) -> None:
        p = self.p
        w = surface.get_width()
        veil = pygame.Surface((w, hit_y), pygame.SRCALPHA)
        veil.fill((6, 2, 20, 180))
        surface.blit(veil, (0, 0))
        self.glow_text(surface, self.display(900, 44), "PAUSED", p.accent2, (w // 2, 230),
                       strength=2)
        keys = [("SPACE", "RESUME"), ("W", "WAIT MODE"), ("- / =", "TEMPO"),
                ("1 2 3", "HANDS"), ("R", "RESTART"), ("ESC", "MENU")]
        x = w // 2 - 330
        for k, label in keys:
            kw = self.label(700, 15).size(k)[0] + 18
            rrect(surface, (255, 255, 255), (x, 300, kw, 26), 6, alpha=28)
            text(surface, self.label(700, 15), k, p.text, (x + kw // 2, 313), "center")
            r = text(surface, self.label(600, 15), label, p.muted, (x + kw + 8, 304))
            x = r.right + 22

    def draw_keyboard(self, surface, layout: KeyLayout, pressed: dict[int, Hand]) -> None:
        w = surface.get_width()
        for pitch in range(layout.lo, layout.hi + 1):
            if is_black(pitch):
                continue
            r = layout.key_rect(pitch)
            if pitch in pressed:
                surface.blit(vgradient((r.w - 1, r.h), (255, 255, 255),
                                       self.hand_color(pressed[pitch])), r.topleft)
            else:
                surface.blit(vgradient((r.w - 1, r.h), (206, 200, 228), (246, 244, 255)),
                             r.topleft)
            pygame.draw.line(surface, (120, 100, 160), (r.right - 1, r.y), (r.right - 1, r.bottom))
        for pitch in range(layout.lo, layout.hi + 1):
            if not is_black(pitch):
                continue
            r = layout.key_rect(pitch)
            if pitch in pressed:
                c = self.hand_color(pressed[pitch])
                surface.blit(vgradient(r.size, mix(c, (0, 0, 0), 0.3), c), r.topleft)
            else:
                surface.blit(vgradient(r.size, (10, 6, 22), (48, 36, 78)), r.topleft)
        surface.blit(vgradient((w, 12), (60, 30, 90), (255, 255, 255)), (0, layout.y),
                     special_flags=pygame.BLEND_RGB_MULT)

    # ================================================================== menu
    def _album_art(self, size: tuple[int, int], title: str) -> pygame.Surface:
        key = ("art", size, title)
        art = self._backdrop_cache.get(key)
        if art is not None:
            return art
        seed = sum(ord(c) * (i + 1) for i, c in enumerate(title))
        rnd = random.Random(seed)
        hues = [(40, 120, 255), (255, 140, 40), (255, 47, 208), (24, 231, 255), (120, 90, 255),
                (75, 255, 155)]
        a = hues[seed % len(hues)]
        b = rnd.choice([(20, 10, 60), (80, 10, 60), (40, 8, 90), (10, 10, 40)])
        w, h = size
        art = vgradient(size, a, b).copy()
        sun_y = int(h * 0.62)
        pygame.draw.circle(art, mix(a, (255, 255, 255), 0.4), (w // 2, sun_y), int(w * 0.28))
        for k in range(6):
            pygame.draw.line(art, b, (0, sun_y + k * 7 - 6), (w, sun_y + k * 7 - 6), 3)
        for _ in range(18):
            bh = rnd.randint(10, max(11, h // 3))
            pygame.draw.rect(art, mix(b, (0, 0, 0), 0.5),
                             (rnd.randint(0, w), h - bh, rnd.randint(8, 18), bh))
        self._backdrop_cache[key] = art
        return art

    def draw_menu(self, surface: pygame.Surface, frame: MenuFrame) -> None:
        p = self.p
        w, h = surface.get_size()
        self.draw_backdrop(surface, horizon=470)

        # status chips
        for i, (label, ok) in enumerate((("MIDI", frame.midi_connected),
                                         ("OUT", frame.output_connected),
                                         ("SOUND", frame.sound_ok))):
            x = 28 + i * 120
            rrect(surface, (255, 255, 255), (x, 26, 108, 34), 10, alpha=14)
            rrect(surface, p.good if ok else p.faint, (x, 26, 108, 34), 10, alpha=140, width=1)
            pygame.draw.circle(surface, p.good if ok else p.faint, (x + 18, 43), 5)
            text(surface, self.label(700, 15), label, p.text if ok else p.muted, (x + 30, 33))
            text(surface, self.label(600, 12), "ON" if ok else "OFF", p.muted, (x + 96, 35),
                 "topright")
        hands = f"HANDS: {frame.hand_split.upper()}"
        hw = self.label(700, 15).size(hands)[0] + 28
        rrect(surface, (255, 255, 255), (w - 28 - hw, 26, hw, 34), 10, alpha=14)
        rrect(surface, p.accent2, (w - 28 - hw, 26, hw, 34), 10, alpha=140, width=1)
        text(surface, self.label(700, 15), hands, p.text, (w - 28 - hw // 2, 43), "center")

        self.glow_text(surface, self.display(900, 54), "KEYFALL", p.accent2, (w // 2, 66),
                       strength=2)

        # mode tabs
        tab_font = self.label(700, 22)
        total = sum(tab_font.size(m.upper())[0] for m in frame.modes) + 46 * (len(frame.modes) - 1)
        tx = w // 2 - total // 2
        for i, mode in enumerate(frame.modes):
            r = text(surface, tab_font, mode.upper(), p.text if i == frame.mode else p.muted,
                     (tx, 116))
            if i == frame.mode:
                line = pygame.Rect(r.x, r.bottom + 2, r.w, 3)
                self._glow_rect(surface, line, p.accent, 2)
                pygame.draw.rect(surface, p.accent, line)
            tx = r.right + 46

        cy = 320
        if frame.songs:
            self._carousel(surface, frame, cy)
        else:
            text(surface, self.label(700, 26), "NO SONGS LOADED", p.text, (w // 2, cy - 20),
                 "center")
            text(surface, self.label(600, 17), "START KEYFALL WITH --songs-dir PATH", p.muted,
                 (w // 2, cy + 14), "center")

        # play button
        btn = pygame.Rect(0, 0, 280, 58)
        btn.center = (w // 2, 552)
        self._glow_rect(surface, btn, p.accent, 29)
        blit_rounded(surface, vgradient(btn.size, (90, 245, 255), (10, 170, 230)), btn.topleft, 29)
        pygame.draw.rect(surface, p.bg, btn.inflate(4, 4), 3, border_radius=31)
        label = frame.modes[frame.mode].upper()
        lf = self.display(900, 22)
        lw = lf.size(label)[0] + 30
        lx = btn.centerx - lw // 2
        pygame.draw.polygon(surface, p.bg, [(lx, btn.y + 18), (lx, btn.y + 40),
                                            (lx + 18, btn.y + 29)])
        text(surface, lf, label, p.bg, (lx + 30, btn.centery), "midleft")

        info = []
        if frame.songs:
            song = frame.songs[frame.selected]
            info.append(f"BEST {song.best_accuracy:.0f}%" if song.best_accuracy is not None
                        else "NEW SONG")
            if frame.details:
                d = frame.details
                info.append(f"{int(d.duration) // 60}:{int(d.duration) % 60:02d}")
                info.append(f"{d.note_count} NOTES")
        text(surface, self.label(600, 16), "  ·  ".join(info), p.muted, (w // 2, 600), "center")
        if frame.error:
            text(surface, self.label(600, 15), frame.error, p.miss, (w // 2, 628), "center")

        hx = w // 2 - 330
        for key, label in (("ARROWS", "SELECT"), ("ENTER", "START"), ("TAB", "MODE"),
                           ("H", "HANDS"), ("S", "SETTINGS"), ("ESC", "QUIT")):
            kw = self.label(700, 15).size(key)[0] + 18
            rrect(surface, (255, 255, 255), (hx, 660, kw, 26), 6, alpha=28)
            rrect(surface, p.muted, (hx, 660, kw, 26), 6, alpha=120, width=1)
            text(surface, self.label(700, 15), key, p.text, (hx + kw // 2, 673), "center")
            r = text(surface, self.label(600, 15), label, p.muted, (hx + kw + 8, 663))
            hx = r.right + 22

    def _carousel(self, surface, frame: MenuFrame, cy: int) -> None:
        p = self.p
        w = surface.get_width()
        n = len(frame.songs)
        offsets = [o for o in (-2, 2, -1, 1, 0) if 0 <= frame.selected + o < n]
        for off in offsets:
            song = frame.songs[frame.selected + off]
            scale = 1.0 if off == 0 else 0.78 if abs(off) == 1 else 0.6
            cw, ch = int(250 * scale), int(310 * scale)
            cx = w // 2 + off * 250 - (0 if off == 0 else int(math.copysign(30 * abs(off), off)))
            rect = pygame.Rect(0, 0, cw, ch)
            rect.center = (cx, cy)
            if off == 0:
                self._glow_rect(surface, rect.inflate(8, 8), p.accent2, 20)
            card = pygame.Surface(rect.size)
            card.fill((24, 12, 48))
            art_h = int(ch * 0.62)
            card.blit(self._album_art((cw, art_h), song.title), (0, 0))
            if off != 0:
                veil = pygame.Surface(rect.size, pygame.SRCALPHA)
                veil.fill((8, 3, 26, 120 if abs(off) == 1 else 170))
                card.blit(veil, (0, 0))
            blit_rounded(surface, card, rect.topleft, 18)
            pygame.draw.rect(surface, p.accent2 if off == 0 else (90, 60, 140), rect, 2,
                             border_radius=18)
            if abs(off) > 1:
                continue
            ty = rect.y + art_h + 10
            fs = 22 if off == 0 else 17
            title = song.title.upper()
            tf = self.label(700, fs)
            while tf.size(title)[0] > cw - 28 and len(title) > 3:
                title = title[:-2] + "…"
            text(surface, tf, title, p.text, (rect.x + 14, ty))
            text(surface, self.label(500, fs - 6), song.kind, p.muted, (rect.x + 14, ty + fs + 2))
            level = frame.details.difficulty_level if (off == 0 and frame.details) else None
            if level:
                stars = max(1, min(5, math.ceil(level / 3.6)))
                for k in range(5):
                    col = p.gold if k < stars else (70, 50, 110)
                    star(surface, col, (rect.x + 20 + k * 16, rect.bottom - 24), 6)
            if song.best_accuracy is not None:
                grade = grade_letter(song.best_accuracy, 1)
                gc = {"S": p.gold, "A": p.accent, "B": p.good}.get(grade, p.muted)
                badge = (rect.right - 30, rect.y + 30)
                rad = 20 if off == 0 else 16
                pygame.draw.circle(surface, (10, 4, 30), badge, rad)
                pygame.draw.circle(surface, gc, badge, rad, 2)
                text(surface, self.display(900, 18 if off == 0 else 14), grade, gc, badge, "center")
        if frame.selected > 0:
            chevron(surface, p.muted, (w // 2 - 590, cy), 16, "left", 3)
        if frame.selected < n - 1:
            chevron(surface, p.muted, (w // 2 + 590, cy), 16, "right", 3)
