"""Sending sound and key lights to the player's keyboard."""

import pygame

from keyfall import accessibility, settings
from keyfall.midi_input import NONE
from keyfall.midi_output import MidiOutputHub
from keyfall.models import Hand, NoteEvent, Song
from keyfall.playback import KeyLights, PlaybackEngine, SongOutputs
from keyfall.ui_state import UIState
from keyfall.views.base import ViewContext, ViewManager
from keyfall.views.settings_view import ROW_OUT, ROW_OUT_MODE, SettingsView


class RecordingPort:
    def __init__(self):
        self.sent = []
        self.closed = False

    def send_message(self, msg):
        self.sent.append(list(msg))

    def close_port(self):
        self.closed = True


class OutBackend:
    def __init__(self, ports=("Roland FP-30X:Roland FP-30X MIDI 1 20:0",)):
        self.port_names = list(ports)
        self.ports_opened = []

    def list_ports(self):
        return list(self.port_names)

    def open(self, index):
        port = RecordingPort()
        self.ports_opened.append(port)
        return port


def _hub():
    hub = MidiOutputHub(OutBackend())
    assert hub.select("Roland FP-30X MIDI 1")
    return hub, hub._port


def test_output_is_off_by_default():
    hub = MidiOutputHub(OutBackend())
    assert not hub.select(NONE) and not hub.connected
    hub.note_on(60, 100)  # silently ignored


def test_note_events_program_changes_and_all_notes_off():
    hub, port = _hub()
    hub.program_change(1, 25)
    hub.program_change(1, 25)  # duplicate suppressed
    hub.play_note_event(NoteEvent(64, 0.0, 0.0, 90), channel=1)
    hub.flush_pending_offs()
    assert port.sent[:3] == [[0xC1, 25], [0x91, 64, 90], [0x81, 64, 0]]
    hub.close()
    assert [0xB0 | 15, 123, 0] in port.sent and port.closed


def test_key_lights_turn_on_ahead_and_off_after():
    hub, port = _hub()
    song = Song(notes=[NoteEvent(60, 1.0, 0.5, hand=Hand.RIGHT),
                       NoteEvent(48, 1.0, 0.5, hand=Hand.LEFT)])
    lights = KeyLights()
    lights.update(song, 0.2, Hand.BOTH, hub, channel=3)
    assert port.sent == []  # too early
    lights.update(song, 0.6, Hand.RIGHT, hub, channel=3)  # practicing right hand only
    assert port.sent == [[0x93, 60, 1]]
    lights.update(song, 1.6, Hand.RIGHT, hub, channel=3)
    assert port.sent[-1] == [0x83, 60, 0]


def _routing(mode):
    hub, port = _hub()
    song = Song(notes=[NoteEvent(60, 0.0, 0.4, hand=Hand.RIGHT),
                       NoteEvent(48, 0.0, 0.4, hand=Hand.LEFT)],
                backing=[NoteEvent(67, 0.0, 0.4, track=3)], backing_programs={3: 48})
    engine = PlaybackEngine(song)
    engine.active_hand = Hand.RIGHT
    outputs = SongOutputs(song)
    newly = engine.update(0.1, set())
    outputs.update(engine, newly, None, hub, mode, light_channel=10)
    return port.sent


def test_accompaniment_sends_backing_and_the_other_hand():
    sent = _routing("accompaniment")
    assert [0x90, 48, 80] in sent  # left hand auto-played on channel 1
    assert any(m[0] == 0xC1 and m[1] == 48 for m in sent)  # strings program
    assert any(m[0] == 0x91 and m[1] == 67 for m in sent)  # backing note
    assert not any(m[0] == 0x9A for m in sent)  # no lights


def test_lights_mode_sends_only_lights():
    sent = _routing("lights")
    assert sent == [[0x9A, 60, 1]]  # the right-hand note the player must press


def test_settings_rows_pick_output_device_and_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    monkeypatch.setattr(accessibility, "_SETTINGS_PATH", tmp_path / "s.json")
    pygame.init()
    hub = MidiOutputHub(OutBackend())
    ui = UIState()
    ctx = ViewContext(screen_size=(1280, 720), midi_input=None, audio=None, progress=None,
                      midi_output=hub, ui=ui)
    vm = ViewManager(ctx)
    vm.register(SettingsView)
    vm.push("settings")
    view = vm.active_view
    view.change(ROW_OUT, 1)
    assert hub.connected and hub.port_name == "Roland FP-30X MIDI 1"
    view.change(ROW_OUT_MODE, 1)
    assert ui.devices.output_mode == "lights"
    saved = settings.load_devices()
    assert (saved.midi_output, saved.output_mode) == ("Roland FP-30X MIDI 1", "lights")
    vm.draw(pygame.Surface((1280, 720)))
    view.change(ROW_OUT, 1)  # back to off
    assert not hub.connected
