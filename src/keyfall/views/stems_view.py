"""Stems screen: assign a role to each stem of a multi-stem song, then play it."""

from __future__ import annotations

import pygame

from keyfall.models import Hand, Song
from keyfall.renderer.skins.frames import SettingsRow, StemsFrame
from keyfall.renderer.skins.keys import note_name
from keyfall.stems import QUANTIZE_OPTIONS, ROLE_ORDER, StemRole, StemSet
from keyfall.views.base import ViewAction, ViewContext

_SWATCH = {StemRole.RIGHT: "right", StemRole.LEFT: "left", StemRole.BOTH: "both",
           StemRole.BACKING: "backing", StemRole.OFF: "off"}
_QUANTIZE_NAMES = {0: "Off", 8: "1/8 notes", 16: "1/16 notes"}


class StemsView:
    name = "stems"
    display_name = "Stems"

    def __init__(self) -> None:
        self._context: ViewContext | None = None
        self._set: StemSet | None = None
        self._song: Song | None = None
        self._selected = 0
        self._message = ""

    def on_enter(self, context: ViewContext) -> None:
        self._context = context
        self._message = ""
        try:
            self._set = StemSet.load(context.stem_folder)
        except Exception as exc:
            self._set = None
            self._message = f"Could not read stems: {exc}"
        self._recombine()

    def on_exit(self) -> None:
        pass

    # rows: one per stem, then Clean up, Snap to grid, Start
    @property
    def _row_count(self) -> int:
        return (len(self._set.stems) if self._set else 0) + 3

    def _recombine(self) -> None:
        self._song = self._set.combine() if self._set else None

    def handle_event(self, event: pygame.event.Event) -> ViewAction | None:
        if event.type != pygame.KEYDOWN:
            return None
        if event.key == pygame.K_ESCAPE:
            return ViewAction(kind="pop")
        if self._set is None:
            return None
        if event.key == pygame.K_UP:
            self._selected = (self._selected - 1) % self._row_count
        elif event.key in (pygame.K_DOWN, pygame.K_TAB):
            self._selected = (self._selected + 1) % self._row_count
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.change(self._selected, -1 if event.key == pygame.K_LEFT else 1)
        elif event.key == pygame.K_RETURN:
            if self._selected == self._row_count - 1:
                return self.start()
            self.change(self._selected, 1)
        return None

    def change(self, row: int, step: int) -> None:
        stems = self._set.stems
        if row < len(stems):
            stem = stems[row]
            i = ROLE_ORDER.index(stem.role)
            stem.role = ROLE_ORDER[(i + step) % len(ROLE_ORDER)]
        elif row == len(stems):
            self._set.clean = not self._set.clean
        elif row == len(stems) + 1:
            i = QUANTIZE_OPTIONS.index(self._set.quantize_division)
            self._set.quantize_division = QUANTIZE_OPTIONS[(i + step) % len(QUANTIZE_OPTIONS)]
        else:
            return
        self._message = ""
        self._recombine()

    def start(self) -> ViewAction | None:
        song = self._song
        if song is None or not song.notes:
            self._message = "Give at least one stem a hand (right, left or both) to play."
            return None
        try:
            self._set.save()
        except OSError:
            pass  # read-only folder: still playable, just not remembered
        target = (self._context.next_view if self._context else "") or "waterfall"
        # switch (not push) so Esc in the song goes back to the menu
        return ViewAction(kind="switch", target=target, context_patch={"song": song})

    def update(self, dt: float) -> ViewAction | None:
        return None

    def _rows(self) -> list[SettingsRow]:
        rows = []
        for stem in self._set.stems:
            rng = stem.pitch_range
            detail = f"{stem.instrument} · {len(stem.notes)} notes"
            if rng:
                detail += f" · {note_name(rng[0])}–{note_name(rng[1])}"
            rows.append(SettingsRow(stem.label(self._set.folder.name), stem.role.value, detail,
                                    swatch=_SWATCH[stem.role]))
        rows.append(SettingsRow("Clean up transcription", "On" if self._set.clean else "Off",
                                "Remove ghost notes and merge double hits"))
        rows.append(SettingsRow("Snap to grid", _QUANTIZE_NAMES[self._set.quantize_division],
                                f"Quantize at {self._bpm():.0f} BPM (only if the tempo is right)"))
        rows.append(SettingsRow("Start", "", "", adjustable=False))
        return rows

    def _bpm(self) -> float:
        if self._song and self._song.tempo_changes:
            return self._song.tempo_changes[0].bpm
        return 120.0

    def _summary(self) -> list[str]:
        song = self._song
        if song is None:
            return []
        right = sum(1 for n in song.notes if n.hand == Hand.RIGHT)
        left = sum(1 for n in song.notes if n.hand == Hand.LEFT)
        minutes, seconds = divmod(int(song.duration), 60)
        lines = [f"{right} right-hand notes · {left} left-hand notes · {minutes}:{seconds:02d}"]
        if song.backing:
            lines.append(f"{len(song.backing)} backing notes play automatically")
        if self._set and self._set.clean and self._set.removed_notes:
            lines.append(f"Cleanup removed or merged {self._set.removed_notes} notes")
        return lines

    def draw(self, surface: pygame.Surface) -> None:
        if self._context is None:
            return
        title = self._set.folder.name if self._set else "Stems"
        rows = self._rows() if self._set else []
        self._context.skin.draw_stems(surface, StemsFrame(
            title=title, rows=rows, selected=self._selected, song=self._song,
            summary=self._summary(), message=self._message,
        ))
