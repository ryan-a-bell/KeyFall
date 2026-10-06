"""MIDI output to the player's keyboard: accompaniment sound and key lights."""

from __future__ import annotations

import time

from keyfall.midi_input import AUTO, NONE, normalize_port_name
from keyfall.models import NoteEvent

try:
    import rtmidi
    _HAS_RTMIDI = True
except ImportError:
    _HAS_RTMIDI = False

# What gets sent to the keyboard
MODE_ACCOMPANIMENT = "accompaniment"  # backing stems + the auto-played hand
MODE_LIGHTS = "lights"  # upcoming notes for the player, for light-up keys
MODE_BOTH = "both"
OUTPUT_MODES = (MODE_ACCOMPANIMENT, MODE_LIGHTS, MODE_BOTH)


class RtMidiOutBackend:
    def __init__(self) -> None:
        self._probe = None
        if _HAS_RTMIDI:
            try:
                self._probe = rtmidi.MidiOut()
            except Exception:  # no MIDI subsystem
                self._probe = None

    def list_ports(self) -> list[str]:
        if self._probe is None:
            return []
        try:
            return list(self._probe.get_ports())
        except Exception:
            return []

    def open(self, index: int):
        port = rtmidi.MidiOut()
        port.open_port(index)
        return port


class MidiOutputHub:
    """The app's single MIDI output. ``choice`` is NONE (default), AUTO, or a port name."""

    def __init__(self, backend=None, choice: str = NONE) -> None:
        self.backend = backend if backend is not None else RtMidiOutBackend()
        self.choice = choice
        self.port_name: str | None = None
        self.error = ""
        self._port = None
        self._pending_offs: list[tuple[float, int, int]] = []  # (off_time, pitch, channel)
        self._programs: dict[int, int] = {}

    @property
    def connected(self) -> bool:
        return self._port is not None

    def ports(self) -> list[str]:
        return [normalize_port_name(p) for p in self.backend.list_ports()]

    def select(self, choice: str) -> bool:
        self.close()
        self.choice = choice
        self.error = ""
        if choice == NONE:
            return False
        ports = self.ports()
        if not ports:
            self.error = "No MIDI outputs found"
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

    def send(self, message: list[int]) -> None:
        if self._port is None:
            return
        try:
            self._port.send_message(message)
        except Exception:
            self.close()  # unplugged mid-song: stop sending, don't crash

    def note_on(self, pitch: int, velocity: int, channel: int = 0) -> None:
        self.send([0x90 | channel, pitch & 0x7F, max(1, min(127, velocity))])

    def note_off(self, pitch: int, channel: int = 0) -> None:
        self.send([0x80 | channel, pitch & 0x7F, 0])

    def program_change(self, channel: int, program: int) -> None:
        if self._programs.get(channel) != program:
            self._programs[channel] = program
            self.send([0xC0 | channel, program & 0x7F])

    def play_note_event(self, note: NoteEvent, channel: int = 0) -> None:
        self.note_on(note.pitch, note.velocity, channel)
        self._pending_offs.append((time.time() + note.duration, note.pitch, channel))

    def flush_pending_offs(self) -> None:
        now = time.time()
        keep = []
        for off_time, pitch, channel in self._pending_offs:
            if now >= off_time:
                self.note_off(pitch, channel)
            else:
                keep.append((off_time, pitch, channel))
        self._pending_offs = keep

    def all_notes_off(self) -> None:
        for _, pitch, channel in self._pending_offs:
            self.note_off(pitch, channel)
        self._pending_offs.clear()
        for channel in range(16):
            self.send([0xB0 | channel, 123, 0])  # All Notes Off

    def close(self) -> None:
        if self._port is not None:
            self.all_notes_off()
            try:
                self._port.close_port()
            except Exception:
                pass
        self._port = None
        self.port_name = None
        self._programs.clear()
