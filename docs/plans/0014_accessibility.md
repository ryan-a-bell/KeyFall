# 0014 — accessibility (Bonus)

## Summary

Ensure KeyFall is usable by players with visual impairments, color vision deficiency, and motor differences. Accessibility should be a first-class concern, not an afterthought.

## Module

`src/keyfall/accessibility.py` (new)
Touches: `renderer/colors.py`, `config.py`, `app.py`

## Public API

```python
class AccessibilitySettings:
    color_palette: ColorPalette
    high_contrast: bool
    note_labels: NoteLabelMode
    screen_reader: bool
    large_text: bool
    input_latency_offset_ms: float

def apply_accessibility(settings: AccessibilitySettings) -> None: ...
```

## Detailed Design

### Color Vision Deficiency (CVD)

The default palette (blue/orange) is already deuteranopia-friendly. Add additional palettes:

```python
class ColorPalette(Enum):
    DEFAULT = auto()        # Blue / Orange
    PROTANOPIA = auto()     # Blue / Yellow
    TRITANOPIA = auto()     # Red / Cyan
    HIGH_CONTRAST = auto()  # White / Bright Yellow on black
    MONOCHROME = auto()     # Pattern-based differentiation
```

For monochrome mode, differentiate hands using patterns instead of colors:
- Right hand: solid fill
- Left hand: diagonal stripes (hatching)

Implementation: draw note bars to a small surface, apply a stripe mask via `pygame.Surface.blit` with `BLEND_MULT`.

### Note Labels

Display text on each falling note bar to aid identification:

```python
class NoteLabelMode(Enum):
    NONE = auto()
    NOTE_NAME = auto()      # "C4", "F#3"
    FINGER_NUMBER = auto()  # "1", "2", "3", "4", "5"
    SOLFEGE = auto()        # "Do", "Re", "Mi"
    MIDI_NUMBER = auto()    # "60", "65"
```

Render labels centered on each note bar. Use a small font that scales with bar width. Only show labels when the bar is tall enough (skip for very short notes).

### High Contrast Mode

- Background: pure black `(0, 0, 0)`.
- Note bars: bright white outlines + fill.
- Keyboard: stark white/black with thick borders.
- Text: white on black, larger font size.
- Hit line: thick bright line instead of subtle indicator.

### Screen Reader Support

Limited but useful announcements via system TTS:

1. Use `subprocess` to call platform TTS:
   - Linux: `espeak` or `spd-say`
   - macOS: `say`
   - Windows: PowerShell `Add-Type -AssemblyName System.Speech`
2. Announce:
   - Menu navigation ("Song selected: Für Elise")
   - Practice mode changes ("Wait mode enabled")
   - Session results ("Accuracy: 85 percent, 12 perfects")
3. Keep announcements brief to avoid overwhelming.

```python
def speak(text: str) -> None:
    """Fire-and-forget TTS announcement."""
    if sys.platform == "linux":
        subprocess.Popen(["espeak", "-s", "160", text],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif sys.platform == "darwin":
        subprocess.Popen(["say", text])
    elif sys.platform == "win32":
        # Use SAPI via PowerShell
        subprocess.Popen(["powershell", "-Command",
                          f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text}')"])
```

### Large Text Mode

- Scale all UI text by 1.5x.
- Increase HUD font size from 20 to 30.
- Widen note label fonts.
- Ensure no text is clipped by its container.

### Input Latency Compensation

Different setups (Bluetooth keyboards, USB audio interfaces) introduce varying latency:
1. Provide a calibration screen: "Press any key when you hear the click."
2. Measure the offset between the expected time and the actual input time over 10 taps.
3. Average the offset and store as `input_latency_offset_ms`.
4. Apply this offset in the evaluator: `adjusted_time = played_time - offset`.

### Keyboard Navigation

All UI screens must be fully navigable without a mouse:
- Arrow keys: move between menu items.
- Enter: select.
- Escape: back.
- Tab: cycle between UI sections.

### Settings Persistence

Store accessibility settings in `~/.keyfall/settings.json`:

```json
{
  "accessibility": {
    "color_palette": "DEFAULT",
    "high_contrast": false,
    "note_labels": "NOTE_NAME",
    "screen_reader": false,
    "large_text": false,
    "input_latency_offset_ms": 0.0
  }
}
```

Load on startup, apply before first render.

## Testing Plan

| Test | Assertion |
|------|-----------|
| Each palette has distinct L/R colors | color values differ |
| Monochrome mode uses patterns | stripe mask applied |
| Note labels render on bars | text surface created |
| High contrast bg is pure black | `(0,0,0)` |
| speak() doesn't block | function returns immediately |
| Latency offset adjusts evaluation | shifted time used |
| Settings round-trip through JSON | save then load matches |
| Keyboard nav reaches all menu items | focus cycles correctly |

## Dependencies

- `pygame` (LGPL)
- System TTS (optional, graceful fallback to no-op)
- `json` (stdlib)

## Open Questions

- Should we integrate with platform accessibility APIs (AT-SPI on Linux, NSAccessibility on macOS)?
- Should we support custom user-defined color palettes via JSON?
- Should haptic feedback (controller vibration) be an option for timing cues?
