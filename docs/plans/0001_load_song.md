# 0001 — load_song

## Summary

Parse MIDI (`.mid`, `.midi`) and MusicXML (`.xml`, `.mxl`, `.musicxml`) files into the internal `Song` data model. This is the foundation — every other feature depends on having a normalized song representation.

## Module

`src/keyfall/song_loader.py`

## Public API

```python
def load_song(file_path: str | Path) -> Song: ...
```

## Detailed Design

### MIDI Loading (`mido`)

1. Open the file with `mido.MidiFile`.
2. Extract `ticks_per_beat` from the header.
3. Walk every track, accumulating absolute time (converting delta ticks to seconds via `mido.tick2second`).
4. Track `set_tempo` meta-messages to build `tempo_changes` list.
5. Track `time_signature` meta-messages to build `time_signatures` list.
6. For `note_on` (velocity > 0), push `(start_time, velocity)` into a `pending` dict keyed by pitch.
7. For `note_off` (or `note_on` with velocity 0), pop from `pending` and emit a `NoteEvent`.
8. Assign `hand` heuristically:
   - If the MIDI has exactly 2 tracks with notes, treat track 0 as right hand and track 1 as left hand (common convention).
   - If single-track, split by pitch threshold (default: middle C / MIDI 60).
   - Expose a `hand_split_strategy` parameter for overrides.
9. Sort `song.notes` by `start_time`.
10. Compute `song.duration` from the last note's end time.

### MusicXML Loading (`music21`)

1. Parse with `music21.converter.parse()`.
2. Extract `MetronomeMark` objects for tempo changes.
3. Extract `TimeSignature` objects.
4. Iterate `score.parts` — index 0 = right hand, index 1 = left hand.
5. Flatten each part, iterate `.notes` (handles both `Note` and `Chord`).
6. Convert `music21` offset (quarter-note beats) to seconds using the tempo map.
7. Emit `NoteEvent` for each pitch.

### Edge Cases

- **Type 0 MIDI** (single track, multiple channels): split by channel, not track index.
- **Overlapping notes**: same pitch re-triggered before note-off — close the previous note first.
- **Empty tracks**: skip tracks with no note events.
- **Corrupt files**: catch `mido` and `music21` parse errors, raise `SongLoadError` with a clear message.

### New Types

```python
class HandSplitStrategy(Enum):
    BY_TRACK = auto()      # track index determines hand
    BY_PITCH = auto()       # notes >= threshold = right
    BY_CHANNEL = auto()     # MIDI channel determines hand

class SongLoadError(Exception): ...
```

## Testing Plan

| Test | Input | Assertion |
|------|-------|-----------|
| Load simple MIDI | 2-track MIDI, 4 notes each | `len(song.notes) == 8`, hands assigned |
| Load Type 0 MIDI | single-track, 2 channels | hands split by channel |
| Load MusicXML | 2-part score | notes parsed, tempo extracted |
| Overlapping notes | same pitch rapid re-trigger | no negative durations |
| Unsupported format | `.wav` file | raises `SongLoadError` |
| Corrupt MIDI | truncated file | raises `SongLoadError` |

## Dependencies

- `mido` (MIT)
- `music21` (BSD) — lazy import only when MusicXML requested

## Open Questions

- Should we cache parsed songs (pickle/JSON) to avoid re-parsing large files?
- Should we support `.kar` (karaoke MIDI with lyrics)?
