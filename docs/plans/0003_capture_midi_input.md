# 0003 — capture_midi_input

## Summary

Listen to a connected MIDI keyboard in real-time, producing timestamped note-on/note-off events that feed into the hit evaluator and audio engine.

## Module

`src/keyfall/midi_input.py`

## Public API

```python
class MidiInput:
    @staticmethod
    def list_ports() -> list[str]: ...
    def open(self) -> None: ...
    def poll(self) -> LiveNoteEvent | None: ...
    def close(self) -> None: ...
```

## Detailed Design

### Port Discovery

1. `list_ports()` creates a temporary `rtmidi.MidiIn()` and returns `get_ports()`.
2. In the UI, present a device selection screen if multiple ports exist.
3. Support a `--midi-port` CLI argument and a config file setting for a default device name (substring match).

### Connection

1. `open()` calls `self.midi_in.open_port(idx)`.
2. If no ports exist, raise `MidiDeviceError` with a user-friendly message.
3. Support hot-plug detection: periodically (every 2s) re-scan ports in a background check. If the active port disappears, pause playback and show a reconnect prompt.

### Message Parsing

1. `poll()` is non-blocking — called once per game loop frame.
2. Read raw MIDI bytes, mask status byte to extract message type:
   - `0x90` + velocity > 0 → `note_on`
   - `0x80` or `0x90` + velocity 0 → `note_off`
   - Ignore control change, pitch bend, etc. for now.
3. Timestamp with `time.perf_counter()` for sub-millisecond accuracy (not `time.time()`).
4. Return `LiveNoteEvent(pitch, velocity, timestamp, is_note_on)`.

### Latency Considerations

- `python-rtmidi` uses a callback-based model internally. We use the polling API (`get_message()`) which drains the internal queue. This adds up to 1 frame of latency (~16ms at 60fps), which is acceptable.
- For tighter latency, a future enhancement could use the callback API with a thread-safe queue (`queue.SimpleQueue`).

### Fallback: Computer Keyboard

For users without a MIDI keyboard, map computer keys to piano notes:

```
Row: z x c v b n m , . /
Map: C4 D4 E4 F4 G4 A4 B4 C5 D5 E5

Row: a s d f g h j k l ;
Map: C#4 D#4 ... (sharps/flats)

Row: q w e r t y u i o p
Map: C5 D5 E5 ... (upper octave)
```

Implement as a `KeyboardInput` class with the same `poll() -> LiveNoteEvent | None` interface.

### New Types

```python
class MidiDeviceError(Exception): ...

class KeyboardInput:
    """Fallback input using computer keyboard."""
    def poll(self) -> LiveNoteEvent | None: ...
```

### Protocol / Interface

Define an `InputSource` protocol so MIDI and keyboard inputs are interchangeable:

```python
class InputSource(Protocol):
    def poll(self) -> LiveNoteEvent | None: ...
    def close(self) -> None: ...
```

## Testing Plan

| Test | Assertion |
|------|-----------|
| `list_ports()` returns list of strings | type check |
| `poll()` returns `None` when no messages | no crash |
| Note-on message parsed correctly | pitch, velocity, is_note_on=True |
| Note-off (velocity 0) parsed correctly | is_note_on=False |
| No MIDI device raises `MidiDeviceError` | exception with message |
| Keyboard fallback maps 'z' to C4 (MIDI 60) | pitch == 60 |

## Dependencies

- `python-rtmidi` (MIT)
- `pygame.event` (for keyboard fallback)

## Open Questions

- Should we support MIDI output (sending light-up signals to compatible keyboards)?
- Should velocity from computer keyboard be configurable or fixed at 80?
