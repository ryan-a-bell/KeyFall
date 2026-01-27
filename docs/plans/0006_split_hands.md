# 0006 — split_hands

## Summary

Separate a song into left-hand and right-hand parts so the player can practice each hand independently while the engine auto-plays the other.

## Module

`src/keyfall/playback.py`

## Public API

```python
def split_hands(song: Song) -> tuple[Song, Song]: ...
```

## Detailed Design

### Primary Strategy: By Track / Part

Most well-structured MIDI files and all MusicXML files assign hands to separate tracks or parts:
- Track/part 0 → right hand
- Track/part 1 → left hand

The `song_loader` already tags each `NoteEvent.hand` during parsing. `split_hands()` simply filters:

```python
left_notes  = [n for n in song.notes if n.hand == Hand.LEFT]
right_notes = [n for n in song.notes if n.hand == Hand.RIGHT]
```

### Fallback Strategy: By Pitch

For single-track MIDI files where hand assignment is ambiguous:
1. Default split point: MIDI 60 (middle C).
2. Notes with `pitch < split_point` → left hand.
3. Notes with `pitch >= split_point` → right hand.
4. Allow user to adjust the split point via a slider in the UI.

### Fallback Strategy: By Channel

Type 0 MIDI files sometimes use channels to distinguish hands:
- Channel 0 → right hand
- Channel 1 → left hand

### Result

Each returned `Song` contains:
- Only the notes for that hand.
- The full `tempo_changes` and `time_signatures` (shared).
- Recalculated `duration` based on the last note in that hand.

### UI Integration

The practice screen offers three modes:
1. **Both hands** — default, play everything.
2. **Right hand only** — left hand auto-plays (dimmed in waterfall).
3. **Left hand only** — right hand auto-plays (dimmed in waterfall).

A toggle (keyboard shortcut: `1` / `2` / `3` or buttons) switches between modes. The `PlaybackEngine.active_hand` property controls which notes the player is responsible for.

## Testing Plan

| Test | Assertion |
|------|-----------|
| Song with tagged hands splits correctly | left/right note counts match |
| Single-track splits by pitch at C4 | notes below 60 in left |
| Adjustable split point | changing threshold re-sorts notes |
| Empty hand returns empty Song | no crash, `duration == 0` |
| Tempo/time sig copied to both | both songs have identical metadata |

## Dependencies

- Internal: `models.py`
