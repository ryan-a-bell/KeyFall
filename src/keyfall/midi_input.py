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
        status = data[0] & 0xF0
        if status == 0x90 and data[2] > 0:
            return LiveNoteEvent(pitch=data[1], velocity=data[2], timestamp=time.time(), is_note_on=True)
        elif status == 0x80 or (status == 0x90 and data[2] == 0):
            return LiveNoteEvent(pitch=data[1], velocity=0, timestamp=time.time(), is_note_on=False)
        return None

    def close(self) -> None:
        if self._open:
            self.midi_in.close_port()
            self._open = False
