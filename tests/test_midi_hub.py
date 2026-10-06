"""MIDI device picker: the hub that switches input devices at runtime."""

import pygame

from keyfall import accessibility, settings
from keyfall.midi_input import AUTO, NONE, MidiInputHub, normalize_port_name
from keyfall.ui_state import UIState
from keyfall.views.base import ViewContext, ViewManager
from keyfall.views.menu_view import MenuView
from keyfall.views.settings_view import ROW_MIDI, SettingsView


class FakePort:
    def __init__(self, messages):
        self.messages = list(messages)
        self.closed = False

    def get_message(self):
        return (self.messages.pop(0), 0.0) if self.messages else None

    def close_port(self):
        self.closed = True


class FakeBackend:
    def __init__(self, ports, messages=()):
        self.port_names = list(ports)
        self.messages = list(messages)
        self.opened: list[int] = []

    def list_ports(self):
        return list(self.port_names)

    def open(self, index):
        self.opened.append(index)
        return FakePort(self.messages)


def test_normalize_strips_alsa_client_numbers():
    assert normalize_port_name("Roland FP-30X:Roland FP-30X MIDI 1 20:0") == \
        "Roland FP-30X MIDI 1"
    assert normalize_port_name("Client:Other Port 28:0") == "Client:Other Port"
    assert normalize_port_name("USB Keyboard") == "USB Keyboard"


def test_auto_picks_first_device_and_decodes_notes():
    backend = FakeBackend(["Keys A 20:0", "Keys B 24:0"],
                          [[0xF8], [0x90, 60, 100], [0x80, 60, 0], [0x90, 62, 0]])
    hub = MidiInputHub(backend, AUTO)
    assert hub.select(AUTO)
    assert hub.port_name == "Keys A"
    on = hub.poll()  # the clock byte (0xF8) is skipped
    assert (on.pitch, on.velocity, on.is_note_on) == (60, 100, True)
    assert hub.poll().is_note_on is False
    assert hub.poll().is_note_on is False  # note_on with velocity 0 = note off
    assert hub.poll() is None


def test_select_by_saved_name_survives_new_port_numbers():
    backend = FakeBackend(["Other 14:0", "Keys B 28:0"])
    hub = MidiInputHub(backend)
    assert hub.select("Keys B")
    assert backend.opened == [1]


def test_missing_device_and_none_choice():
    hub = MidiInputHub(FakeBackend([]))
    assert not hub.select(AUTO)
    assert hub.error == "No MIDI devices found"
    assert hub.poll() is None
    hub = MidiInputHub(FakeBackend(["Keys 20:0"]))
    assert not hub.select(NONE)
    assert not hub.select("Gone")
    assert "not connected" in hub.error


def test_ensure_connects_keyboard_plugged_in_later():
    backend = FakeBackend([])
    hub = MidiInputHub(backend, AUTO)
    hub.select(AUTO)
    backend.port_names = ["Late Keys 20:0"]
    hub.ensure()
    assert hub.connected and hub.port_name == "Late Keys"


def test_switching_devices_closes_previous_port():
    backend = FakeBackend(["A 1:0", "B 2:0"])
    hub = MidiInputHub(backend)
    hub.select("A")
    first = hub._port
    hub.select("B")
    assert first.closed and hub.port_name == "B"


def test_settings_row_switches_device_and_saves(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    monkeypatch.setattr(accessibility, "_SETTINGS_PATH", tmp_path / "s.json")
    pygame.init()
    hub = MidiInputHub(FakeBackend(["Keys A 20:0", "Keys B 24:0"]))
    hub.select(AUTO)
    ui = UIState()
    ctx = ViewContext(screen_size=(1280, 720), midi_input=hub, audio=None, progress=None, ui=ui)
    vm = ViewManager(ctx)
    vm.register(MenuView)
    vm.register(SettingsView)
    vm.push("settings")
    view = vm.active_view
    view.change(ROW_MIDI, 1)  # auto -> Keys A
    view.change(ROW_MIDI, 1)  # -> Keys B
    assert hub.port_name == "Keys B"
    assert settings.load_devices().midi_input == "Keys B"
    view.change(ROW_MIDI, 1)  # -> off
    assert not hub.connected and ui.devices.midi_input == NONE
    vm.draw(pygame.Surface((1280, 720)))
