"""Real-time MIDI input capture from connected keyboards."""

from __future__ import annotations

import time
from dataclasses import dataclass

import rtmidi


@dataclass
class LiveNoteEvent:
    pitch: int
    velocity: int
    timestamp: float
    is_note_on: bool


class MidiInput:
    def __init__(self, port_index: int | None = None) -> None:
        self.midi_in = rtmidi.MidiIn()
        self._port_index = port_index
        self._open = False

    @staticmethod
    def list_ports() -> list[str]:
        midi_in = rtmidi.MidiIn()
        return midi_in.get_ports()

    def open(self) -> None:
        ports = self.midi_in.get_ports()
        if not ports:
            raise RuntimeError("No MIDI input devices found")
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
