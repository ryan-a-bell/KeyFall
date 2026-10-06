"""Real-time MIDI input capture from connected keyboards."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pygame

try:
    import rtmidi
    _HAS_RTMIDI = True
except ImportError:
    _HAS_RTMIDI = False


@dataclass
class LiveNoteEvent:
    pitch: int
    velocity: int
    timestamp: float
    is_note_on: bool


class MidiDeviceError(Exception):
    """Raised when no MIDI device is found or connection fails."""


@runtime_checkable
class InputSource(Protocol):
    """Common interface for MIDI and keyboard input sources."""
    def poll(self) -> LiveNoteEvent | None: ...
    def close(self) -> None: ...


# Computer keyboard -> MIDI pitch mapping
_LOWER_ROW = {
    pygame.K_z: 60, pygame.K_x: 62, pygame.K_c: 64, pygame.K_v: 65,
    pygame.K_b: 67, pygame.K_n: 69, pygame.K_m: 71, pygame.K_COMMA: 72,
    pygame.K_PERIOD: 74, pygame.K_SLASH: 76,
}
_MIDDLE_ROW = {
    pygame.K_a: 61, pygame.K_s: 63, pygame.K_d: 66, pygame.K_f: 68,
    pygame.K_g: 70, pygame.K_h: 73, pygame.K_j: 75, pygame.K_k: 77,
    pygame.K_l: 78, pygame.K_SEMICOLON: 80,
}
_UPPER_ROW = {
    pygame.K_q: 72, pygame.K_w: 74, pygame.K_e: 76, pygame.K_r: 77,
    pygame.K_t: 79, pygame.K_y: 81, pygame.K_u: 83, pygame.K_i: 84,
    pygame.K_o: 86, pygame.K_p: 88,
}
_KEY_TO_PITCH: dict[int, int] = {**_LOWER_ROW, **_MIDDLE_ROW, **_UPPER_ROW}


class KeyboardInput:
    """Fallback input using computer keyboard mapped to piano notes."""

    def __init__(self, velocity: int = 80) -> None:
        self._velocity = velocity
        self._events: list[LiveNoteEvent] = []
        self._held: set[int] = set()

    def feed_event(self, event: pygame.event.Event) -> None:
        """Call from the game loop for each pygame event."""
        if event.type == pygame.KEYDOWN and event.key in _KEY_TO_PITCH:
            pitch = _KEY_TO_PITCH[event.key]
            if pitch not in self._held:
                self._held.add(pitch)
                self._events.append(LiveNoteEvent(
                    pitch=pitch, velocity=self._velocity,
                    timestamp=time.time(), is_note_on=True,
                ))
        elif event.type == pygame.KEYUP and event.key in _KEY_TO_PITCH:
            pitch = _KEY_TO_PITCH[event.key]
            self._held.discard(pitch)
            self._events.append(LiveNoteEvent(
                pitch=pitch, velocity=0,
                timestamp=time.time(), is_note_on=False,
            ))

    def poll(self) -> LiveNoteEvent | None:
        if self._events:
            return self._events.pop(0)
        return None

    def close(self) -> None:
        self._events.clear()
        self._held.clear()


class MidiInput:
    def __init__(self, port_index: int | None = None) -> None:
        if not _HAS_RTMIDI:
            raise MidiDeviceError("python-rtmidi is not installed")
        self.midi_in = rtmidi.MidiIn()
        self._port_index = port_index
        self._open = False

    @staticmethod
    def list_ports() -> list[str]:
        if not _HAS_RTMIDI:
            return []
        midi_in = rtmidi.MidiIn()
        return midi_in.get_ports()

    def open(self) -> None:
        ports = self.midi_in.get_ports()
        if not ports:
            raise MidiDeviceError("No MIDI input devices found")
        idx = self._port_index if self._port_index is not None else 0
        self.midi_in.open_port(idx)
        self._open = True

    def poll(self) -> LiveNoteEvent | None:
        """Non-blocking poll for the next MIDI message. Returns None if no message."""
        if not self._open:
            return None
        msg = self.midi_in.get_message()
        if msg is None:
            return None
        data, _delta = msg
        return _decode(data)

    def close(self) -> None:
        if self._open:
            self.midi_in.close_port()
            self._open = False


# --------------------------------------------------------------------------- device picker

AUTO = "auto"  # first available device
NONE = "none"  # computer keyboard only


def normalize_port_name(name: str) -> str:
    """Drop the session-specific client/port numbers ALSA appends (e.g. ' 20:0').

    Saved choices then still match after a reboot or replug.
    """
    import re
    name = re.sub(r"\s+\d+:\d+$", "", name).strip()
    # ALSA reports "Client:Port"; the port usually repeats the client ("FP-30X:FP-30X MIDI 1")
    client, sep, port = name.partition(":")
    if sep and port.startswith(client):
        name = port
    return name


class RtMidiBackend:
    """Thin wrapper over python-rtmidi. Any failure means "no devices"."""

    def __init__(self) -> None:
        self._probe = None
        if _HAS_RTMIDI:
            try:
                self._probe = rtmidi.MidiIn()
            except Exception:  # no MIDI subsystem (e.g. no ALSA sequencer)
                self._probe = None

    @property
    def available(self) -> bool:
        return self._probe is not None

    def list_ports(self) -> list[str]:
        if self._probe is None:
            return []
        try:
            return list(self._probe.get_ports())
        except Exception:
            return []

    def open(self, index: int):
        port = rtmidi.MidiIn()
        port.open_port(index)
        return port


def _decode(data) -> LiveNoteEvent | None:
    if not data or len(data) < 3:
        return None
    status = data[0] & 0xF0
    if status == 0x90 and data[2] > 0:
        return LiveNoteEvent(pitch=data[1], velocity=data[2], timestamp=time.time(),
                             is_note_on=True)
    if status == 0x80 or (status == 0x90 and data[2] == 0):
        return LiveNoteEvent(pitch=data[1], velocity=0, timestamp=time.time(), is_note_on=False)
    return None


class MidiInputHub:
    """The app's single MIDI input. Views poll it; Settings switches devices live.

    ``choice`` is AUTO, NONE, or a normalized port name. The hub stays usable
    (polls return None) when nothing is connected or rtmidi is unavailable.
    """

    def __init__(self, backend=None, choice: str = AUTO) -> None:
        self.backend = backend if backend is not None else RtMidiBackend()
        self.choice = choice
        self.port_name: str | None = None
        self.error: str = ""
        self._port = None

    @property
    def connected(self) -> bool:
        return self._port is not None

    def ports(self) -> list[str]:
        return [normalize_port_name(p) for p in self.backend.list_ports()]

    def select(self, choice: str) -> bool:
        """Switch to ``choice`` now. Returns True if a device is connected afterwards."""
        self.close()
        self.choice = choice
        self.error = ""
        if choice == NONE:
            return False
        ports = self.ports()
        if not ports:
            self.error = "No MIDI devices found"
            return False
        if choice == AUTO:
            index = 0
        elif choice in ports:
            index = ports.index(choice)
        else:
            self.error = f"{choice} is not connected"
            return False
        try:
            self._port = self.backend.open(index)
            self.port_name = ports[index]
        except Exception as exc:
            self._port = None
            self.error = f"Could not open {ports[index]}: {exc}"
        return self.connected

    def ensure(self) -> None:
        """Retry the saved choice if it isn't connected (e.g. keyboard plugged in late)."""
        if not self.connected and self.choice != NONE:
            self.select(self.choice)

    def poll(self) -> LiveNoteEvent | None:
        while self._port is not None:
            try:
                msg = self._port.get_message()
            except Exception:
                self.close()
                return None
            if msg is None:
                return None
            event = _decode(msg[0])
            if event is not None:
                return event  # skip clock/CC/etc. and keep reading
        return None

    def close(self) -> None:
        if self._port is not None:
            try:
                self._port.close_port()
            except Exception:
                pass
        self._port = None
        self.port_name = None
