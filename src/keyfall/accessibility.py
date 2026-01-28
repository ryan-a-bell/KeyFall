"""Accessibility settings and utilities."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from enum import Enum, auto
from pathlib import Path


class ColorPalette(Enum):
    DEFAULT = auto()       # Blue / Orange
    PROTANOPIA = auto()    # Blue / Yellow
    TRITANOPIA = auto()    # Red / Cyan
    HIGH_CONTRAST = auto() # White / Bright Yellow on black
    MONOCHROME = auto()    # Pattern-based


class NoteLabelMode(Enum):
    NONE = auto()
    NOTE_NAME = auto()
    FINGER_NUMBER = auto()
    SOLFEGE = auto()
    MIDI_NUMBER = auto()


# RGB palette sets: (right_hand, left_hand, bg)
PALETTE_COLORS: dict[ColorPalette, tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]] = {
    ColorPalette.DEFAULT: ((66, 135, 245), (245, 166, 66), (18, 18, 24)),
    ColorPalette.PROTANOPIA: ((66, 135, 245), (245, 220, 50), (18, 18, 24)),
    ColorPalette.TRITANOPIA: ((220, 60, 60), (60, 220, 220), (18, 18, 24)),
    ColorPalette.HIGH_CONTRAST: ((255, 255, 255), (255, 255, 60), (0, 0, 0)),
    ColorPalette.MONOCHROME: ((200, 200, 200), (140, 140, 140), (0, 0, 0)),
}


@dataclass
class AccessibilitySettings:
    color_palette: str = "DEFAULT"
    high_contrast: bool = False
    note_labels: str = "NONE"
    screen_reader: bool = False
    large_text: bool = False
    input_latency_offset_ms: float = 0.0

    def get_palette(self) -> ColorPalette:
        try:
            return ColorPalette[self.color_palette]
        except KeyError:
            return ColorPalette.DEFAULT

    def get_label_mode(self) -> NoteLabelMode:
        try:
            return NoteLabelMode[self.note_labels]
        except KeyError:
            return NoteLabelMode.NONE


_SETTINGS_PATH = Path.home() / ".keyfall" / "settings.json"


def load_settings() -> AccessibilitySettings:
    """Load accessibility settings from disk, returning defaults if absent."""
    if not _SETTINGS_PATH.exists():
        return AccessibilitySettings()
    try:
        data = json.loads(_SETTINGS_PATH.read_text())
        a11y = data.get("accessibility", {})
        return AccessibilitySettings(**{
            k: v for k, v in a11y.items()
            if k in AccessibilitySettings.__dataclass_fields__
        })
    except Exception:
        return AccessibilitySettings()


def save_settings(settings: AccessibilitySettings) -> None:
    """Persist accessibility settings to disk."""
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if _SETTINGS_PATH.exists():
        try:
            data = json.loads(_SETTINGS_PATH.read_text())
        except Exception:
            pass
    data["accessibility"] = asdict(settings)
    _SETTINGS_PATH.write_text(json.dumps(data, indent=2))


def apply_accessibility(settings: AccessibilitySettings) -> None:
    """Apply accessibility settings to the renderer color module and config.

    This modifies the global color values used by the renderers at runtime.
    """
    import keyfall.renderer.colors as colors

    palette = settings.get_palette()
    if settings.high_contrast:
        palette = ColorPalette.HIGH_CONTRAST

    rh, lh, bg = PALETTE_COLORS.get(palette, PALETTE_COLORS[ColorPalette.DEFAULT])
    colors.NOTE_RIGHT_HAND = rh
    colors.NOTE_LEFT_HAND = lh
    colors.BG = bg

    if palette == ColorPalette.HIGH_CONTRAST:
        colors.HUD_TEXT = (255, 255, 255)
        colors.WHITE_KEY = (255, 255, 255)
        colors.BLACK_KEY = (0, 0, 0)

    if settings.screen_reader:
        speak("Accessibility settings applied")


def speak(text: str) -> None:
    """Fire-and-forget TTS announcement. No-op if TTS unavailable."""
    try:
        if sys.platform == "linux":
            subprocess.Popen(
                ["espeak", "-s", "160", text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "darwin":
            subprocess.Popen(["say", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            subprocess.Popen(
                ["powershell", "-Command",
                 f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text}')"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except FileNotFoundError:
        pass
