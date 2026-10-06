"""Results screen shown when a song ends: grade, timing, comparison, next steps."""

from __future__ import annotations

import pygame

from keyfall.renderer.skins.frames import ResultsFrame, SessionResult
from keyfall.views.base import ViewAction, ViewContext


class ResultsView:
    name = "results"
    display_name = "Results"

    def __init__(self) -> None:
        self._context: ViewContext | None = None
        self._result: SessionResult | None = None
        self._buttons: list[tuple[str, str]] = []  # (label, action)
        self._selected = 0
        self._clock = 0.0

    def on_enter(self, context: ViewContext) -> None:
        self._context = context
        self._result = context.results
        self._clock = 0.0
        self._buttons = [("Play again", "retry")]
        trouble = self._result.trouble if self._result else None
        if trouble:
            self._buttons.append((f"Practice bars {trouble[0]}–{trouble[1]}", "practice"))
        self._buttons.append(("Menu", "menu"))
        self._selected = 1 if trouble else 0  # suggest practicing the weak spot

    def on_exit(self) -> None:
        pass

    def handle_event(self, event: pygame.event.Event) -> ViewAction | None:
        if event.type != pygame.KEYDOWN:
            return None
        key = event.key
        if key == pygame.K_ESCAPE:
            return self._do("menu")
        if key in (pygame.K_LEFT, pygame.K_UP):
            self._selected = (self._selected - 1) % len(self._buttons)
        elif key in (pygame.K_RIGHT, pygame.K_DOWN, pygame.K_TAB):
            self._selected = (self._selected + 1) % len(self._buttons)
        elif key == pygame.K_RETURN:
            return self._do(self._buttons[self._selected][1])
        elif key == pygame.K_r:
            return self._do("retry")
        elif key == pygame.K_p and any(a == "practice" for _, a in self._buttons):
            return self._do("practice")
        return None

    def _do(self, action: str) -> ViewAction:
        ctx = self._context
        if action == "retry" and ctx is not None:
            target = ctx.next_view or "waterfall"
            return ViewAction(kind="switch", target=target, context_patch={"song": ctx.song})
        if action == "practice" and ctx is not None and self._result is not None:
            first, last, _ = self._result.trouble
            return ViewAction(kind="switch", target="practice",
                              context_patch={"song": ctx.song, "section": (first, last)})
        return ViewAction(kind="pop")

    def update(self, dt: float) -> ViewAction | None:
        self._clock += dt
        return None

    def draw(self, surface: pygame.Surface) -> None:
        if self._context is None or self._result is None:
            return
        self._context.skin.draw_results(surface, ResultsFrame(
            result=self._result,
            buttons=[label for label, _ in self._buttons],
            selected=self._selected,
            clock=self._clock,
        ))
