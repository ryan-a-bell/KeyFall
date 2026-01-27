# 0012 — tempo_scaling (Bonus)

## Summary

Allow the player to slow down or speed up song playback without affecting pitch. Essential for learning difficult passages at a comfortable speed before building up to full tempo.

## Module

`src/keyfall/playback.py` (within `PlaybackEngine`)

## Public API

```python
class PlaybackEngine:
    tempo_scale: float  # 1.0 = normal, 0.5 = half speed, 2.0 = double speed

    def set_tempo_scale(self, scale: float) -> None: ...
```

## Detailed Design

### Time Scaling

The `PlaybackEngine` already has a `tempo_scale` property. Normal mode advances:

```python
self.position += dt * self.tempo_scale
```

This scales everything uniformly — note spacing, duration, and playback speed.

### Audio Pitch Independence

FluidSynth plays notes at their original pitch regardless of when we trigger them. Since we're scheduling individual `note_on`/`note_off` events (not streaming audio), pitch is unaffected by tempo changes. No pitch-shift algorithm needed.

### Note Duration Adjustment

When displaying notes in the waterfall at a different tempo:
- Visual duration scales with tempo: `visual_duration = note.duration / tempo_scale`.
- Hit windows scale proportionally: at 50% speed, the perfect window is effectively 100ms of real time.
- The evaluator should compare against **song time**, not wall-clock time, so windows remain consistent relative to the musical score.

### UI Controls

1. **Slider**: range 0.25x to 2.0x, step 0.05.
2. **Keyboard shortcuts**:
   - `-` / `=` : decrease/increase by 0.05
   - `0` : reset to 1.0x
3. **Display**: show current tempo as percentage and BPM (base BPM × scale).
4. **Preset buttons**: 25%, 50%, 75%, 100%.

### Progressive Practice Mode

An optional auto-scaling feature:
1. Start at a user-defined slow tempo (e.g., 50%).
2. After each successful loop (accuracy > threshold, e.g., 90%), increase by a step (e.g., +5%).
3. Continue until reaching 100% or the player's target.
4. If accuracy drops below threshold, decrease by a step.

```python
@dataclass
class ProgressivePractice:
    start_scale: float = 0.5
    target_scale: float = 1.0
    step: float = 0.05
    accuracy_threshold: float = 90.0
    current_scale: float = 0.5
```

### Metronome

- Optional click track that follows the scaled tempo.
- Use MIDI channel 9 (percussion), note 37 (side stick) or 76 (hi woodblock).
- Accent beat 1 with higher velocity.
- Toggle with `M` key.

## Testing Plan

| Test | Assertion |
|------|-----------|
| tempo_scale=0.5 advances at half speed | position after 1s == 0.5 |
| tempo_scale=2.0 advances at double speed | position after 1s == 2.0 |
| Clamped to [0.25, 2.0] | values outside range rejected |
| Progressive practice increases scale | scale goes up after good loop |
| Progressive practice decreases on failure | scale goes down after bad loop |
| Reset to 1.0 | `tempo_scale == 1.0` |

## Dependencies

- Internal: `playback.py`, `audio.py`, `config.py`
