"""Studio skin: modern and professional (calm palette, Inter, practice analytics)."""

from __future__ import annotations

import math
from pathlib import Path

import pygame

from keyfall.models import Hand
from keyfall.renderer.draw import (
    blit_rounded,
    chevron,
    gradient_rect,
    mix,
    radial,
    rrect,
    shadow,
    text,
    tracked,
    vgradient,
)
from keyfall.renderer.skins.base import Skin
from keyfall.renderer.skins.frames import MenuFrame, PlayFrame, grade_letter
from keyfall.renderer.skins.keys import (
    KeyLayout,
    beat_seconds,
    beats_per_bar,
    is_black,
    label_for,
    note_name,
)
from keyfall.renderer.theme import STUDIO

TOP_BAR = 64
KEYBOARD_HEIGHT = 128
LOOK_AHEAD = 2.6
FELT = (123, 30, 44)


def _fmt_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class StudioSkin(Skin):
    theme = STUDIO

    def draw_backdrop(self, surface: pygame.Surface) -> None:
        w, h = surface.get_size()
        surface.fill(self.p.bg)
        surface.blit(radial((w, h), (int(w * 0.7), -100), 900, (18, 22, 40)), (0, 0),
                     special_flags=pygame.BLEND_RGB_ADD)

    # ================================================================== gameplay
    def draw_play(self, surface: pygame.Surface, frame: PlayFrame) -> None:
        p = self.p
        w, h = surface.get_size()
        lo, hi = self.song_range(frame.song)
        notation_h = 170 if frame.show_notation else 0
        below = frame.sheet_below and notation_h > 0
        kb_bottom = h - notation_h if below else h  # sheet music under the piano, if chosen
        layout = KeyLayout(lo, hi, 0, w, kb_bottom - KEYBOARD_HEIGHT, KEYBOARD_HEIGHT)
        top = TOP_BAR + (0 if below else notation_h)
        area = pygame.Rect(0, top, w, layout.y - 5 - top)

        surface.blit(vgradient((w, h), p.bg, p.bg2), (0, 0))
        self._draw_lanes(surface, frame, layout, area)
        self.draw_backing(surface, frame, layout, area, LOOK_AHEAD, (160, 168, 184),
                          fill_alpha=36, edge_alpha=110)
        self._draw_notes(surface, frame, layout, area)
        pygame.draw.line(surface, (255, 255, 255), (0, area.bottom - 1), (w, area.bottom - 1))
        self.draw_keyboard(surface, layout, self.pressed_hands(frame, layout))
        self._draw_top_bar(surface, frame)
        if frame.show_notation:
            y = kb_bottom if below else TOP_BAR
            self.draw_notation_panel(surface, frame, pygame.Rect(0, y, w, notation_h))
        self._draw_stats_card(surface, frame, pygame.Rect(w - 236, area.y + 16, 212, 150))
        self.draw_count_in(surface, frame, area)
        if frame.paused:
            self._draw_paused(surface, frame, area)

    def _draw_lanes(self, surface, frame: PlayFrame, layout: KeyLayout, area) -> None:
        p = self.p
        for pitch in range(layout.lo, layout.hi + 1):
            if pitch % 12 in (0, 5):
                x = int(layout.x_of(pitch))
                col = (30, 34, 42) if pitch % 12 == 0 else (22, 25, 32)
                pygame.draw.line(surface, col, (x, area.y), (x, area.bottom))
        beat = beat_seconds(frame.song)
        per_bar = beats_per_bar(frame.song)
        pps = area.h / LOOK_AHEAD
        first = math.floor(frame.position / beat)
        for b in range(first, first + int(LOOK_AHEAD / beat) + 2):
            y = area.bottom - (b * beat - frame.position) * pps
            if area.y < y < area.bottom:
                downbeat = b % per_bar == 0
                pygame.draw.line(surface, (40, 45, 56) if downbeat else (24, 27, 34),
                                 (0, int(y)), (area.right, int(y)))
                if downbeat and b >= 0:
                    first_bar = frame.loop[0] if frame.loop else 1  # real bar numbers in loops
                    text(surface, self.ui(600, 11), str(b // per_bar + first_bar),
                                    p.faint, (8, int(y) - 16))

    def _draw_notes(self, surface, frame: PlayFrame, layout: KeyLayout, area) -> None:
        pps = area.h / LOOK_AHEAD
        label_font = self.ui(700, 10)
        notes = self.note_index(frame.song).window(frame.position - 0.05,
                                                   frame.position + LOOK_AHEAD)
        dim = frame.active_hand != Hand.BOTH
        for n in sorted(notes, key=lambda n: is_black(n.pitch)):
            if not layout.contains(n.pitch):
                continue
            x, lw = layout.lane(n.pitch)
            y0 = area.bottom - (n.start_time + n.duration - frame.position) * pps
            y1 = area.bottom - (n.start_time - frame.position) * pps
            r = pygame.Rect(int(x), int(y0), int(lw), int(y1 - y0)).clip(area)
            if r.h <= 0:
                continue
            c = self.hand_color(n.hand)
            if is_black(n.pitch):
                c = mix(c, (0, 0, 0), 0.25)
            if dim and n.hand != frame.active_hand:
                c = mix(c, self.p.bg, 0.65)  # the other hand is auto-played
            rrect(surface, c, r, 5)
            pygame.draw.line(surface, mix(c, (255, 255, 255), 0.35), (r.x + 4, r.y + 1),
                             (r.right - 5, r.y + 1))
            lbl = label_for(n.pitch, self.label_mode)
            if lbl and r.h > 22 and lw > 12:
                text(surface, label_font, lbl, mix(c, (0, 0, 0), 0.6),
                                (r.centerx, r.bottom - 9), "center")

    def _draw_top_bar(self, surface, frame: PlayFrame) -> None:
        p = self.p
        w = surface.get_width()
        rrect(surface, p.panel, (0, 0, w, TOP_BAR), 0)
        pygame.draw.line(surface, p.line, (0, TOP_BAR - 1), (w, TOP_BAR - 1))
        chevron(surface, p.muted, (26, 32), 7, "left")
        title = frame.song.title
        if len(title) > 28:
            title = title[:27] + "…"
        text(surface, self.ui(700, 16), title, p.text, (48, 13))
        sub = frame.coach or f"{frame.mode} · {'Wait mode' if frame.wait_mode else 'Real time'}"
        text(surface, self.ui(400, 12), sub, p.muted, (48, 35))

        tl = pygame.Rect(360, 30, 440, 4)
        rrect(surface, p.line, tl, 2)
        rrect(surface, p.accent, (tl.x, tl.y, int(tl.w * frame.progress), 4), 2)
        pygame.draw.circle(surface, (255, 255, 255), (tl.x + int(tl.w * frame.progress),
                                                      tl.centery), 7)
        text(surface, self.ui(500, 11), _fmt_time(frame.position), p.muted,
             (tl.x - 10, tl.centery), "midright")
        text(surface, self.ui(500, 11), _fmt_time(frame.song.duration), p.muted,
             (tl.right + 10, tl.centery), "midleft")
        if frame.loop:
            loop_txt = f"LOOP BARS {frame.loop[0]}–{frame.loop[1]}  ·  PASS {frame.loop_count + 1}"
            text(surface, self.ui(600, 10), loop_txt, p.accent, (tl.centerx, tl.y - 12),
                 "center")

        hands = {Hand.BOTH: "Both", Hand.RIGHT: "Right", Hand.LEFT: "Left"}[frame.active_hand]
        chips = [(f"{frame.tempo_scale:.0%}", "Tempo"),
                 ("Wait" if frame.wait_mode else "Live", "Mode"), (hands, "Hands"),
                 ({"off": "Off", "count-in": "Count-in", "on": "On"}[frame.metronome], "Click")]
        if frame.mic_level is not None:
            chips.insert(0, ("Mic", "Listening"))
        cx = w - 24
        for val, label in reversed(chips):
            fw = max(self.ui(700, 13).size(val)[0], self.ui(500, 10).size(label)[0]) + 22
            cx -= fw
            rrect(surface, p.panel2, (cx, 12, fw, 40), 8)
            text(surface, self.ui(700, 13), val, p.text, (cx + fw // 2, 25), "center")
            text(surface, self.ui(500, 10), label, p.muted, (cx + fw // 2, 42), "center")
            if label == "Listening" and frame.mic_level is not None:  # live level bar
                lvl = pygame.Rect(cx + 6, 49, fw - 12, 3)
                rrect(surface, p.line, lvl, 1)
                rrect(surface, p.good, (lvl.x, lvl.y, int(lvl.w * frame.mic_level), 3), 1)
            cx -= 8

    def _draw_stats_card(self, surface, frame: PlayFrame, card: pygame.Rect) -> None:
        p = self.p
        rrect(surface, (21, 24, 31), card, 12, alpha=235)
        rrect(surface, (255, 255, 255), card, 12, alpha=16, width=1)
        tracked(surface, self.ui(600, 10), "ACCURACY", p.faint, (card.x + 16, card.y + 14), 1)
        acc = f"{frame.stats.accuracy_pct:.1f}%" if frame.stats.total_notes else "—"
        text(surface, self.ui(700, 28), acc, p.text, (card.x + 16, card.y + 28))
        tracked(surface, self.ui(600, 10), "STREAK", p.faint, (card.x + 148, card.y + 14), 1)
        text(surface, self.ui(700, 28), str(frame.streak), p.good, (card.x + 148, card.y + 28))
        tracked(surface, self.ui(600, 10), "TIMING", p.faint, (card.x + 16, card.y + 78), 1)
        bins = [0] * 11
        for off in frame.timing_offsets_ms[-200:]:
            bins[max(0, min(10, int((off + 220) / 40)))] += 1
        peak = max(bins) or 1
        for i, v in enumerate(bins):
            bh = max(2, int(36 * v / peak)) if v else 2
            c = p.good if 3 <= i <= 7 else p.muted
            rrect(surface, c, (card.x + 16 + i * 17, card.y + 128 - bh, 12, bh), 2)
        text(surface, self.ui(500, 10), "early", p.faint, (card.x + 16, card.y + 132))
        text(surface, self.ui(500, 10), "late", p.faint, (card.right - 16, card.y + 132),
             "topright")

    def _draw_paused(self, surface, frame: PlayFrame, area) -> None:
        p = self.p
        veil = pygame.Surface(area.size, pygame.SRCALPHA)
        veil.fill((8, 9, 12, 170))
        surface.blit(veil, area.topleft)
        card = pygame.Rect(0, 0, 460, 220)
        card.center = area.center
        shadow(surface, card)
        rrect(surface, p.panel, card, 14)
        rrect(surface, p.line, card, 14, width=1)
        text(surface, self.ui(700, 22), "Paused", p.text, (card.x + 28, card.y + 24))
        keys = [("Space", "Resume"), ("W", "Wait mode"), ("- / =", "Tempo"),
                ("1 2 3", "Both / right / left hand"), ("R", "Restart"), ("Esc", "Back to menu")]
        if frame.mode == "Practice":
            keys[4] = ("L  [ ]", "Loop section")
        for i, (k, label) in enumerate(keys):
            x = card.x + 28 + (i % 2) * 210
            y = card.y + 72 + (i // 2) * 44
            kw = self.ui(600, 12).size(k)[0] + 16
            rrect(surface, p.line, (x, y, kw, 24), 6)
            text(surface, self.ui(600, 12), k, p.text, (x + kw // 2, y + 12), "center")
            text(surface, self.ui(500, 13), label, p.muted, (x + kw + 10, y + 4))

    def draw_keyboard(self, surface, layout: KeyLayout, pressed: dict[int, Hand]) -> None:
        w = surface.get_width()
        pygame.draw.rect(surface, FELT, (0, layout.y - 5, w, 5))
        pygame.draw.line(surface, mix(FELT, (0, 0, 0), 0.4), (0, layout.y - 1),
                         (w, layout.y - 1))
        label_font = self.ui(600, 10)
        for pitch in range(layout.lo, layout.hi + 1):
            if is_black(pitch):
                continue
            r = layout.key_rect(pitch)
            if pitch in pressed:
                c = self.hand_color(pressed[pitch])
                surface.blit(vgradient((r.w - 1, r.h), mix(c, (255, 255, 255), 0.35), c),
                             r.topleft)
            else:
                surface.blit(vgradient((r.w - 1, r.h), (232, 234, 238), (250, 250, 252)),
                             r.topleft)
            pygame.draw.line(surface, (180, 184, 192), (r.right - 1, r.y), (r.right - 1, r.bottom))
            if pitch % 12 == 0:
                text(surface, label_font, note_name(pitch), (140, 146, 158),
                                (r.centerx, r.bottom - 12), "center")
        for pitch in range(layout.lo, layout.hi + 1):
            if not is_black(pitch):
                continue
            r = layout.key_rect(pitch)
            if pitch in pressed:
                c = self.hand_color(pressed[pitch])
                surface.blit(vgradient(r.size, mix(c, (0, 0, 0), 0.2), c), r.topleft)
            else:
                surface.blit(vgradient(r.size, (16, 17, 20), (52, 55, 62)), r.topleft)
                pygame.draw.rect(surface, (70, 74, 82), (r.x + 2, r.bottom - 8, r.w - 4, 5),
                                 border_radius=2)
        surface.blit(vgradient((w, 10), (0, 0, 0), (40, 40, 40)), (0, layout.y),
                     special_flags=pygame.BLEND_RGB_MULT)

    # ================================================================== menu
    def _icon(self, surface, kind: str, x: int, y: int, color) -> None:
        if kind == "Play":
            pygame.draw.polygon(surface, color, [(x + 3, y + 2), (x + 3, y + 16), (x + 15, y + 9)])
        elif kind == "Practice":
            pygame.draw.circle(surface, color, (x + 8, y + 9), 8, 2)
            pygame.draw.line(surface, color, (x + 8, y + 9), (x + 8, y + 4), 2)
            pygame.draw.line(surface, color, (x + 8, y + 9), (x + 12, y + 11), 2)
        elif kind == "Coach":
            pygame.draw.circle(surface, color, (x + 8, y + 9), 8, 2)
            pygame.draw.circle(surface, color, (x + 8, y + 9), 4, 2)
            pygame.draw.circle(surface, color, (x + 8, y + 9), 1)
        elif kind == "Free Play":
            for i in range(4):
                rrect(surface, color, (x + i * 5, y + 3, 4, 13), 1, width=0 if i % 2 else 1)
        elif kind == "Settings":
            pygame.draw.circle(surface, color, (x + 8, y + 9), 7, 2)
            pygame.draw.circle(surface, color, (x + 8, y + 9), 2)

    def _logo(self, surface, x: int, y: int) -> None:
        for i, (hh, c) in enumerate(((22, self.p.accent), (15, self.right), (26, self.left))):
            rrect(surface, c, (x + i * 8, y + 26 - hh, 6, hh), 2)
        text(surface, self.ui(800, 21), "KeyFall", self.p.text, (x + 32, y + 2))

    def draw_menu(self, surface: pygame.Surface, frame: MenuFrame) -> None:
        p = self.p
        w, h = surface.get_size()
        self.draw_backdrop(surface)

        # Sidebar: modes + settings + device status
        rrect(surface, p.panel, (0, 0, 236, h), 0)
        pygame.draw.line(surface, p.line, (236, 0), (236, h))
        self._logo(surface, 24, 24)
        y = 96
        for i, mode in enumerate(frame.modes + ["Settings"]):
            active = i == frame.mode
            if active:
                rrect(surface, p.accent, (12, y - 8, 212, 38), 8, alpha=34)
                rrect(surface, p.accent, (12, y - 2, 3, 26), 2)
            col = p.text if active else p.muted
            self._icon(surface, mode, 30, y + 1, col)
            text(surface, self.ui(600 if active else 500, 15), mode, col, (60, y + 1))
            hint = "Tab" if i < len(frame.modes) else "S"
            if i in (0, len(frame.modes)):
                text(surface, self.ui(500, 11), hint, p.faint, (216, y + 3), "topright")
            y += 46

        devices = [("MIDI keyboard", frame.midi_status, frame.midi_connected),
                   ("Keyboard output", frame.output_status, frame.output_connected),
                   ("Sound", frame.audio_status.removeprefix("Sound: "), frame.sound_ok)]
        top = h - 34 - len(devices) * 62
        tracked(surface, self.ui(600, 11), "DEVICES", p.faint, (24, top - 24), 1)
        for i, (title, sub, ok) in enumerate(devices):
            cy = top + i * 62
            rrect(surface, p.panel2, (12, cy, 212, 52), 10)
            pygame.draw.circle(surface, p.good if ok else p.faint, (32, cy + 26), 5)
            text(surface, self.ui(600, 14), title, p.text if ok else p.muted, (48, cy + 9))
            sub_font = self.ui(400, 12)
            while len(sub) > 2 and sub_font.size(sub)[0] > 168:
                sub = sub[:-2] + "…"
            text(surface, sub_font, sub, p.muted, (48, cy + 28))

        # Header
        x0 = 268
        text(surface, self.ui(700, 28), "Library", p.text, (x0, 28))
        count = f"{len(frame.songs)} song{'s' if len(frame.songs) != 1 else ''}"
        if frame.songs_dir:
            home = str(Path.home())
            shown = frame.songs_dir.replace(home, "~", 1)
            count += f"  ·  {shown}"
        text(surface, self.ui(400, 14), count, p.muted, (x0, 66))
        cx = w - 32
        for chip, key in ((f"Hands: {frame.hand_split}", "H"), ("Open songs folder", "O")):
            cw = self.ui(500, 13).size(chip)[0] + 52
            cx -= cw
            rrect(surface, p.line, (cx, 34, cw, 32), 16, width=1)
            text(surface, self.ui(500, 13), chip, p.muted, (cx + 16, 50), "midleft")
            k = pygame.Rect(cx + cw - 30, 40, 20, 20)
            rrect(surface, p.line, k, 5)
            text(surface, self.ui(600, 11), key, p.text, k.center, "center")
            cx -= 10

        if not frame.songs:
            card = pygame.Rect(x0, 110, w - x0 - 32, 150)
            rrect(surface, p.panel, card, 14)
            rrect(surface, p.line, card, 14, width=1)
            text(surface, self.ui(700, 20), "No songs yet", p.text, (card.x + 28, card.y + 30))
            text(surface, self.ui(400, 14),
                 "Press O to open your songs folder, then drop in MIDI, MusicXML or Suno stems.",
                 p.muted, (card.x + 28, card.y + 66))
            text(surface, self.ui(400, 14), "Press Tab to switch to Free Play.", p.muted,
                 (card.x + 28, card.y + 92))
        else:
            self._draw_hero(surface, frame, pygame.Rect(x0, 96, w - x0 - 32, 128))
            self._draw_table(surface, frame, x0, 252, h - 60)

        if frame.error:
            text(surface, self.ui(500, 13), frame.error, p.miss, (x0, h - 62))
        hx = x0
        for key, label in (("↑↓", "Select"), ("Enter", "Start"), ("Tab", "Mode"),
                           ("H", "Hands"), ("S", "Settings")):
            if key == "↑↓":
                kw = 30
                rrect(surface, p.line, (hx, h - 34, kw, 20), 5)
                chevron(surface, p.text, (hx + 9, h - 24), 3, "up")
                chevron(surface, p.text, (hx + 21, h - 24), 3, "down")
            else:
                kw = self.ui(600, 11).size(key)[0] + 14
                rrect(surface, p.line, (hx, h - 34, kw, 20), 5)
                text(surface, self.ui(600, 11), key, p.text, (hx + kw // 2, h - 24), "center")
            r = text(surface, self.ui(500, 12), label, p.muted, (hx + kw + 8, h - 32))
            hx = r.right + 20

    def _draw_hero(self, surface, frame: MenuFrame, card: pygame.Rect) -> None:
        p = self.p
        song = frame.songs[frame.selected]
        shadow(surface, card)
        gradient_rect(surface, card, (32, 38, 70), (22, 25, 36), 14)
        rrect(surface, (255, 255, 255), card, 14, alpha=18, width=1)
        thumb = pygame.Rect(card.x + 20, card.y + 18, 150, 92)
        self._thumbnail(surface, thumb, song.title)
        mode = frame.modes[frame.mode]
        tracked(surface, self.ui(600, 11), "SELECTED", p.accent, (card.x + 192, card.y + 22), 1)
        text(surface, self.ui(700, 22), song.title, p.text, (card.x + 192, card.y + 40))
        d = frame.details
        bits = [song.kind]
        if d:
            bits += [_fmt_time(d.duration), f"{d.note_count} notes"]
            if d.difficulty_label:
                bits.append(f"{d.difficulty_label} (level {d.difficulty_level})")
        text(surface, self.ui(400, 14), "  ·  ".join(bits), p.muted, (card.x + 192, card.y + 72))
        best = song.best_accuracy
        bar = pygame.Rect(card.x + 192, card.y + 100, 360, 6)
        rrect(surface, (255, 255, 255), bar, 3, alpha=25)
        if best is not None:
            rrect(surface, p.accent, (bar.x, bar.y, int(bar.w * best / 100), 6), 3)
        label = f"Best {best:.0f}%" if best is not None else "Not played yet"
        text(surface, self.ui(500, 12), label, p.muted, (bar.right + 12, bar.y - 5))
        btn = pygame.Rect(card.right - 160, card.centery - 22, 136, 44)
        rrect(surface, p.accent, btn, 10)
        pygame.draw.polygon(surface, (255, 255, 255), [(btn.x + 24, btn.y + 14),
                                                       (btn.x + 24, btn.y + 30),
                                                       (btn.x + 36, btn.y + 22)])
        text(surface, self.ui(600, 15), mode, (255, 255, 255), (btn.x + 46, btn.centery),
             "midleft")

    def _thumbnail(self, surface, rect: pygame.Rect, seed_text: str) -> None:
        rrect(surface, (12, 14, 20), rect, 10)
        seed = sum(ord(c) * (i + 1) for i, c in enumerate(seed_text))
        for k in range(14):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            lx = rect.x + 10 + seed % 120
            ly = rect.y + (seed >> 8) % 80 - 10
            lh = 10 + (seed >> 4) % 18
            c = self.right if lx > rect.centerx - 10 else self.left
            r = pygame.Rect(lx, max(rect.y + 4, ly), 9, lh).clip(rect.inflate(-8, -8))
            rrect(surface, c, r, 3)

    def _draw_table(self, surface, frame: MenuFrame, x0: int, ty: int, bottom: int) -> None:
        p = self.p
        w = surface.get_width()
        cols = [(x0 + 16, "TITLE"), (x0 + 520, "FORMAT"), (x0 + 680, "BEST"), (x0 + 800, "GRADE")]
        for cx, label in cols:
            tracked(surface, self.ui(600, 11), label, p.faint, (cx, ty), 1)
        pygame.draw.line(surface, p.line, (x0, ty + 24), (w - 32, ty + 24))
        row_h = 52
        visible = max(1, (bottom - ty - 34) // row_h)
        start = max(0, min(frame.selected - visible // 2, len(frame.songs) - visible))
        ry = ty + 34
        for i in range(start, min(len(frame.songs), start + visible)):
            song = frame.songs[i]
            r = pygame.Rect(x0, ry - 6, w - x0 - 32, row_h - 4)
            if i == frame.selected:
                rrect(surface, p.accent, r, 10, alpha=26)
                rrect(surface, p.accent, r, 10, alpha=90, width=1)
            tile = pygame.Rect(x0 + 16, ry, 36, 36)
            hue = (p.accent, self.left, p.good, self.right)[i % 4]
            art = vgradient(tile.size, mix(hue, (255, 255, 255), 0.15), mix(hue, (0, 0, 0), 0.5))
            art = art.copy()
            for k, bh in enumerate((6, 14, 10)):
                pygame.draw.rect(art, mix(hue, (255, 255, 255), 0.55), (8 + k * 8, 26 - bh, 5, bh),
                                 border_radius=2)
            blit_rounded(surface, art, tile.topleft, 8)
            text(surface, self.ui(600, 15), song.title, p.text, (x0 + 64, ry + 9))
            fw = self.ui(500, 12).size(song.kind)[0] + 18
            rrect(surface, p.line, (x0 + 520, ry + 7, fw, 22), 11)
            text(surface, self.ui(500, 12), song.kind, p.muted, (x0 + 520 + fw // 2, ry + 18),
                 "center")
            if song.best_accuracy is None:
                text(surface, self.ui(600, 14), "—", p.muted, (x0 + 680, ry + 9))
            else:
                col = p.good if song.best_accuracy >= 85 else p.muted
                text(surface, self.ui(600, 14), f"{song.best_accuracy:.0f}%", col,
                     (x0 + 680, ry + 9))
                grade = grade_letter(song.best_accuracy, 1)
                text(surface, self.ui(700, 14), grade, p.text, (x0 + 800, ry + 9))
            ry += row_h
