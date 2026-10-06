"""Practice Coach screen: the song's section map, the next step, and feedback."""

from __future__ import annotations

from pathlib import Path

import pygame

from keyfall.coach import COACH_DIR, CoachPass, CoachState, technique_tips
from keyfall.renderer.skins.frames import CoachFrame, CoachSection
from keyfall.views.base import ViewAction, ViewContext

_WHY = {
    "right": "Learn the right hand alone first. Wait mode: the music waits for you.",
    "left": "Now the left hand alone, still in wait mode.",
    "together": "Put both hands together, slowly. The music waits for each chord.",
    "tempo": "Play it in real time. The tempo goes up each time you reach 90%.",
    "full": "Every section is mastered. Put it all together.",
}


class CoachView:
    name = "coach"
    display_name = "Practice Coach"
    coach_dir: Path | None = None  # tests point this somewhere temporary

    def __init__(self) -> None:
        self._context: ViewContext | None = None
        self._state: CoachState | None = None
        self._verdict = ""
        self._tips: list[str] = []
        self._selected = 0
        self._buttons = [("Start", "start"), ("Skip step", "skip"), ("Menu", "menu")]

    def on_enter(self, context: ViewContext) -> None:
        self._context = context
        self._verdict, self._tips = "", []
        self._advanced = False
        song = context.song
        if song is None or not song.notes:
            self._state = None
            return
        self._state = CoachState.load(song, self.coach_dir or COACH_DIR)
        result = context.results
        if isinstance(result, CoachPass) and result.completed:
            before = self._state.next_step()
            self._verdict = self._state.record_pass(result.step, result.accuracy, result.seconds)
            self._advanced = self._state.next_step() != before
            if result.step.rung in ("tempo", "full"):  # timing tips need real-time play
                self._tips = technique_tips(result.hits)
            self._save()
        elif isinstance(result, CoachPass):
            self._verdict = "Step stopped early. Press Enter to try it again."
        self._selected = 0

    def _save(self) -> None:
        try:
            self._state.save(self.coach_dir or COACH_DIR)
        except OSError:
            pass

    def on_exit(self) -> None:
        pass

    def handle_event(self, event: pygame.event.Event) -> ViewAction | None:
        if event.type != pygame.KEYDOWN:
            return None
        if event.key == pygame.K_ESCAPE:
            return ViewAction(kind="pop")
        if event.key in (pygame.K_LEFT, pygame.K_UP):
            self._selected = (self._selected - 1) % len(self._buttons)
        elif event.key in (pygame.K_RIGHT, pygame.K_DOWN, pygame.K_TAB):
            self._selected = (self._selected + 1) % len(self._buttons)
        elif event.key == pygame.K_RETURN:
            return self._do(self._buttons[self._selected][1])
        return None

    def _do(self, action: str) -> ViewAction | None:
        if action == "menu" or self._state is None:
            return ViewAction(kind="pop")
        step = self._state.next_step()
        if action == "skip":
            self._verdict = "Skipped. " + self._state.record_pass(step, 100.0, 0.0)
            self._advanced = False
            self._tips = []
            self._save()
            return None
        return ViewAction(kind="switch", target="practice",
                          context_patch={"song": self._context.song, "coach_step": step,
                                         "results": None})

    def update(self, dt: float) -> ViewAction | None:
        return None

    def frame(self) -> CoachFrame | None:
        state = self._state
        if state is None:
            return None
        current = state.current_section()
        sections = [CoachSection(s.first_bar, s.last_bar, s.progress, s.mastered,
                                 s is current, s.rung or s.ladder()[0], s.tempo_pct)
                    for s in state.sections]
        step = state.next_step()
        passes, minutes = state.today()
        return CoachFrame(
            title=state.song_title, mastery=state.mastery, sections=sections,
            step_label=step.label, step_why=_WHY[step.rung], verdict=self._verdict,
            tips=self._tips, today_passes=passes, today_minutes=minutes,
            daily=state.daily_accuracy(), buttons=[b for b, _ in self._buttons],
            selected=self._selected,
        )

    def draw(self, surface: pygame.Surface) -> None:
        if self._context is None:
            return
        frame = self.frame()
        if frame is None:
            surface.fill(self._context.skin.p.bg)
            return
        self._context.skin.draw_coach(surface, frame)
