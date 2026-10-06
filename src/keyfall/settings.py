"""User settings persisted to ~/.keyfall/settings.json.

The file holds one section per area (``appearance``, ``accessibility``, ...).
Saving one section never drops the others.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path.home() / ".keyfall" / "settings.json"

EFFECT_LEVELS = ("full", "reduced", "off")


@dataclass
class AppearanceSettings:
    theme: str = "studio"
    effects: str = "full"  # one of EFFECT_LEVELS


@dataclass
class DeviceSettings:
    midi_input: str = "auto"  # "auto", "none", or a MIDI port name


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
    path = path or SETTINGS_PATH
    data = _read_all(path)
    data[name] = asdict(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def load_appearance(path: Path | None = None) -> AppearanceSettings:
    settings = load_section("appearance", AppearanceSettings, path)
    if settings.effects not in EFFECT_LEVELS:
        settings.effects = "full"
    return settings


def save_appearance(settings: AppearanceSettings, path: Path | None = None) -> None:
    save_section("appearance", settings, path)


def load_devices(path: Path | None = None) -> DeviceSettings:
    return load_section("devices", DeviceSettings, path)


def save_devices(settings: DeviceSettings, path: Path | None = None) -> None:
    save_section("devices", settings, path)
