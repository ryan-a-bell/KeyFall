"""Swappable visual styles. Pick one with :func:`create_skin`."""

from __future__ import annotations

from keyfall.accessibility import AccessibilitySettings
from keyfall.renderer.skins.base import Skin
from keyfall.renderer.skins.classic import ClassicSkin
from keyfall.renderer.skins.neon import NeonSkin
from keyfall.renderer.skins.studio import StudioSkin

SKINS: dict[str, type[Skin]] = {
    "classic": ClassicSkin,
    "studio": StudioSkin,
    "neon": NeonSkin,
}
DEFAULT_SKIN = "studio"


def create_skin(name: str, effects: str = "full",
                accessibility: AccessibilitySettings | None = None) -> Skin:
    """Build the named skin; unknown names fall back to the default."""
    cls = SKINS.get(name, SKINS[DEFAULT_SKIN])
    return cls(effects=effects, accessibility=accessibility)


__all__ = ["SKINS", "DEFAULT_SKIN", "Skin", "create_skin"]
