"""Shared, mutable UI state: current settings and the active skin.

One instance is shared by every view (ViewContext copies keep the same
reference), so changing the theme in Settings restyles every screen at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from keyfall.accessibility import AccessibilitySettings, save_settings
from keyfall.renderer.skins import Skin, create_skin
from keyfall.soundfont import SoundFontDownloader
from keyfall.settings import (
    AppearanceSettings,
    DeviceSettings,
    save_appearance,
    save_devices,
)


@dataclass
class UIState:
    appearance: AppearanceSettings = field(default_factory=AppearanceSettings)
    accessibility: AccessibilitySettings = field(default_factory=AccessibilitySettings)
    devices: DeviceSettings = field(default_factory=DeviceSettings)
    persist: bool = True  # False in tests / when settings shouldn't be written
    downloader: SoundFontDownloader = field(default_factory=SoundFontDownloader)
    skin: Skin = field(init=False)

    def __post_init__(self) -> None:
        self.rebuild()

    def rebuild(self) -> None:
        self.skin = create_skin(self.appearance.theme, self.appearance.effects,
                                self.accessibility)

    def apply_downloads(self, audio) -> list[str]:
        """Load finished SoundFont downloads into the running audio engine.

        Called from the UI thread (never from download threads). Returns
        messages describing what changed.
        """
        messages = []
        for job in self.downloader.finished_unapplied():
            job.applied = True
            if audio is None or job.path is None:
                messages.append(f"{job.spec.label} downloaded; it will be used next time")
                continue
            try:
                if job.spec.key == "gm":
                    audio.load_gm_soundfont(job.path)
                else:
                    audio.load_soundfont(job.path)
                messages.append(f"{job.spec.label} installed and in use")
            except RuntimeError as exc:
                messages.append(f"{job.spec.label} downloaded, but could not load: {exc}")
        return messages

    def apply(self) -> None:
        """Rebuild the skin after a settings change and save to disk."""
        self.rebuild()
        if self.persist:
            save_appearance(self.appearance)
            save_settings(self.accessibility)
            save_devices(self.devices)
