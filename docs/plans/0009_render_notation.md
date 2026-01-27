# 0009 — render_notation

## Summary

Render a simplified traditional sheet music view alongside or instead of the waterfall. Highlight the current playback position and color notes by hit/miss status.

## Module

`src/keyfall/notation.py`

## Public API

```python
def render_notation(
    surface: pygame.Surface,
    song: Song,
    playback_position: float,
    x: int = 0,
    y: int = 0,
    width: int = 400,
    height: int = 200,
) -> None: ...
```

## Detailed Design

### Scope

This is a **simplified** staff view — not a full music engraving engine. Goal: help players connect falling notes to traditional notation. Full engraving is out of scope (use LilyPond/MuseScore for that).

### Layout

1. Draw a grand staff (treble + bass clef) with 5 lines each.
2. Notes scroll **left to right** — the current position is a vertical cursor line at ~30% from the left edge.
3. Future notes appear to the right, past notes scroll off the left.

### Note Rendering

1. Map MIDI pitch to staff position:
   - Treble clef: middle C (60) sits on the first ledger line below.
   - Bass clef: middle C sits on the first ledger line above.
2. Draw note heads as filled/open circles based on duration:
   - Quarter note and shorter: filled.
   - Half note and longer: open.
3. Draw stems (up for notes below the middle line, down for above).
4. Skip beaming, ties, and articulations for v1.
5. Color notes:
   - Default: white
   - Perfect hit: green
   - Good hit: yellow
   - Miss: red
   - Upcoming: dim gray

### Synchronization

- Convert `playback_position` (seconds) to beat position using the tempo map.
- Map beat position to x-coordinate: `x_offset = (beat - current_beat) * pixels_per_beat`.

### Clef and Key Signature

- Draw treble and bass clef glyphs (pre-rendered PNG sprites or simple pygame drawing).
- Key signature: place sharps/flats at the start of each system. Detect from the song's key (if available from MusicXML) or default to C major.

### View Modes

1. **Overlay**: small notation panel above the waterfall.
2. **Split**: waterfall on left, notation on right (50/50 split).
3. **Notation only**: full-screen staff view (for more traditional learners).

### Phased Implementation

| Phase | Features |
|-------|----------|
| v0.1 | Staff lines, note heads at correct positions, scrolling cursor |
| v0.2 | Stems, ledger lines, clef sprites |
| v0.3 | Hit coloring, key/time signature display |
| v1.0 | Rests, bar lines, measure numbers |

## Testing Plan

| Test | Assertion |
|------|-----------|
| Staff lines render at correct y positions | 5 lines per staff, correct spacing |
| MIDI 60 (C4) maps to first ledger line below treble | correct y |
| MIDI 48 (C3) maps to correct bass clef position | correct y |
| Note at current position renders at cursor x | x within tolerance |
| Future note renders to the right of cursor | x > cursor_x |

## Dependencies

- `pygame` (LGPL)
- Internal: `models.py`, `renderer/colors.py`

## Open Questions

- Should we use a font like Bravura (SMuFL) for music symbols instead of drawing them?
- Should this be a separate optional dependency for users who don't want notation?
