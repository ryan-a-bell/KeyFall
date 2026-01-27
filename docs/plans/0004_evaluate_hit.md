# 0004 — evaluate_hit

## Summary

Compare what the player pressed against what the song expects, grading each note as perfect, good, ok, or miss based on pitch accuracy and timing offset.

## Module

`src/keyfall/evaluator.py`

## Public API

```python
def evaluate_hit(
    expected: NoteEvent,
    played_pitch: int,
    played_time: float,
) -> HitResult: ...

class HitTracker:
    def feed(self, played_pitch: int, played_time: float) -> HitResult | None: ...
    def flush_misses(self, current_time: float) -> list[HitResult]: ...
    def get_stats(self) -> SessionStats: ...
```

## Detailed Design

### Single-Note Evaluation

1. If `played_pitch != expected.pitch` → `MISS`.
2. Compute `offset_ms = (played_time - expected.start_time) * 1000`.
3. Grade by `abs(offset_ms)`:
   - `<= 50ms` → `PERFECT`
   - `<= 100ms` → `GOOD`
   - `<= 200ms` → `OK`
   - `> 200ms` → `MISS`
4. Return `HitResult` with the grade and signed offset (negative = early, positive = late).

### HitTracker (Stateful Evaluator)

The game loop needs a stateful wrapper that matches incoming player events to the nearest expected note:

1. Maintain a sliding window of "pending" expected notes (notes within the OK window of the current playback position).
2. When `feed()` is called with a played note:
   - Find the closest pending note with matching pitch.
   - If found, evaluate and remove from pending. Return the `HitResult`.
   - If no match, return `None` (extra note, ignored or penalized).
3. `flush_misses(current_time)` marks any pending notes whose window has fully passed as `MISS`.
4. `get_stats()` aggregates all results into `SessionStats`.

### Scoring

```
PERFECT = 3 points
GOOD    = 2 points
OK      = 1 point
MISS    = 0 points

Streak: consecutive non-MISS hits. Resets on MISS.
Accuracy: (perfect + good + ok) / total_notes * 100
```

### Chord Handling

When multiple notes start simultaneously (within 50ms):
- All notes in the chord must be hit for the chord to count.
- Grade the chord by the worst individual note grade.
- Partial chord hits: grade hit notes individually, remaining notes become misses after the window passes.

### Configuration

| Setting | Default | Notes |
|---------|---------|-------|
| `PERFECT_WINDOW_MS` | 50 | Configurable per difficulty |
| `GOOD_WINDOW_MS` | 100 | |
| `OK_WINDOW_MS` | 200 | |
| `EXTRA_NOTE_PENALTY` | False | Penalize notes not in the song |

### Difficulty Presets

```python
EASY    = {"PERFECT": 80, "GOOD": 150, "OK": 300}
NORMAL  = {"PERFECT": 50, "GOOD": 100, "OK": 200}
HARD    = {"PERFECT": 30, "GOOD": 60,  "OK": 120}
```

## Testing Plan

| Test | Input | Assertion |
|------|-------|-----------|
| Perfect timing | offset 20ms | PERFECT |
| Good timing | offset 80ms | GOOD |
| OK timing | offset 150ms | OK |
| Late miss | offset 300ms | MISS |
| Wrong pitch | correct time, wrong pitch | MISS |
| Early hit | offset -40ms | PERFECT (negative offset) |
| HitTracker matches nearest note | two pending notes, one played | correct note matched |
| flush_misses | note window passed | MISS generated |
| Chord: all hit | 3-note chord, all played | graded by worst |
| Streak tracking | 5 perfects then miss | max_streak == 5 |

## Dependencies

- Internal: `models.py`, `config.py`
