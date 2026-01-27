"""Plugin manager — discovers and registers plugins via entry points."""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Any, Protocol, runtime_checkable

import pygame

from keyfall.models import HitResult, Song

logger = logging.getLogger(__name__)


@runtime_checkable
class ScoringPlugin(Protocol):
    name: str
    def on_hit(self, result: HitResult) -> int: ...
    def on_frame(self, dt: float) -> None: ...
    def get_score(self) -> int: ...


@runtime_checkable
class VisualizationPlugin(Protocol):
    name: str
    def render(self, surface: pygame.Surface, song: Song, position: float) -> None: ...


@runtime_checkable
class InputPlugin(Protocol):
    name: str
    def poll(self) -> Any: ...
    def close(self) -> None: ...


class PluginManager:
    """Discovers and manages plugins from entry points."""

    def __init__(self) -> None:
        self._scoring: list[ScoringPlugin] = []
        self._visualizations: list[VisualizationPlugin] = []
        self._inputs: list[InputPlugin] = []
        self._view_classes: list[type] = []
        self._panel_classes: list[type] = []

    def discover(self) -> None:
        """Scan entry points for keyfall plugins."""
        for group, handler in [
            ("keyfall.plugins", self._register_generic),
            ("keyfall.views", self._register_view),
            ("keyfall.panels", self._register_panel),
        ]:
            try:
                eps = entry_points(group=group)
            except TypeError:
                eps = entry_points().get(group, [])
            for ep in eps:
                try:
                    cls = ep.load()
                    handler(cls)
                except Exception as exc:
                    logger.warning("Failed to load plugin %s: %s", ep.name, exc)

    def _register_generic(self, cls: type) -> None:
        instance = cls()
        if isinstance(instance, ScoringPlugin):
            self._scoring.append(instance)
        elif isinstance(instance, VisualizationPlugin):
            self._visualizations.append(instance)
        elif isinstance(instance, InputPlugin):
            self._inputs.append(instance)

    def _register_view(self, cls: type) -> None:
        self._view_classes.append(cls)

    def _register_panel(self, cls: type) -> None:
        self._panel_classes.append(cls)

    def get_scoring_plugins(self) -> list[ScoringPlugin]:
        return list(self._scoring)

    def get_visualization_plugins(self) -> list[VisualizationPlugin]:
        return list(self._visualizations)

    def get_input_plugins(self) -> list[InputPlugin]:
        return list(self._inputs)

    def get_view_plugins(self) -> list[type]:
        return list(self._view_classes)

    def get_panel_plugins(self) -> list[type]:
        return list(self._panel_classes)
