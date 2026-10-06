"""Settings screen: theme, visual effects, note labels, and hand colors.

Changes apply immediately (the whole app restyles) and are saved to
~/.keyfall/settings.json.
"""

from __future__ import annotations

import pygame

from keyfall.accessibility import ColorPalette, NoteLabelMode
from keyfall.midi_input import AUTO, NONE
from keyfall.midi_output import MODE_ACCOMPANIMENT, MODE_BOTH, MODE_LIGHTS, OUTPUT_MODES
from keyfall.renderer.skins import create_skin
from keyfall.renderer.skins.demo import demo_frame, demo_song
from keyfall.renderer.skins.frames import SettingsFrame, SettingsRow
from keyfall.renderer.theme import THEME_ORDER, THEMES
from keyfall.settings import EFFECT_LEVELS
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

(ROW_THEME, ROW_EFFECTS, ROW_LABELS, ROW_COLORS, ROW_MIDI, ROW_OUT, ROW_OUT_MODE,
 ROW_DONE) = range(8)
ROW_COUNT = 8
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
        elif row == ROW_MIDI:
            self._change_midi(step)
        elif row == ROW_OUT:
            self._change_output(step)
        elif row == ROW_OUT_MODE:
            ui.devices.output_mode = _cycle(list(OUTPUT_MODES), ui.devices.output_mode, step)
        else:
            return
        try:
            ui.apply()
            self._message = "Saved"
        except OSError as exc:
            ui.rebuild()
            self._message = f"Applied, but could not save: {exc}"

    # ------------------------------------------------------------------ frame
    def update(self, dt: float) -> ViewAction | None:
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
            self._midi_row(),
            *self._output_rows(),
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
