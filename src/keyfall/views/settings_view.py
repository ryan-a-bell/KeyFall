"""Settings screen: theme, visual effects, note labels, and hand colors.

Changes apply immediately (the whole app restyles) and are saved to
~/.keyfall/settings.json.
"""

from __future__ import annotations

import pygame

from keyfall.accessibility import ColorPalette, NoteLabelMode
from keyfall.mic_input import SENSITIVITIES
from keyfall.midi_input import AUTO, NONE
from keyfall.midi_output import MODE_ACCOMPANIMENT, MODE_BOTH, MODE_LIGHTS, OUTPUT_MODES
from keyfall.renderer.skins import create_skin
from keyfall.renderer.skins.demo import demo_frame, demo_song
from keyfall.renderer.skins.frames import SettingsFrame, SettingsRow
from keyfall.renderer.theme import THEME_ORDER, THEMES
from keyfall.settings import EFFECT_LEVELS, METRONOME_MODES
from keyfall.soundfont import GM_DOWNLOAD, PIANO_DOWNLOAD, installed_path
from keyfall.views.base import ViewAction, ViewContext

_EFFECT_NAMES = {"full": "Full", "reduced": "Reduced", "off": "Off"}
_LABEL_OPTIONS = [NoteLabelMode.NONE, NoteLabelMode.NOTE_NAME, NoteLabelMode.SOLFEGE,
                  NoteLabelMode.MIDI_NUMBER]
_LABEL_NAMES = {
    NoteLabelMode.NONE: "Off",
    NoteLabelMode.NOTE_NAME: "Letters (C D E)",
    NoteLabelMode.SOLFEGE: "Solfège (Do Re Mi)",
    NoteLabelMode.MIDI_NUMBER: "MIDI numbers",
}
_PALETTES = [ColorPalette.DEFAULT, ColorPalette.PROTANOPIA, ColorPalette.TRITANOPIA,
             ColorPalette.HIGH_CONTRAST, ColorPalette.MONOCHROME]
_PALETTE_NAMES = {
    ColorPalette.DEFAULT: "Theme colors",
    ColorPalette.PROTANOPIA: "Protanopia",
    ColorPalette.TRITANOPIA: "Tritanopia",
    ColorPalette.HIGH_CONTRAST: "High contrast",
    ColorPalette.MONOCHROME: "Monochrome",
}

(ROW_THEME, ROW_EFFECTS, ROW_LABELS, ROW_COLORS, ROW_METRONOME, ROW_MIDI, ROW_MIC,
 ROW_MIC_SENS, ROW_OUT, ROW_OUT_MODE, ROW_PIANO, ROW_GM, ROW_DONE) = range(13)
ROW_COUNT = 13
_SENS_NAMES = {"low": "Low (noisy room)", "normal": "Normal", "high": "High (quiet piano)"}
_METRONOME_NAMES = {"off": "Off", "count-in": "Count-in only", "on": "Always"}
_DOWNLOAD_ROWS = {ROW_PIANO: PIANO_DOWNLOAD, ROW_GM: GM_DOWNLOAD}
_OUT_MODE_NAMES = {MODE_ACCOMPANIMENT: "Accompaniment", MODE_LIGHTS: "Key lights",
                   MODE_BOTH: "Both"}


def _cycle(options: list, current, step: int):
    i = options.index(current) if current in options else 0
    return options[(i + step) % len(options)]


class SettingsView:
    name = "settings"
    display_name = "Settings"

    def __init__(self) -> None:
        self._context: ViewContext | None = None
        self._selected = ROW_THEME
        self._preview_key: tuple | None = None
        self._preview: pygame.Surface | None = None
        self._song = demo_song()
        self._message = ""

    def on_enter(self, context: ViewContext) -> None:
        self._context = context
        context.skin  # ensure a UIState exists
        self._ports: list[str] = self._scan_ports()
        self._out_ports: list[str] = self._scan_out_ports()

    def _mic_hub(self):
        hub = self._context.mic_input if self._context else None
        return hub if hasattr(hub, "select") else None

    def _change_mic(self, step: int) -> None:
        hub = self._mic_hub()
        ui = self._context.ui
        if hub is None or ui is None:
            return
        options = [NONE, AUTO, *hub.ports()]
        current = ui.devices.mic_input
        if current not in options:
            options.insert(2, current)
        ui.devices.mic_input = _cycle(options, current, step)
        hub.set_sensitivity(ui.devices.mic_sensitivity)
        hub.select(ui.devices.mic_input)

    def _mic_rows(self) -> list[SettingsRow]:
        hub = self._mic_hub()
        devices = self._context.ui.devices
        choice = devices.mic_input
        value = {NONE: "Off", AUTO: "Default mic"}.get(choice, choice)
        if hub is None:
            status = "Microphone unavailable"
        elif hub.connected:
            hub.poll()  # keep analysing so the meter moves while Settings is open
            bars = int(round(hub.level * 10))
            status = f"Listening  {'|' * bars}{'.' * (10 - bars)}  play a note to test"
        elif choice == NONE:
            status = "For acoustic pianos (use headphones for song sound)"
        else:
            status = hub.error or "Not connected"
        return [
            SettingsRow("Microphone", value, status),
            SettingsRow("Mic sensitivity", _SENS_NAMES[devices.mic_sensitivity],
                        "Lower it if notes trigger by themselves; raise it if notes are missed"),
        ]

    def _out_hub(self):
        hub = self._context.midi_output if self._context else None
        return hub if hasattr(hub, "select") else None

    def _scan_out_ports(self) -> list[str]:
        hub = self._out_hub()
        return hub.ports() if hub else []

    def _change_output(self, step: int) -> None:
        hub = self._out_hub()
        ui = self._context.ui
        if hub is None or ui is None:
            return
        self._out_ports = self._scan_out_ports()
        options = [NONE, *self._out_ports]
        current = ui.devices.midi_output
        if current not in options and current != AUTO:
            options.insert(1, current)
        ui.devices.midi_output = _cycle(options, current, step)
        hub.select(ui.devices.midi_output)

    def _hub(self):
        hub = self._context.midi_input if self._context else None
        return hub if hasattr(hub, "select") else None

    def _scan_ports(self) -> list[str]:
        hub = self._hub()
        return hub.ports() if hub else []

    def _change_midi(self, step: int) -> None:
        hub = self._hub()
        ui = self._context.ui
        if hub is None or ui is None:
            return
        self._ports = self._scan_ports()  # rescan so newly plugged keyboards appear
        options = [AUTO, *self._ports, NONE]
        current = ui.devices.midi_input
        if current not in options:  # saved device currently unplugged
            options.insert(1, current)
        ui.devices.midi_input = _cycle(options, current, step)
        hub.select(ui.devices.midi_input)

    def on_exit(self) -> None:
        pass

    # ------------------------------------------------------------------ input
    def handle_event(self, event: pygame.event.Event) -> ViewAction | None:
        if event.type != pygame.KEYDOWN or self._context is None:
            return None
        if event.key in (pygame.K_ESCAPE, pygame.K_s):
            return ViewAction(kind="pop")
        if event.key == pygame.K_UP:
            self._selected = (self._selected - 1) % ROW_COUNT
        elif event.key in (pygame.K_DOWN, pygame.K_TAB):
            self._selected = (self._selected + 1) % ROW_COUNT
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self.change(self._selected, -1 if event.key == pygame.K_LEFT else 1)
        elif event.key == pygame.K_RETURN:
            if self._selected == ROW_DONE:
                return ViewAction(kind="pop")
            self.change(self._selected, 1)
        return None

    def change(self, row: int, step: int) -> None:
        ui = self._context.ui if self._context else None
        if ui is None:
            return
        a, acc = ui.appearance, ui.accessibility
        if row == ROW_THEME:
            a.theme = _cycle(THEME_ORDER, a.theme, step)
        elif row == ROW_EFFECTS:
            a.effects = _cycle(list(EFFECT_LEVELS), a.effects, step)
        elif row == ROW_LABELS:
            acc.note_labels = _cycle(_LABEL_OPTIONS, acc.get_label_mode(), step).name
        elif row == ROW_COLORS:
            acc.color_palette = _cycle(_PALETTES, acc.get_palette(), step).name
        elif row == ROW_METRONOME:
            ui.practice.metronome = _cycle(list(METRONOME_MODES), ui.practice.metronome, step)
        elif row == ROW_MIDI:
            self._change_midi(step)
        elif row == ROW_MIC:
            self._change_mic(step)
        elif row == ROW_MIC_SENS:
            ui.devices.mic_sensitivity = _cycle(list(SENSITIVITIES), ui.devices.mic_sensitivity,
                                                step)
            if self._mic_hub() is not None:
                self._mic_hub().set_sensitivity(ui.devices.mic_sensitivity)
        elif row == ROW_OUT:
            self._change_output(step)
        elif row == ROW_OUT_MODE:
            ui.devices.output_mode = _cycle(list(OUTPUT_MODES), ui.devices.output_mode, step)
        elif row in _DOWNLOAD_ROWS:
            self.start_download(_DOWNLOAD_ROWS[row])
            return
        else:
            return
        try:
            ui.apply()
            self._message = "Saved"
        except OSError as exc:
            ui.rebuild()
            self._message = f"Applied, but could not save: {exc}"

    def start_download(self, spec) -> None:
        ui = self._context.ui
        job = ui.downloader.jobs.get(spec.key)
        if installed_path(spec) is not None and (job is None or job.status != "error"):
            self._message = f"{spec.label} is already installed"
            return
        ui.downloader.start(spec)
        self._message = f"Downloading {spec.label}…"

    # ------------------------------------------------------------------ frame
    def update(self, dt: float) -> ViewAction | None:
        if self._context and self._context.ui:
            messages = self._context.ui.apply_downloads(self._context.audio)
            if messages:
                self._message = " · ".join(messages)
        return None

    def _rows(self) -> list[SettingsRow]:
        ui = self._context.ui
        a, acc = ui.appearance, ui.accessibility
        theme = THEMES.get(a.theme, THEMES["studio"])
        return [
            SettingsRow("Theme", theme.display_name, "Overall look of menus and gameplay"),
            SettingsRow("Visual effects", _EFFECT_NAMES[a.effects],
                        "Glow, light beams and sparks (lower for slower computers)"),
            SettingsRow("Note labels", _LABEL_NAMES.get(acc.get_label_mode(), "Off"),
                        "Show note names on the falling notes"),
            SettingsRow("Hand colors", _PALETTE_NAMES[acc.get_palette()],
                        "Colorblind-friendly palettes override the theme"),
            SettingsRow("Metronome", _METRONOME_NAMES[ui.practice.metronome],
                        "Count-in bar before each song or loop; Always clicks every beat"),
            self._midi_row(),
            *self._mic_rows(),
            *self._output_rows(),
            self._download_row(PIANO_DOWNLOAD, "Grand piano for your playing (CC-BY 3.0)"),
            self._download_row(GM_DOWNLOAD, "Guitar, strings, bass, drums… for backing (MIT)"),
            SettingsRow("Done", "", "", adjustable=False),
        ]

    def _midi_row(self) -> SettingsRow:
        hub = self._hub()
        choice = self._context.ui.devices.midi_input
        value = {AUTO: "Auto", NONE: "Off (computer keys)"}.get(choice, choice)
        if hub is None:
            status = "MIDI unavailable"
        elif hub.connected:
            status = f"Connected: {hub.port_name}"
        elif choice == NONE:
            status = "Using the computer keyboard"
        else:
            found = len(self._ports)
            status = hub.error or f"{found} device{'s' if found != 1 else ''} found"
        return SettingsRow("MIDI keyboard", value, status)

    def _output_rows(self) -> list[SettingsRow]:
        hub = self._out_hub()
        devices = self._context.ui.devices
        choice = devices.midi_output
        value = {NONE: "Off", AUTO: "Auto"}.get(choice, choice)
        if hub is None:
            status = "MIDI unavailable"
        elif hub.connected:
            status = f"Sending to: {hub.port_name}"
        elif choice == NONE:
            found = len(self._out_ports)
            status = f"Song sound stays on the computer · {found} output" + \
                ("s" if found != 1 else "") + " found"
        else:
            status = hub.error or "Not connected"
        mode = devices.output_mode
        mode_desc = {
            MODE_ACCOMPANIMENT: "Backing and the auto-played hand play on the keyboard",
            MODE_LIGHTS: f"Light up the next keys to press (channel {devices.light_channel})",
            MODE_BOTH: f"Accompaniment, plus key lights on channel {devices.light_channel}",
        }[mode]
        return [
            SettingsRow("Keyboard output", value, status),
            SettingsRow("Send to keyboard", _OUT_MODE_NAMES[mode], mode_desc),
        ]

    def _download_row(self, spec, about: str) -> SettingsRow:
        job = self._context.ui.downloader.jobs.get(spec.key)
        if job is not None and job.status == "downloading":
            if job.fraction >= 0.999:
                return SettingsRow(spec.label, "Installing…", "Verifying and unpacking",
                                   button=True, progress=1.0)
            done_mb = job.fraction * spec.size_mb
            return SettingsRow(spec.label, f"{job.fraction:.0%}",
                               f"Downloading… {done_mb:.0f} of {spec.size_mb} MB",
                               button=True, progress=job.fraction)
        if job is not None and job.status == "error":
            return SettingsRow(spec.label, "Retry", f"Download failed: {job.error}"[:70],
                               button=True)
        if installed_path(spec) is not None:
            return SettingsRow(spec.label, "Installed", about, button=True)
        return SettingsRow(spec.label, f"Download · {spec.size_mb} MB", about, button=True)

    def _preview_surface(self) -> pygame.Surface:
        """Render the current settings onto a demo song (cached until settings change)."""
        ui = self._context.ui
        key = (ui.appearance.theme, ui.appearance.effects, ui.accessibility.color_palette,
               ui.accessibility.note_labels)
        if key != self._preview_key or self._preview is None:
            skin = create_skin(ui.appearance.theme, ui.appearance.effects, ui.accessibility)
            surf = pygame.Surface(self._context.screen_size)
            skin.draw_play(surf, demo_frame(self._song,
                                            label_mode=ui.accessibility.get_label_mode()))
            self._preview, self._preview_key = surf, key
        return self._preview

    def draw(self, surface: pygame.Surface) -> None:
        if self._context is None:
            return
        ui = self._context.ui
        theme = THEMES.get(ui.appearance.theme, THEMES["studio"])
        self._context.skin.draw_settings(surface, SettingsFrame(
            rows=self._rows(),
            selected=self._selected,
            preview=self._preview_surface(),
            theme_description=theme.description,
            message=self._message,
        ))
