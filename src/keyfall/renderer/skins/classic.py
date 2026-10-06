"""Classic skin: the original KeyFall look (flat colors, monospace text)."""

from __future__ import annotations

import pygame

from keyfall.config import MIDI_NOTE_MAX, MIDI_NOTE_MIN
from keyfall.renderer.draw import text
from keyfall.renderer.skins.base import Skin
from keyfall.renderer.skins.frames import MenuFrame, PlayFrame
from keyfall.renderer.skins.keys import KeyLayout, is_black, label_for
from keyfall.renderer.theme import CLASSIC

KEYBOARD_HEIGHT = 120
LOOK_AHEAD = 3.0


class ClassicSkin(Skin):
    theme = CLASSIC

    def draw_play(self, surface: pygame.Surface, frame: PlayFrame) -> None:
        p = self.p
        w, h = surface.get_size()
        surface.fill(p.bg)
        notation_h = 180 if frame.show_notation else 0
        below = frame.sheet_below and notation_h > 0
        kb_y = h - KEYBOARD_HEIGHT - (notation_h if below else 0)
        layout = KeyLayout(MIDI_NOTE_MIN, MIDI_NOTE_MAX, 0, w, kb_y, KEYBOARD_HEIGHT)
        top = 44 + (0 if below else notation_h)
        if frame.show_notation:
            y = kb_y + KEYBOARD_HEIGHT if below else 44
            self.draw_notation_panel(surface, frame, pygame.Rect(0, y, w, notation_h))

        self.draw_backing(surface, frame, layout, pygame.Rect(0, 0, w, kb_y), LOOK_AHEAD,
                          (110, 110, 130), fill_alpha=60, edge_alpha=0,
                          clip=pygame.Rect(0, top, w, kb_y - top))
        pps = kb_y / LOOK_AHEAD
        label_font = self.ui(700, 11)
        for n in self.note_index(frame.song).window(frame.position - 0.5,
                                                    frame.position + LOOK_AHEAD):
            if not layout.contains(n.pitch):
                continue
            x, lw = layout.lane(n.pitch)
            y_bottom = kb_y - (n.start_time - frame.position) * pps
            bar_h = max(n.duration * pps, 6)
            r = pygame.Rect(int(x), int(y_bottom - bar_h), int(lw), int(bar_h)).clip(
                pygame.Rect(0, top, w, kb_y - top))
            if r.h <= 0:
                continue
            pygame.draw.rect(surface, self.hand_color(n.hand), r, border_radius=3)
            lbl = label_for(n.pitch, self.label_mode)
            if lbl and r.h > 16 and not is_black(n.pitch):
                text(surface, label_font, lbl, p.bg, (r.centerx, r.bottom - 8), "center")
        self.draw_keyboard(surface, layout, self.pressed_hands(frame, layout))
        if frame.count_in:
            text(surface, self.ui(700, 96), str(frame.count_in), p.text,
                 (w // 2, (top + kb_y) // 2), "center")
        if frame.hints and (frame.paused or frame.mode == "Practice"):
            text(surface, self.ui(500, 16), frame.hints, p.faint, (10, kb_y - 26))

        hud = self.ui(500, 20)
        score = frame.stats.perfect * 3 + frame.stats.good * 2 + frame.stats.ok
        lines = (f"Score: {score}", f"Streak: {frame.streak}",
                 f"Accuracy: {frame.stats.accuracy_pct:.0f}%")
        for i, line in enumerate(lines):
            text(surface, hud, line, p.text, (10, 10 + i * 28))

        parts = [f"Tempo: {frame.tempo_scale:.0%}", "WAIT" if frame.wait_mode else "PLAY",
                 f"Hand: {frame.active_hand.name}"]
        if frame.loop:
            parts.append(f"Loop: bars {frame.loop[0]}-{frame.loop[1]} (#{frame.loop_count})")
        if frame.paused:
            parts.append("PAUSED")
        text(surface, self.ui(500, 18), " | ".join(parts), p.text, (w - 10, 12), "topright")

    def draw_menu(self, surface: pygame.Surface, frame: MenuFrame) -> None:
        p = self.p
        w, h = surface.get_size()
        surface.fill(p.bg)
        f = self.ui(500, 20)
        text(surface, self.ui(700, 36), "KeyFall", p.accent, (w // 2, 30), "midtop")
        text(surface, f, f"Mode: < {frame.modes[frame.mode]} >  (Tab to cycle)", p.right, (40, 90))
        text(surface, f, f"Hands: < {frame.hand_split} >  (H to cycle)", p.left, (520, 90))
        text(surface, f, frame.audio_status, p.good if frame.sound_ok else p.miss, (40, 120))

        if frame.songs:
            text(surface, f, "Songs:", p.text, (40, 160))
            y = 195
            start = max(0, frame.selected - 14)
            for i, song in enumerate(frame.songs[start:], start):
                sel = i == frame.selected
                text(surface, f, f"{'> ' if sel else '  '}{song.title}",
                     p.accent if sel else p.text, (40, y))
                y += 28
                if y > h - 100:
                    break
        else:
            text(surface, f, "No songs found. Press O to open the songs folder.", p.miss, (40, 180))
        if frame.error:
            text(surface, f, frame.error, p.miss, (40, h - 70))
        legend = "Up/Down: select | Enter: launch | Tab: mode | H: hands | O: folder | S: settings"
        text(surface, f, legend, p.muted, (40, h - 40))
