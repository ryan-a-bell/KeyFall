"""Practice mode view with notation, section looping, and hand splitting."""

from __future__ import annotations

import math
from collections import Counter

import pygame

from keyfall.accessibility import NoteLabelMode
from keyfall.evaluator import evaluate_hit
from keyfall.models import Hand, HitGrade, HitResult, NoteEvent, SessionStats, Song
from keyfall.playback import (
    ClickTrack,
    PlaybackEngine,
    SongOutputs,
    bar_of,
    beat_length,
    count_in_seconds,
    select_section,
)
from keyfall.renderer.skins.frames import PlayFrame, SessionResult
from keyfall.views.base import (
    ViewAction,
    appearance,
    ViewContext,
    best_accuracy,
    metronome_mode,
    mic_active,
    poll_inputs,
    stop_outputs,
    update_outputs,
)


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
        self._clock: float = 0.0
        self._judgement: HitGrade | None = None
        self._judgement_at: float = -99.0
        self._offsets: list[float] = []
        self._outputs: SongOutputs | None = None
        self._click = ClickTrack()
        self._press_pos: dict[int, float] = {}
        self._coach = None  # CoachStep when run from the Coach screen
        self._hits: list = []  # HitResults for technique feedback
        self._miss_bars: Counter[int] = Counter()
        self._show_notation: bool = True
        self._looping: bool = False
        self._section_start: int = 1
        self._section_end: int = 4
        self._hit_results: dict[int, HitGrade] = {}
        self._loop_count: int = 0

    def on_enter(self, context: ViewContext) -> None:
        self._context = context
        self._full_song = context.song or Song(title="Empty")
        self._stats = SessionStats(song_title=self._full_song.title)
        self._streak = 0
        self._pressed = set()
        self._pending_notes = []
        self._clock = 0.0
        self._judgement = None
        self._offsets = []
        self._miss_bars = Counter()
        self._hit_results = {}
        self._loop_count = 0

        self._coach = context.coach_step
        self._hits = []
        self._show_notation = appearance(context).notation != "off"
        if self._coach is not None:
            self._section_start, self._section_end = self._coach.first_bar, self._coach.last_bar
            self._looping = False
        elif context.section:  # e.g. "Practice bars 5-6" from the results screen
            self._section_start, self._section_end = context.section
            self._looping = True

        self._build_engine()

    def _build_engine(self) -> None:
        song = self._full_song
        if song is None:
            return
        coach = self._coach
        if self._looping or (coach is not None and coach.rung != "full"):
            song = select_section(song, self._section_start, self._section_end)
        self._engine = PlaybackEngine(song)
        if self._context:
            self._engine.set_tempo_scale(self._context.tempo_scale)
            self._engine.active_hand = self._context.hand
        self._engine.wait_mode = True  # default for practice
        if coach is not None:
            self._engine.wait_mode = coach.wait_mode
            self._engine.set_tempo_scale(coach.tempo_pct / 100)
            self._engine.active_hand = coach.hand
        self._start_position()

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
            if self._coach is not None:  # back to the Coach screen, no verdict
                return self._coach_action(completed=False)
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
        self._clock += dt

        # MIDI keyboard, computer keys, microphone
        engine.required_fraction = 0.6 if mic_active(self._context) else 1.0
        poll_inputs(self._context, self._pressed, self._press_pos, engine.position,
                    engine.expected_pitches())

        newly_active = engine.update(dt, self._pressed)
        # auto-played hand, backing tracks, key lights (synth and/or keyboard)
        self._outputs = update_outputs(self._context, self._outputs, engine, newly_active)
        clicks = self._click.update(engine.position, beat_length(engine.song),
                                    metronome_mode(self._context))
        self._click.play(self._context.audio if self._context else None, clicks)

        for note in newly_active:
            if engine.active_hand == Hand.BOTH or note.hand == engine.active_hand:
                self._pending_notes.append(note)

        still_pending: list[NoteEvent] = []
        for note in self._pending_notes:
            age = engine.position - note.start_time
            if age > 0.3:
                self._stats.missed += 1
                self._streak = 0
                self._judge(HitGrade.MISS, note=note)
                self._hits.append(HitResult(note, None, HitGrade.MISS, 0.0))
            elif note.pitch in self._pressed:
                result = evaluate_hit(note, note.pitch,
                                      self._press_pos.get(note.pitch, engine.position))
                self._judge(result.grade, result.timing_offset_ms, note)
                self._hits.append(result)
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
            elif self._coach is not None:
                return self._coach_action(completed=True)
            else:
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

    def _coach_action(self, completed: bool) -> ViewAction:
        from keyfall.coach import CoachPass
        self._update_accuracy()
        result = CoachPass(self._coach, self._stats.accuracy_pct, self._clock, list(self._hits),
                           completed=completed and self._stats.total_notes > 0)
        return ViewAction(kind="switch", target="coach",
                          context_patch={"results": result, "song": self._full_song,
                                         "coach_step": None})

    def _coach_label(self) -> str:
        return f"Coach · {self._coach.label}" if self._coach is not None else ""

    def _first_bar(self) -> int:
        return self._section_start if self._looping else 1

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
            title=title, mode="Practice",
            stats=self._stats, timing_offsets_ms=list(self._offsets),
            best_before=best_accuracy(self._context, title), miss_bars=dict(self._miss_bars),
        )
        song = self._full_song if hasattr(self, "_full_song") else self._engine.song
        return ViewAction(kind="switch", target="results",
                          context_patch={"results": result, "song": song,
                                         "next_view": "practice"})

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
            mode="Practice",
            label_mode=ctx.ui.accessibility.get_label_mode() if ctx.ui else NoteLabelMode.NONE,
            judgement=self._judgement,
            judgement_age=self._clock - self._judgement_at,
            timing_offsets_ms=self._offsets,
            loop=(self._section_start, self._section_end) if self._looping else None,
            loop_count=self._loop_count,
            show_notation=self._show_notation,
            hit_results=self._hit_results,
            hints="N:notation L:loop [/]:section W:wait +/-:tempo 1/2/3:hand R:restart",
            clock=self._clock,
            rising=appearance(ctx).layout == "rising",
            count_in=(math.ceil(-engine.position / beat_length(engine.song) - 1e-6)
                      if engine.position < 0 else None),
            metronome=metronome_mode(ctx),
            mic_level=ctx.mic_input.level if mic_active(ctx) else None,
            coach=self._coach_label() if hasattr(self, "_coach_label") else "",
        ))
