# 0002 — render_waterfall

## Summary

Draw a falling-note waterfall visualization where colored rectangular bars descend toward a virtual piano keyboard. This is the primary gameplay view and the visual signature of the app.

## Module

`src/keyfall/renderer/waterfall.py`

## Public API

```python
def render_waterfall(
    surface: pygame.Surface,
    song: Song,
    playback_position: float,
    look_ahead: float = 3.0,
) -> None: ...
```

## Detailed Design

### Coordinate System

- The keyboard sits at `KEYBOARD_Y` (bottom of the waterfall area).
- Notes fall **downward**: a note 3 seconds in the future appears at `y=0`, a note at the current position appears at `y=KEYBOARD_Y`.
- `pixels_per_sec = KEYBOARD_Y / look_ahead`.

### Note Bar Rendering

1. For each `NoteEvent` in the song:
   - Compute `dt = note.start_time - playback_position`.
   - Skip if `dt > look_ahead` (not visible yet) or `dt + note.duration < -0.5` (already past).
   - `y_bottom = KEYBOARD_Y - dt * pixels_per_sec`
   - `bar_height = note.duration * pixels_per_sec` (min 6px for very short notes).
   - `y_top = y_bottom - bar_height`
   - `x` and `width` come from `key_x_position(note.pitch)` and `key_width(note.pitch)`.
2. Color by hand: blue for right, orange for left (from `colors.py`).
3. Draw with `pygame.draw.rect(..., border_radius=3)`.

### Performance Optimizations

- **Visible window culling**: only iterate notes within `[position - 0.5, position + look_ahead]`. Use binary search (`bisect`) on the sorted notes list instead of scanning all notes every frame.
- **Surface caching**: for very dense passages, consider pre-rendering note columns to an offscreen surface and scrolling it, only re-rendering when notes enter/leave the window.
- **Batch rendering**: group rects by color and use `pygame.draw.rect` in batches (pygame doesn't have true batch draw, but grouping reduces Python overhead from color switching).

### Visual Polish (Future)

- Glow effect on notes crossing the hit line.
- Fade-out for notes that have passed.
- Color flash on hit (green for perfect, yellow for good, red for miss).
- Particle burst on perfect hits.

### Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `look_ahead` | `3.0` s | How far ahead notes are visible |
| `NOTE_FALL_SPEED` | `300` px/s | (Derived from look_ahead; kept for reference) |
| `min_bar_height` | `6` px | Minimum height for very short notes |
| `border_radius` | `3` px | Rounded corners on note bars |

## Testing Plan

| Test | Assertion |
|------|-----------|
| Note at `position + 1s` renders within visible area | `0 < y_top < KEYBOARD_Y` |
| Note far in future (`+10s`) is culled | not drawn |
| Note in the past (`-2s`) is culled | not drawn |
| Very short note has minimum height | `bar_height >= 6` |
| Left/right hand notes use correct colors | color matches hand enum |

## Dependencies

- `pygame` (LGPL)
- Internal: `models.py`, `config.py`, `renderer/keyboard.py`, `renderer/colors.py`
