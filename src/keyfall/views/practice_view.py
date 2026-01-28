"""Practice mode view with notation, section looping, and hand splitting."""

from __future__ import annotations

import pygame

from keyfall.evaluator import evaluate_hit
from keyfall.models import Hand, HitGrade, NoteEvent, SessionStats, Song
from keyfall.notation import render_notation
from keyfall.playback import PlaybackEngine, select_section
from keyfall.renderer import colors as colors_mod
from keyfall.renderer.hud import render_hud
from keyfall.renderer.keyboard import render_keyboard
from keyfall.renderer.waterfall import render_waterfall
from keyfall.views.base import ViewAction, ViewContext, layout_regions


class PracticeView:
    name = "practice"
    display_name = "Practice Mode"

    def __init__(self) -> None:
        self._context: ViewContext | None = None
        self._engine: PlaybackEngine | None = None
        self._full_song: Song | None = None
        self._stats = SessionStats()
        self._pressed: set[int] = set()
        self._streak: int = 0
        self._pending_notes: list[NoteEvent] = []
        self._font: pygame.font.Font | None = None
        self._show_notation: bool = True
        self._looping: bool = False
        self._section_start: int = 1
        self._section_end: int = 4
        self._hit_results: dict[int, HitGrade] = {}
        self._loop_count: int = 0

    def on_enter(self, context: ViewContext) -> None:
        self._context = context
        self._font = pygame.font.SysFont("monospace", 18)
        self._full_song = context.song or Song(title="Empty")
        self._stats = SessionStats(song_title=self._full_song.title)
        self._streak = 0
        self._pressed = set()
        self._pending_notes = []
        self._hit_results = {}
        self._loop_count = 0

        if context.section:
            self._section_start, self._section_end = context.section

        self._build_engine()

    def _build_engine(self) -> None:
        song = self._full_song
        if song is None:
            return
        if self._looping:
            song = select_section(song, self._section_start, self._section_end)
        self._engine = PlaybackEngine(song)
        if self._context:
            self._engine.set_tempo_scale(self._context.tempo_scale)
            self._engine.active_hand = self._context.hand
        self._engine.wait_mode = True  # default for practice

    def on_exit(self) -> None:
        if self._context and self._context.audio:
            self._context.audio.all_notes_off()
        if self._context and self._context.progress:
            self._update_accuracy()
            self._context.progress.save_session(self._stats)

    def handle_event(self, event: pygame.event.Event) -> ViewAction | None:
        if event.type != pygame.KEYDOWN:
            return None

        engine = self._engine
        if engine is None:
            return None

        if event.key == pygame.K_ESCAPE:
            return ViewAction(kind="pop")
        elif event.key == pygame.K_SPACE:
            engine.paused = not engine.paused
        elif event.key == pygame.K_w:
            engine.wait_mode = not engine.wait_mode
        elif event.key == pygame.K_l:
            self._looping = not self._looping
            self._build_engine()
        elif event.key == pygame.K_n:
            self._show_notation = not self._show_notation
        elif event.key == pygame.K_r:
            self._build_engine()
        elif event.key == pygame.K_LEFTBRACKET:
            shift = 4 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1
            self._section_start = max(1, self._section_start - shift)
            if self._looping:
                self._build_engine()
        elif event.key == pygame.K_RIGHTBRACKET:
            shift = 4 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1
            self._section_end += shift
            if self._looping:
                self._build_engine()
        elif event.key == pygame.K_MINUS or event.key == pygame.K_KP_MINUS:
            engine.set_tempo_scale(engine.tempo_scale - 0.05)
        elif event.key == pygame.K_EQUALS or event.key == pygame.K_KP_PLUS:
            engine.set_tempo_scale(engine.tempo_scale + 0.05)
        elif event.key == pygame.K_1:
            engine.active_hand = Hand.BOTH
        elif event.key == pygame.K_2:
            engine.active_hand = Hand.RIGHT
        elif event.key == pygame.K_3:
            engine.active_hand = Hand.LEFT

        return None

    def update(self, dt: float) -> ViewAction | None:
        engine = self._engine
        if engine is None:
            return None

        # Poll MIDI and keyboard input
        if self._context:
            for source in (self._context.midi_input, self._context.keyboard_input):
                if source is None:
                    continue
                while True:
                    evt = source.poll()
                    if evt is None:
                        break
                    if evt.is_note_on:
                        self._pressed.add(evt.pitch)
                        if self._context.audio:
                            self._context.audio.note_on(evt.pitch, evt.velocity)
                    else:
                        self._pressed.discard(evt.pitch)
                        if self._context.audio:
                            self._context.audio.note_off(evt.pitch)

        newly_active = engine.update(dt, self._pressed)

        for note in newly_active:
            self._pending_notes.append(note)
            # Auto-play inactive hand
            if self._context and self._context.audio:
                if engine.active_hand != Hand.BOTH and note.hand != engine.active_hand:
                    self._context.audio.play_note_event(note)

        still_pending: list[NoteEvent] = []
        for note in self._pending_notes:
            age = engine.position - note.start_time
            if age > 0.3:
                self._stats.missed += 1
                self._streak = 0
            elif note.pitch in self._pressed:
                result = evaluate_hit(note, note.pitch, engine.position)
                if result.grade == HitGrade.PERFECT:
                    self._stats.perfect += 1
                    self._streak += 1
                elif result.grade == HitGrade.GOOD:
                    self._stats.good += 1
                    self._streak += 1
                elif result.grade == HitGrade.OK:
                    self._stats.ok += 1
                    self._streak += 1
                else:
                    self._stats.missed += 1
                    self._streak = 0
                self._stats.max_streak = max(self._stats.max_streak, self._streak)
            else:
                still_pending.append(note)
                continue
            self._update_accuracy()
        self._pending_notes = still_pending

        # Loop restart
        if engine.finished and not self._pending_notes:
            if self._looping:
                self._loop_count += 1
                self._build_engine()
            else:
                return ViewAction(kind="pop")

        return None

    def _update_accuracy(self) -> None:
        hit = self._stats.perfect + self._stats.good + self._stats.ok
        total = hit + self._stats.missed
        self._stats.total_notes = total
        self._stats.accuracy_pct = (hit / total * 100.0) if total > 0 else 0.0

    def draw(self, surface: pygame.Surface) -> None:
        engine = self._engine
        if engine is None:
            return

        surface.fill(colors_mod.BG)
        w, h = surface.get_size()

        regions = layout_regions(
            pygame.Rect(0, 0, w, h),
            [
                ("hud", "top", 44),
                ("keyboard", "bottom", 120),
            ] + ([("notation", "top", 180)] if self._show_notation else []),
        )

        # Notation panel
        if self._show_notation:
            nr = regions["notation"]
            render_notation(
                surface, engine.song, engine.position,
                x=nr.x, y=nr.y, width=nr.w, height=nr.h,
                hit_results=self._hit_results,
            )

        # Waterfall in center region
        render_waterfall(surface, engine.song, engine.position)

        # Keyboard
        render_keyboard(surface, self._pressed)

        # HUD
        render_hud(surface, self._stats)

        # Status info
        if self._font:
            info_parts = [
                f"Tempo: {engine.tempo_scale:.0%}",
                f"{'WAIT' if engine.wait_mode else 'PLAY'}",
                f"Hand: {engine.active_hand.name}",
            ]
            if self._looping:
                info_parts.append(f"Loop: bars {self._section_start}-{self._section_end} (#{self._loop_count})")
            if engine.paused:
                info_parts.append("PAUSED")
            info_text = " | ".join(info_parts)
            rendered = self._font.render(info_text, True, colors_mod.HUD_TEXT)
            surface.blit(rendered, (w - rendered.get_width() - 10, 10))

        # Controls hint
        if self._font:
            hint = self._font.render(
                "N:notation L:loop [/]:section W:wait +/-:tempo 1/2/3:hand R:restart",
                True, (80, 80, 100),
            )
            surface.blit(hint, (10, h - 25))
