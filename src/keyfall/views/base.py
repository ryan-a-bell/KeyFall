"""View protocol, ViewContext, ViewAction, and ViewManager."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

import pygame

from keyfall.models import Hand, Song

if TYPE_CHECKING:
    from keyfall.audio import AudioEngine
    from keyfall.midi_input import KeyboardInput, MidiInput
    from keyfall.plugins.manager import PluginManager
    from keyfall.progress import ProgressTracker


@dataclass
class ViewContext:
    """Shared state passed to views on entry."""

    screen_size: tuple[int, int]
    midi_input: MidiInput | None
    audio: AudioEngine | None
    progress: ProgressTracker | None
    plugin_manager: PluginManager | None = None
    keyboard_input: KeyboardInput | None = None
    song: Song | None = None
    section: tuple[int, int] | None = None
    hand: Hand = Hand.BOTH
    tempo_scale: float = 1.0
    songs_dir: str = ""


@dataclass
class ViewAction:
    """Navigation command returned by views."""

    kind: Literal["push", "pop", "switch", "quit"]
    target: str | None = None
    context_patch: dict[str, Any] | None = None


@runtime_checkable
class Panel(Protocol):
    """A composable sub-region within a view (reusable across views)."""

    def layout(self, rect: pygame.Rect) -> None: ...
    def handle_event(self, event: pygame.event.Event) -> None: ...
    def update(self, dt: float) -> None: ...
    def draw(self, surface: pygame.Surface) -> None: ...


@runtime_checkable
class View(Protocol):
    """A full-screen game state."""

    name: str
    display_name: str

    def on_enter(self, context: ViewContext) -> None: ...
    def on_exit(self) -> None: ...
    def handle_event(self, event: pygame.event.Event) -> ViewAction | None: ...
    def update(self, dt: float) -> ViewAction | None: ...
    def draw(self, surface: pygame.Surface) -> None: ...


class ViewManager:
    """Owns the view stack and dispatches the game loop to the active view."""

    def __init__(self, context: ViewContext) -> None:
        self._registry: dict[str, type] = {}
        self._stack: list[tuple[View, ViewContext]] = []
        self._context = context

    def register(self, view_cls: type) -> None:
        instance = view_cls()
        self._registry[instance.name] = view_cls

    def list_views(self) -> list[tuple[str, str]]:
        return [(name, cls().display_name) for name, cls in self._registry.items()]

    def push(self, view_name: str, **context_overrides: Any) -> None:
        if self._stack:
            self._stack[-1][0].on_exit()
        view = self._registry[view_name]()
        ctx = self._patched_context(context_overrides)
        view.on_enter(ctx)
        self._stack.append((view, ctx))

    def pop(self) -> None:
        if self._stack:
            self._stack.pop()[0].on_exit()
        if self._stack:
            view, ctx = self._stack[-1]
            view.on_enter(ctx)

    def switch(self, view_name: str, **context_overrides: Any) -> None:
        if self._stack:
            self._stack.pop()[0].on_exit()
        self.push(view_name, **context_overrides)

    @property
    def active_view(self) -> View | None:
        return self._stack[-1][0] if self._stack else None

    def handle_event(self, event: pygame.event.Event) -> bool:
        if (view := self.active_view) is None:
            return False
        action = view.handle_event(event)
        return self._process_action(action)

    def update(self, dt: float) -> bool:
        if (view := self.active_view) is None:
            return False
        action = view.update(dt)
        return self._process_action(action)

    def draw(self, surface: pygame.Surface) -> None:
        if (view := self.active_view) is not None:
            view.draw(surface)

    def _process_action(self, action: ViewAction | None) -> bool:
        if action is None:
            return True
        if action.kind == "quit":
            return False
        elif action.kind == "push":
            self.push(action.target, **(action.context_patch or {}))
        elif action.kind == "pop":
            self.pop()
        elif action.kind == "switch":
            self.switch(action.target, **(action.context_patch or {}))
        return True

    def _patched_context(self, overrides: dict[str, Any]) -> ViewContext:
        if not overrides:
            return self._context
        ctx = ViewContext(
            screen_size=self._context.screen_size,
            midi_input=self._context.midi_input,
            audio=self._context.audio,
            progress=self._context.progress,
            plugin_manager=self._context.plugin_manager,
            keyboard_input=self._context.keyboard_input,
            song=self._context.song,
            section=self._context.section,
            hand=self._context.hand,
            tempo_scale=self._context.tempo_scale,
            songs_dir=self._context.songs_dir,
        )
        for key, val in overrides.items():
            if hasattr(ctx, key):
                setattr(ctx, key, val)
        return ctx


def layout_regions(
    total: pygame.Rect,
    specs: list[tuple[str, Literal["top", "bottom", "left", "right"], int]],
) -> dict[str, pygame.Rect]:
    """Carve out named regions from a total rect. Remainder is 'center'."""
    remaining = total.copy()
    regions: dict[str, pygame.Rect] = {}

    for name, anchor, size in specs:
        if anchor == "top":
            regions[name] = pygame.Rect(remaining.x, remaining.y, remaining.w, size)
            remaining = pygame.Rect(remaining.x, remaining.y + size, remaining.w, remaining.h - size)
        elif anchor == "bottom":
            regions[name] = pygame.Rect(remaining.x, remaining.bottom - size, remaining.w, size)
            remaining = pygame.Rect(remaining.x, remaining.y, remaining.w, remaining.h - size)
        elif anchor == "left":
            regions[name] = pygame.Rect(remaining.x, remaining.y, size, remaining.h)
            remaining = pygame.Rect(remaining.x + size, remaining.y, remaining.w - size, remaining.h)
        elif anchor == "right":
            regions[name] = pygame.Rect(remaining.right - size, remaining.y, size, remaining.h)
            remaining = pygame.Rect(remaining.x, remaining.y, remaining.w - size, remaining.h)

    regions["center"] = remaining
    return regions
