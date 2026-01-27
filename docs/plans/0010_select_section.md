# 0010 — select_section

## Summary

Let the player select and loop a specific section of a song (by bar range) for focused practice on difficult passages.

## Module

`src/keyfall/playback.py`

## Public API

```python
def select_section(
    song: Song,
    start_bar: int,
    end_bar: int,
    beats_per_bar: float = 4.0,
) -> Song: ...
```

## Detailed Design

### Bar-to-Time Conversion

1. Use the song's `time_signatures` list to determine beats per bar at any point.
2. If no time signatures are present, default to `beats_per_bar` (4/4).
3. Walk through time signatures to compute the start/end time in seconds:
   ```
   start_time = sum of (bars * beats_per_bar * seconds_per_beat) for each time sig region
   ```
4. For v1, use a simplified calculation assuming constant time signature (configurable).

### Section Extraction

1. Filter `song.notes` to those with `start_time` in `[start_time, end_time)`.
2. Shift all note start times so the section begins at `t=0`:
   ```python
   note.start_time -= start_time
   ```
3. Copy tempo changes and time signatures that fall within the range.
4. Recalculate `section.duration`.

### Loop Mode

The `PlaybackEngine` manages looping:

1. New property: `loop_enabled: bool = False`
2. New property: `loop_count: int = 0`
3. When `finished` and `loop_enabled`:
   - Reset `note_index = 0` and `position = 0.0`.
   - Increment `loop_count`.
   - Optionally increase `tempo_scale` slightly each loop (progressive practice).

### UI for Section Selection

Two approaches:

**Quick select:**
- Keyboard shortcuts: `[` sets loop start at current bar, `]` sets loop end.
- Display loop markers on the waterfall as horizontal lines.

**Song browser:**
- Before starting, show a bar-range selector (two number inputs or a range slider).
- Display a minimap of the song (tiny waterfall overview) with draggable handles.

### Bookmark System

Allow saving named sections for later:

```python
@dataclass
class Bookmark:
    name: str
    start_bar: int
    end_bar: int
```

Store bookmarks in the progress database, keyed by song hash.

## Testing Plan

| Test | Assertion |
|------|-----------|
| Select bars 2-2 of a 3-bar song | only notes in bar 2 |
| Note times are shifted to start at 0 | first note `start_time >= 0` |
| Select beyond song end | clamp to last bar |
| start_bar > end_bar | raise ValueError |
| Empty section (no notes in range) | returns Song with empty notes |
| Loop resets note_index | `note_index == 0` after loop |

## Dependencies

- Internal: `models.py`
