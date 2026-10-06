"""Render mockups of the proposed "Song packs" feature with the real Studio skin.

Three screens:
  1. Library with a new "Get songs" chip
  2. The Song packs browser (one pack installed, one downloading, one selected)
  3. The Library after installing packs: pack filter, PACK and LEVEL columns

Pack names, piece counts and sizes are illustrative.

Usage:
    PYTHONPATH=src python docs/mockups/song_packs_mockup.py OUT_DIR
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from keyfall.renderer.draw import (  # noqa: E402
    blit_rounded,
    chevron,
    gradient_rect,
    mix,
    rrect,
    shadow,
    text,
    tracked,
    vgradient,
)
from keyfall.renderer.skins.frames import (  # noqa: E402
    MenuFrame,
    MenuSong,
    SongDetails,
    grade_letter,
)
from keyfall.renderer.skins.studio import StudioSkin  # noqa: E402

W, H = 1280, 720
OUT = sys.argv[1] if len(sys.argv) > 1 else "."
X0 = 268

STARTER = [
    "Bach - Minuet in A minor", "Bach - Minuet in B-flat major", "Beethoven - Fur Elise",
    "Burgmuller - Arabesque", "Chopin - Prelude in A major", "Chopin - Prelude in E minor",
    "Debussy - Clair de Lune", "Handel - Sonatina in B-flat major", "Joplin - The Entertainer",
    "Tchaikovsky - March of the Wooden Soldiers",
]


def base_frame(songs: list[MenuSong], selected: int = 0) -> MenuFrame:
    return MenuFrame(
        songs=songs, selected=selected, modes=["Play", "Practice", "Coach", "Free Play"], mode=0,
        hand_split="Auto", audio_status="Sound: YDP-GrandPiano", midi_status="Roland FP-30X",
        midi_connected=True, sound_ok=True, songs_dir=os.path.expanduser("~/KeyFall/Songs"),
        details=SongDetails(duration=174, note_count=1102, difficulty_level=9,
                            difficulty_label="Intermediate"),
    )


class MockSkin(StudioSkin):
    # ------------------------------------------------------------ shared bits
    def key_cap(self, surface, key: str, x: int, y: int) -> int:
        kw = self.ui(600, 11).size(key)[0] + 14
        rrect(surface, self.p.line, (x, y, kw, 20), 5)
        text(surface, self.ui(600, 11), key, self.p.text, (x + kw // 2, y + 10), "center")
        return kw

    def hints(self, surface, items) -> None:
        hx = X0
        for key, label in items:
            if key == "↑↓":
                kw = 30
                rrect(surface, self.p.line, (hx, H - 34, kw, 20), 5)
                chevron(surface, self.p.text, (hx + 9, H - 24), 3, "up")
                chevron(surface, self.p.text, (hx + 21, H - 24), 3, "down")
            else:
                kw = self.key_cap(surface, key, hx, H - 34)
            r = text(surface, self.ui(500, 12), label, self.p.muted, (hx + kw + 8, H - 32))
            hx = r.right + 20

    def chip(self, surface, label: str, key: str, right: int, y: int, accent=False) -> int:
        p = self.p
        cw = self.ui(500, 13).size(label)[0] + 52
        cx = right - cw
        if accent:
            rrect(surface, p.accent, (cx, y, cw, 32), 16, alpha=40)
            rrect(surface, p.accent, (cx, y, cw, 32), 16, width=1)
        else:
            rrect(surface, p.line, (cx, y, cw, 32), 16, width=1)
        text(surface, self.ui(600 if accent else 500, 13), label,
             p.text if accent else p.muted, (cx + 16, y + 16), "midleft")
        k = pygame.Rect(cx + cw - 30, y + 6, 20, 20)
        rrect(surface, p.accent if accent else p.line, k, 5)
        text(surface, self.ui(600, 11), key, (255, 255, 255) if accent else p.text, k.center,
             "center")
        return cx

    def tile(self, surface, rect: pygame.Rect, hue, radius=8) -> None:
        art = vgradient(rect.size, mix(hue, (255, 255, 255), 0.15), mix(hue, (0, 0, 0), 0.5)).copy()
        s = rect.w / 36
        for k, bh in enumerate((6, 14, 10)):
            pygame.draw.rect(art, mix(hue, (255, 255, 255), 0.55),
                             (int((8 + k * 8) * s), int((26 - bh) * s), int(5 * s), int(bh * s)),
                             border_radius=2)
        blit_rounded(surface, art, rect.topleft, radius)

    def pill(self, surface, label: str, x: int, y: int, color=None, fill_alpha=None) -> int:
        f = self.ui(500, 12)
        pw = f.size(label)[0] + 18
        if color is None:
            rrect(surface, self.p.line, (x, y, pw, 22), 11)
            text(surface, f, label, self.p.muted, (x + pw // 2, y + 11), "center")
        else:
            rrect(surface, color, (x, y, pw, 22), 11, alpha=fill_alpha or 40)
            text(surface, f, label, color, (x + pw // 2, y + 11), "center")
        return pw

    def clear_main(self, surface) -> None:
        """Repaint the area right of the sidebar so a new screen can be drawn there."""
        full = pygame.Surface((W, H))
        self.draw_backdrop(full)
        surface.blit(full, (X0 - 31, 0), pygame.Rect(X0 - 31, 0, W, H))

    # ------------------------------------------------------------ 1. library chip
    def draw_library_with_chip(self, surface) -> None:
        songs = [MenuSong(t, "MIDI") for t in STARTER]
        songs[2].best_accuracy = 91
        self.draw_menu(surface, base_frame(songs, selected=2))
        # The real menu draws "Open songs folder" and "Hands" chips; add "Get songs" to their left.
        cx = W - 32
        for chip in ("Hands: Auto", "Open songs folder"):
            cx -= self.ui(500, 13).size(chip)[0] + 52 + 10
        left = self.chip(surface, "Get more songs", "G", cx, 34, accent=True)
        tip = pygame.Rect(left - 70, 74, 300, 52)
        shadow(surface, tip, 10, 120)
        rrect(surface, self.p.panel2, tip, 10)
        rrect(surface, self.p.accent, tip, 10, alpha=120, width=1)
        text(surface, self.ui(600, 13), "New: free song packs", self.p.text,
             (tip.x + 14, tip.y + 9))
        text(surface, self.ui(400, 12), "Hundreds of public-domain pieces, graded",
             self.p.muted, (tip.x + 14, tip.y + 28))

    # ------------------------------------------------------------ 2. pack browser
    PACKS = [
        # name, source, count, size, licenses, levels, state, hue
        ("Starter songs", "Built in · Mutopia Project", 10, "0.3 MB", "Public domain",
         "Levels 4-15", "installed", "accent"),
        ("Piano: First Pieces", "Mutopia Project", 48, "1.1 MB", "PD · CC0 · CC BY",
         "Levels 1-5", "selected", "good"),
        ("Piano: Intermediate", "Mutopia Project", 64, "2.2 MB", "PD · CC BY · CC BY-SA",
         "Levels 6-11", "downloading", "right"),
        ("Piano: Advanced", "Mutopia Project", 41, "2.9 MB", "PD · CC BY-SA",
         "Levels 12-18", "available", "left"),
        ("Lieder Accompaniments", "OpenScore", 120, "6.4 MB", "CC0",
         "Levels 5-14", "available", "gold"),
    ]

    def draw_pack_browser(self, surface) -> None:
        p = self.p
        songs = [MenuSong(t, "MIDI") for t in STARTER]
        self.draw_menu(surface, base_frame(songs))
        self.clear_main(surface)

        chevron(surface, p.muted, (X0 + 6, 46), 6, "left")
        text(surface, self.ui(700, 28), "Get more songs", p.text, (X0 + 22, 28))
        text(surface, self.ui(400, 14),
             "Free sheet music from open collections. Songs go into ~/KeyFall/Songs/<pack>.",
             p.muted, (X0, 66))
        self.chip(surface, "Remove pack", "Del", W - 32, 34)

        # Pack list
        lw = 520
        y = 104
        for name, source, count, size, lic, levels, state, hue_name in self.PACKS:
            hue = getattr(p, hue_name)
            sel = state == "selected"
            card = pygame.Rect(X0, y, lw, 92)
            if sel:
                shadow(surface, card, 12, 80)
                gradient_rect(surface, card, (32, 38, 70), (22, 25, 36), 12)
                rrect(surface, p.accent, card, 12, alpha=150, width=1)
            else:
                rrect(surface, p.panel, card, 12)
                rrect(surface, p.line, card, 12, width=1)
            self.tile(surface, pygame.Rect(card.x + 16, card.y + 16, 44, 44), hue, 10)
            text(surface, self.ui(600, 16), name, p.text, (card.x + 76, card.y + 14))
            text(surface, self.ui(400, 12), f"{source}  ·  {count} pieces  ·  {size}",
                 p.muted, (card.x + 76, card.y + 38))
            px = card.x + 76
            px += self.pill(surface, levels, px, card.y + 60) + 6
            self.pill(surface, lic, px, card.y + 60)

            # Right-hand status
            bx = card.right - 16
            if state == "installed":
                f = self.ui(600, 13)
                r = text(surface, f, "Installed", p.good, (bx, card.y + 22), "topright")
                pygame.draw.lines(surface, p.good, False,
                                  [(r.x - 18, r.centery), (r.x - 13, r.centery + 5),
                                   (r.x - 5, r.centery - 5)], 2)
            elif state == "downloading":
                bar = pygame.Rect(bx - 120, card.y + 24, 120, 8)
                rrect(surface, (255, 255, 255), bar, 4, alpha=25)
                rrect(surface, p.accent, (bar.x, bar.y, int(bar.w * 0.42), 8), 4)
                text(surface, self.ui(500, 12), "27 of 64 · 42%", p.muted,
                     (bx, card.y + 40), "topright")
            else:
                btn = pygame.Rect(bx - 96, card.y + 16, 96, 34)
                if sel:
                    rrect(surface, p.accent, btn, 9)
                    text(surface, self.ui(600, 14), "Install", (255, 255, 255), btn.center,
                         "center")
                else:
                    rrect(surface, p.line, btn, 9, width=1)
                    text(surface, self.ui(600, 14), "Install", p.text, btn.center, "center")
            y += 102

        # Detail panel for the selected pack
        dx = X0 + lw + 24
        panel = pygame.Rect(dx, 104, W - dx - 32, 500)
        rrect(surface, p.panel, panel, 14)
        rrect(surface, p.line, panel, 14, width=1)
        ix = panel.x + 24
        tracked(surface, self.ui(600, 11), "MUTOPIA PROJECT", p.accent, (ix, panel.y + 22), 1)
        text(surface, self.ui(700, 22), "Piano: First Pieces", p.text, (ix, panel.y + 40))
        for i, line in enumerate((
                "Short, graded pieces for your first year: minuets,",
                "sonatinas, Album for the Young and Burgmüller études,",
                "engraved by Mutopia volunteers with both hands split.")):
            text(surface, self.ui(400, 13), line, p.muted, (ix, panel.y + 74 + i * 19))

        # Difficulty histogram
        tracked(surface, self.ui(600, 11), "DIFFICULTY", p.faint, (ix, panel.y + 146), 1)
        hist = [9, 14, 12, 8, 5]
        bw, gap, base = 44, 8, panel.y + 222
        for i, n in enumerate(hist):
            hgt = n * 4
            rrect(surface, mix(p.good, p.accent, i / 4), (ix + i * (bw + gap), base - hgt, bw, hgt),
                  4)
            text(surface, self.ui(500, 11), f"L{i + 1}", p.faint,
                 (ix + i * (bw + gap) + bw // 2, base + 6), "midtop")

        # License breakdown bar
        lx = ix + 5 * (bw + gap) + 24
        tracked(surface, self.ui(600, 11), "LICENSES", p.faint, (lx, panel.y + 146), 1)
        bar = pygame.Rect(lx, panel.y + 172, panel.right - 24 - lx, 10)
        parts = [(0.62, p.good, "Public domain 30"), (0.25, p.accent, "CC0 12"),
                 (0.13, p.gold, "CC BY 6")]
        bx = bar.x
        for frac, col, _ in parts:
            seg = int(bar.w * frac)
            pygame.draw.rect(surface, col, (bx, bar.y, seg - 2, bar.h), border_radius=3)
            bx += seg
        for i, (_, col, label) in enumerate(parts):
            pygame.draw.circle(surface, col, (lx + 5, panel.y + 198 + i * 18 + 7), 4)
            text(surface, self.ui(500, 12), label, p.muted, (lx + 16, panel.y + 198 + i * 18))

        # Sample pieces
        tracked(surface, self.ui(600, 11), "INCLUDES", p.faint, (ix, panel.y + 262), 1)
        pieces = [("Bach", "Minuet in G major (BWV Anh. 114)", 2),
                  ("Schumann", "Melody (Album for the Young, Op. 68 No. 1)", 1),
                  ("Clementi", "Sonatina in C major (Op. 36 No. 1)", 3),
                  ("Burgmüller", "Candour (Op. 100 No. 1)", 2),
                  ("Gurlitt", "The Little Wanderer (Op. 205 No. 3)", 1)]
        for i, (who, what, lvl) in enumerate(pieces[:4]):
            ry = panel.y + 284 + i * 26
            r = text(surface, self.ui(600, 13), who, p.text, (ix, ry))
            text(surface, self.ui(400, 13), what, p.muted, (r.right + 8, ry))
            text(surface, self.ui(600, 12), f"L{lvl}", p.good, (panel.right - 24, ry),
                 "topright")
        text(surface, self.ui(500, 12), "+ 44 more", p.faint, (ix, panel.y + 284 + 4 * 26))

        # Footer of the panel
        pygame.draw.line(surface, p.line, (panel.x, panel.bottom - 76),
                         (panel.right, panel.bottom - 76))
        text(surface, self.ui(400, 12), "Credits saved to ATTRIBUTION.md", p.faint,
             (ix, panel.bottom - 58))
        text(surface, self.ui(400, 12), "Source: mutopiaproject.org", p.faint,
             (ix, panel.bottom - 40))
        btn = pygame.Rect(panel.right - 24 - 168, panel.bottom - 58, 168, 40)
        rrect(surface, p.accent, btn, 10)
        text(surface, self.ui(600, 14), "Install 48 songs", (255, 255, 255), btn.center, "center")

        self.hints(surface, [("↑↓", "Select pack"), ("Enter", "Install"), ("Del", "Remove"),
                             ("Esc", "Back to library")])

    # ------------------------------------------------------------ 3. library after
    def draw_library_after(self, surface) -> None:
        p = self.p
        rows = [
            ("Bach - Minuet in G major", "First Pieces", 2, 96),
            ("Burgmuller - Candour", "First Pieces", 2, 88),
            ("Clementi - Sonatina in C major", "First Pieces", 3, None),
            ("Gurlitt - The Little Wanderer", "First Pieces", 1, 100),
            ("Schumann - Melody", "First Pieces", 1, None),
            ("Schumann - Soldiers' March", "First Pieces", 2, None),
            ("Beethoven - Fur Elise", "Starter", 9, 91),
        ]
        songs = [MenuSong(t, "MIDI", acc) for t, _, _, acc in rows]
        frame = base_frame(songs, selected=2)
        frame.details = SongDetails(duration=96, note_count=412, difficulty_level=3,
                                    difficulty_label="Beginner")
        self._rows = rows
        self.draw_menu(surface, frame)
        # Fix the header count to reflect the whole library, not the filtered view.
        full = pygame.Surface((W, H))
        self.draw_backdrop(full)
        surface.blit(full, (X0, 62), pygame.Rect(X0, 62, 400, 24))
        text(surface, self.ui(400, 14), "58 songs  ·  ~/KeyFall/Songs", p.muted, (X0, 66))
        cx = W - 32
        for chip in ("Hands: Auto", "Open songs folder"):
            cx -= self.ui(500, 13).size(chip)[0] + 52 + 10
        self.chip(surface, "Get more songs", "G", cx, 34)

    def _draw_table(self, surface, frame: MenuFrame, x0: int, ty: int, bottom: int) -> None:
        rows = getattr(self, "_rows", None)
        if rows is None:
            return super()._draw_table(surface, frame, x0, ty, bottom)
        p = self.p
        w = surface.get_width()
        # Pack filter chips
        fx = x0
        for i, (label, n) in enumerate((("All", 58), ("Starter", 10), ("First Pieces", 48),
                                        ("Intermediate", "27/64"))):
            s = f"{label}  {n}"
            cw = self.ui(500, 13).size(s)[0] + 26
            if i == 2:
                rrect(surface, p.accent, (fx, ty - 6, cw, 28), 14, alpha=50)
                rrect(surface, p.accent, (fx, ty - 6, cw, 28), 14, width=1)
                text(surface, self.ui(600, 13), s, p.text, (fx + 13, ty + 8), "midleft")
            else:
                rrect(surface, p.line, (fx, ty - 6, cw, 28), 14, width=1)
                text(surface, self.ui(500, 13), s, p.muted, (fx + 13, ty + 8), "midleft")
            fx += cw + 8
        text(surface, self.ui(500, 12), "Sort: Level", p.muted, (w - 32 - 54, ty + 8), "midright")
        self.key_cap(surface, "L", w - 32 - 44, ty - 2)
        ty += 40
        cols = [(x0 + 16, "TITLE"), (x0 + 470, "PACK"), (x0 + 640, "LEVEL"), (x0 + 760, "BEST"),
                (x0 + 860, "GRADE")]
        for cx, label in cols:
            tracked(surface, self.ui(600, 11), label, p.faint, (cx, ty), 1)
        pygame.draw.line(surface, p.line, (x0, ty + 24), (w - 32, ty + 24))
        row_h = 46
        ry = ty + 32
        order = sorted(range(len(rows)), key=lambda i: rows[i][2])
        for i in order[:6]:
            title, pack, lvl, acc = rows[i]
            r = pygame.Rect(x0, ry - 5, w - x0 - 32, row_h - 4)
            if i == frame.selected:
                rrect(surface, p.accent, r, 10, alpha=26)
                rrect(surface, p.accent, r, 10, alpha=90, width=1)
            self.tile(surface, pygame.Rect(x0 + 16, ry, 32, 32),
                      p.good if pack == "First Pieces" else p.accent)
            text(surface, self.ui(600, 15), title, p.text, (x0 + 60, ry + 7))
            self.pill(surface, pack, x0 + 470, ry + 5)
            # Level meter on KeyFall's 1-18 difficulty scale
            meter = pygame.Rect(x0 + 640, ry + 13, 54, 6)
            rrect(surface, p.line, meter, 3)
            rrect(surface, p.good, (meter.x, meter.y, max(6, meter.w * lvl // 18), 6), 3)
            text(surface, self.ui(600, 12), str(lvl), p.muted, (x0 + 704, ry + 8))
            if acc is None:
                text(surface, self.ui(600, 14), "—", p.muted, (x0 + 760, ry + 8))
            else:
                col = p.good if acc >= 85 else p.muted
                text(surface, self.ui(600, 14), f"{acc}%", col, (x0 + 760, ry + 8))
                grade = grade_letter(acc, 1)
                text(surface, self.ui(700, 14), grade, p.text, (x0 + 860, ry + 8))
            ry += row_h


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (("1_library_get_songs", "draw_library_with_chip"),
                     ("2_pack_browser", "draw_pack_browser"),
                     ("3_library_after_install", "draw_library_after")):
        skin = MockSkin()
        surf = pygame.Surface((W, H))
        getattr(skin, fn)(surf)
        path = os.path.join(OUT, f"{name}.png")
        pygame.image.save(surf, path)
        print(path)


if __name__ == "__main__":
    main()
