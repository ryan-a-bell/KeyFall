# 0005 — wait_mode_playback

## Summary

Implement "wait for correct note" mode — the song pauses until the player plays the right note(s), then advances. This is the core practice feature.

## Module

`src/keyfall/playback.py` (within `PlaybackEngine`)

## Public API

```python
class PlaybackEngine:
    wait_mode: bool
    active_hand: Hand
    tempo_scale: float
    paused: bool

    def update(self, dt: float, pressed_pitches: set[int]) -> list[NoteEvent]: ...
```

## Detailed Design

### Normal Mode

1. Each frame, advance `position += dt * tempo_scale`.
2. Collect all notes whose `start_time <= position` and haven't been emitted yet.
3. Return them as "newly active" — the audio engine plays them, the evaluator starts tracking them.

### Wait Mode

1. Do **not** advance `position` based on wall-clock time.
2. Look at the next note(s) in sequence (simultaneous notes grouped within 50ms tolerance).
3. Determine which notes the player is responsible for based on `active_hand`:
   - `BOTH` → player must hit all notes in the group.
   - `LEFT` or `RIGHT` → player only responsible for notes matching that hand; the engine auto-plays the other hand.
4. Each frame, compare `pressed_pitches` (currently held keys) against the required set.
5. When `required.issubset(pressed_pitches)`:
   - Advance `note_index` past the group.
   - Set `position` to the end of the group.
   - Return the group as newly active.
6. The waterfall freezes in place until the player succeeds — no notes scroll off screen.

### Auto-Play for Inactive Hand

When `active_hand` is LEFT or RIGHT, the opposite hand's notes should:
1. Play audio automatically at their correct time (relative to the player's advancement).
2. Render in a dimmed color on the waterfall.
3. Not count toward scoring.

### Pause / Resume

- `paused = True` freezes everything (both normal and wait mode).
- Toggled by spacebar or a UI button.
- On resume, reset the frame `dt` accumulator to avoid a time jump.

### Loop Integration

Wait mode works with section looping (plan 0010):
1. When the player finishes the last note in a section, reset `note_index` and `position` to the section start.
2. Increment a loop counter for progress tracking.

### State Machine

```
IDLE → PLAYING (normal) → FINISHED
IDLE → WAITING (wait mode) → FINISHED
Any  → PAUSED → (previous state)
```

## Testing Plan

| Test | Assertion |
|------|-----------|
| Normal mode advances position | `position` increases each frame |
| Wait mode does not advance without input | `position` unchanged |
| Correct note advances wait mode | `note_index` incremented |
| Wrong note does not advance | `note_index` unchanged |
| Chord requires all notes | partial press doesn't advance |
| Active hand filters responsibility | only matching hand notes required |
| Pause freezes position | `position` unchanged while paused |
| Finished flag set at end of song | `engine.finished == True` |

## Dependencies

- Internal: `models.py`, `config.py`
