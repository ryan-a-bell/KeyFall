# 0011 — free_play_sandbox (Bonus)

## Summary

A mode with no song loaded where the player can freely play the piano with audio feedback, see chord detection, record performances, and experiment.

## Module

`src/keyfall/free_play.py` (new)

## Public API

```python
class FreePlayMode:
    def __init__(self, audio: AudioEngine, input_source: InputSource) -> None: ...
    def update(self, dt: float) -> None: ...
    def get_active_chord(self) -> str | None: ...
    def start_recording(self) -> None: ...
    def stop_recording(self) -> Song: ...
```

## Detailed Design

### Core Loop

1. Poll input every frame.
2. Forward note_on/note_off to the audio engine for immediate playback.
3. Track currently held notes for chord detection and keyboard highlighting.
4. No scoring, no song, no waterfall — just the keyboard renderer and HUD.

### Chord Detection

1. Maintain a set of currently held pitches.
2. When the set changes, analyze the interval pattern to identify the chord:
   - Map held pitches to pitch classes (mod 12).
   - Match against known chord templates:
     ```
     Major:     {0, 4, 7}
     Minor:     {0, 3, 7}
     Dim:       {0, 3, 6}
     Aug:       {0, 4, 8}
     Dom7:      {0, 4, 7, 10}
     Maj7:      {0, 4, 7, 11}
     Min7:      {0, 3, 7, 10}
     ```
   - Try all 12 roots, pick the best match.
3. Display the chord name above the keyboard (e.g., "Cm7", "G", "F#dim").

### Key Signature Context

- Optional: let the user select a key signature.
- Highlight scale tones on the keyboard (dimly lit).
- Show the scale degree of each played note relative to the key.

### Recording

1. `start_recording()` — begin capturing `NoteEvent`s with timestamps.
2. `stop_recording()` — return a `Song` object containing the recorded notes.
3. The recorded song can be:
   - Played back immediately (review mode).
   - Saved as a MIDI file via `mido`.
   - Loaded into practice mode to practice your own composition.

### MIDI Export

```python
def export_midi(song: Song, output_path: Path) -> None:
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    # Convert NoteEvents to mido messages with delta times
    ...
    mid.save(str(output_path))
```

### UI Elements

- Piano keyboard (full width, bottom).
- Chord name display (large, centered above keyboard).
- Key signature selector (dropdown or key shortcuts).
- Record button (red circle, top-right).
- Recording timer.
- Instrument selector (change MIDI program: piano, electric piano, organ, etc.).

## Testing Plan

| Test | Assertion |
|------|-----------|
| Chord detection: C-E-G | "C" |
| Chord detection: A-C-E | "Am" |
| Chord detection: empty | None |
| Recording captures notes | `len(song.notes) > 0` after playing |
| MIDI export produces valid file | `mido.MidiFile` can re-read it |

## Dependencies

- Internal: `audio.py`, `midi_input.py`, `models.py`, `renderer/keyboard.py`
- `mido` for MIDI export
