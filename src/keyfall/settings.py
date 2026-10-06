"""User settings persisted to ~/.keyfall/settings.json.

The file holds one section per area (``appearance``, ``accessibility``, ...).
Saving one section never drops the others, and stamps that section's ``updated_at``
(under ``_updated``) so sync can keep the most recent edit of each section.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from keyfall.storage import data_dir, now_iso

SETTINGS_PATH = data_dir() / "settings.json"
STAMPS_KEY = "_updated"  # {section: ISO time of its last local save}
# Sections that follow the player between devices; "devices" names this machine's ports.
SYNCED_SECTIONS = ("appearance", "accessibility", "practice")

EFFECT_LEVELS = ("full", "reduced", "off")


@dataclass
class AppearanceSettings:
    theme: str = "studio"
    effects: str = "full"  # one of EFFECT_LEVELS
    # where the sheet music goes: "above" the falling notes, or "below" the piano
    layout: str = "above"
    notation: str = "practice"  # sheet music: "practice" (Practice only), "always", or "off"


LAYOUTS = ("above", "below")
_OLD_LAYOUTS = {"falling": "above", "rising": "below"}  # values saved by earlier versions
NOTATION_MODES = ("practice", "always", "off")


@dataclass
class DeviceSettings:
    midi_input: str = "auto"  # "auto", "none", or a MIDI port name
    midi_output: str = "none"  # keyboard to send sound/lights to: "none", "auto", or a name
    output_mode: str = "accompaniment"  # "accompaniment", "lights", or "both"
    light_channel: int = 1  # MIDI channel (1-16) for key-light notes
    mic_input: str = "none"  # microphone for an acoustic piano: "none", "auto", or a name
    mic_sensitivity: str = "normal"  # "low", "normal", "high"


@dataclass
class PracticeSettings:
    metronome: str = "count-in"  # "off", "count-in" (one bar before playing), or "on"


METRONOME_MODES = ("off", "count-in", "on")


def _read_all(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_section(name: str, cls: type, path: Path | None = None):
    """Load one section into dataclass ``cls``; unknown keys are ignored."""
    raw = _read_all(path or SETTINGS_PATH).get(name, {})
    if not isinstance(raw, dict):
        raw = {}
    known = {f.name for f in fields(cls)}
    try:
        return cls(**{k: v for k, v in raw.items() if k in known})
    except Exception:
        return cls()


def save_section(name: str, value: Any, path: Path | None = None) -> None:
    """Write one dataclass section, preserving every other section in the file."""
    _write_section(name, asdict(value), now_iso(), path or SETTINGS_PATH)


def _write_section(name: str, values: dict[str, Any], updated_at: str, path: Path) -> None:
    data = _read_all(path)
    data[name] = values
    stamps = data.get(STAMPS_KEY)
    data[STAMPS_KEY] = {**(stamps if isinstance(stamps, dict) else {}), name: updated_at}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def synced_sections(path: Path | None = None) -> dict[str, tuple[dict[str, Any], str]]:
    """``{section: (values, updated_at)}`` for each saved section that syncs."""
    data = _read_all(path or SETTINGS_PATH)
    stamps = data.get(STAMPS_KEY)
    stamps = stamps if isinstance(stamps, dict) else {}
    return {name: (data[name], str(stamps.get(name, "")))
            for name in SYNCED_SECTIONS if isinstance(data.get(name), dict)}


def apply_remote_section(name: str, values: dict[str, Any], updated_at: str,
                         path: Path | None = None) -> bool:
    """Take a section saved on another device if it's newer than ours. True if applied."""
    if name not in SYNCED_SECTIONS or not isinstance(values, dict):
        return False
    local = synced_sections(path).get(name)
    if local is not None and local[1] >= updated_at:
        return False
    _write_section(name, values, updated_at, path or SETTINGS_PATH)
    return True


def load_appearance(path: Path | None = None) -> AppearanceSettings:
    settings = load_section("appearance", AppearanceSettings, path)
    if settings.effects not in EFFECT_LEVELS:
        settings.effects = "full"
    settings.layout = _OLD_LAYOUTS.get(settings.layout, settings.layout)
    if settings.layout not in LAYOUTS:
        settings.layout = "above"
    if settings.notation not in NOTATION_MODES:
        settings.notation = "practice"
    return settings


def save_appearance(settings: AppearanceSettings, path: Path | None = None) -> None:
    save_section("appearance", settings, path)


def load_devices(path: Path | None = None) -> DeviceSettings:
    return load_section("devices", DeviceSettings, path)


def save_devices(settings: DeviceSettings, path: Path | None = None) -> None:
    save_section("devices", settings, path)


def load_practice(path: Path | None = None) -> PracticeSettings:
    settings = load_section("practice", PracticeSettings, path)
    if settings.metronome not in METRONOME_MODES:
        settings.metronome = "count-in"
    return settings


def save_practice(settings: PracticeSettings, path: Path | None = None) -> None:
    save_section("practice", settings, path)
