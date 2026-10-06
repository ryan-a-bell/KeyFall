"""Classic waterfall gameplay view."""

from __future__ import annotations

import math
from collections import Counter

import pygame

from keyfall.accessibility import NoteLabelMode
from keyfall.evaluator import evaluate_hit
from keyfall.models import Hand, HitGrade, NoteEvent, SessionStats, Song
from keyfall.playback import (
    ClickTrack,
    PlaybackEngine,
    SongOutputs,
    bar_of,
    beat_length,
    count_in_seconds,
)
from keyfall.renderer.skins.frames import PlayFrame, SessionResult
from keyfall.views.base import (
    ViewAction,
    ViewContext,
    best_accuracy,
    metronome_mode,
    stop_outputs,
    update_outputs,
)


class WaterfallView:
    name = "waterfall"
    display_name = "Classic Waterfall"

    def __init__(self) -> None:
        self._context: ViewContext | None = None
        self._engine: PlaybackEngine | None = None
        self._stats = SessionStats()
        self._pressed: set[int] = set()
        self._streak: int = 0
        self._pending_notes: list[NoteEvent] = []
        self._clock: float = 0.0
        self._judgement: HitGrade | None = None
        self._judgement_at: float = -99.0
        self._offsets: list[float] = []
        self._outputs: SongOutputs | None = None
        self._click = ClickTrack()
        self._miss_bars: Counter[int] = Counter()

    def on_enter(self, context: ViewContext) -> None:
        self._context = context
        song = context.song
        if song is None:
            song = Song(title="Empty")
        self._engine = PlaybackEngine(song)
        self._engine.set_tempo_scale(context.tempo_scale)
        self._engine.active_hand = context.hand
        self._stats = SessionStats(song_title=song.title)
        self._start_position()
        self._streak = 0
        self._pressed = set()
        self._pending_notes = []
        self._clock = 0.0
        self._judgement = None
        self._offsets = []
        self._miss_bars = Counter()

    def on_exit(self) -> None:
        stop_outputs(self._context, self._outputs)
        self._outputs = None
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
        elif event.key == pygame.K_r:
            self._start_position()
            self._pending_notes = []
        elif event.key == pygame.K_MINUS or event.key == pygame.K_KP_MINUS:
            engine.set_tempo_scale(engine.tempo_scale - 0.05)
        elif event.key == pygame.K_EQUALS or event.key == pygame.K_KP_PLUS:
            engine.set_tempo_scale(engine.tempo_scale + 0.05)
        elif event.key == pygame.K_0:
            engine.set_tempo_scale(1.0)
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
        self._clock += dt

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

        # Advance playback
        newly_active = engine.update(dt, self._pressed)
        # auto-played hand, backing tracks, key lights (synth and/or keyboard)
        self._outputs = update_outputs(self._context, self._outputs, engine, newly_active)
        clicks = self._click.update(engine.position, beat_length(engine.song),
                                    metronome_mode(self._context))
        self._click.play(self._context.audio if self._context else None, clicks)

        # Evaluate hits
        for note in newly_active:
            if engine.active_hand == Hand.BOTH or note.hand == engine.active_hand:
                self._pending_notes.append(note)

        # Evaluate pending notes against pressed keys
        still_pending: list[NoteEvent] = []
        for note in self._pending_notes:
            age = engine.position - note.start_time
            if age > 0.3:  # missed
                self._stats.missed += 1
                self._streak = 0
                self._judge(HitGrade.MISS, note=note)
            elif note.pitch in self._pressed:
                result = evaluate_hit(note, note.pitch, engine.position)
                self._judge(result.grade, result.timing_offset_ms, note)
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

        if engine.finished and not self._pending_notes:
            return self._results()

        return None

    def _judge(self, grade: HitGrade, offset_ms: float | None = None,
               note: NoteEvent | None = None) -> None:
        self._judgement = grade
        self._judgement_at = self._clock
        if grade == HitGrade.MISS and note is not None and self._engine is not None:
            self._miss_bars[bar_of(note.start_time, self._engine.song, self._first_bar())] += 1
        if offset_ms is not None:
            self._offsets.append(offset_ms)
            del self._offsets[:-300]

    def _first_bar(self) -> int:
        return 1

    def _start_position(self) -> None:
        """Rewind to one bar before the song so the count-in clicks lead into it."""
        engine = self._engine
        engine.position = -count_in_seconds(engine.song, metronome_mode(self._context))
        engine.note_index = 0
        self._click.reset()

    def _results(self) -> ViewAction:
        self._update_accuracy()
        title = self._stats.song_title
        result = SessionResult(
            title=title, mode="Play",
            stats=self._stats, timing_offsets_ms=list(self._offsets),
            best_before=best_accuracy(self._context, title), miss_bars=dict(self._miss_bars),
        )
        song = self._full_song if hasattr(self, "_full_song") else self._engine.song
        return ViewAction(kind="switch", target="results",
                          context_patch={"results": result, "song": song,
                                         "next_view": "waterfall"})

    def _update_accuracy(self) -> None:
        hit = self._stats.perfect + self._stats.good + self._stats.ok
        total = hit + self._stats.missed
        self._stats.total_notes = total
        self._stats.accuracy_pct = (hit / total * 100.0) if total > 0 else 0.0

    def draw(self, surface: pygame.Surface) -> None:
        engine = self._engine
        if engine is None or self._context is None:
            return
        ctx = self._context
        self._context.skin.draw_play(surface, PlayFrame(
            song=engine.song,
            position=engine.position,
            pressed=self._pressed,
            stats=self._stats,
            streak=self._streak,
            tempo_scale=engine.tempo_scale,
            wait_mode=engine.wait_mode,
            paused=engine.paused,
            active_hand=engine.active_hand,
            mode="Play",
            label_mode=ctx.ui.accessibility.get_label_mode() if ctx.ui else NoteLabelMode.NONE,
            judgement=self._judgement,
            judgement_age=self._clock - self._judgement_at,
            timing_offsets_ms=self._offsets,
            hints="Space: pause | W: wait | +/-: tempo | 1/2/3: hands | R: restart | Esc: menu",
            clock=self._clock,
            count_in=(math.ceil(-engine.position / beat_length(engine.song) - 1e-6)
                      if engine.position < 0 else None),
            metronome=metronome_mode(ctx),
        ))
