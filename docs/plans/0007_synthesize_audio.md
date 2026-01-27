# 0007 — synthesize_audio

## Summary

Play audio for the song's backing track and the player's own key presses using FluidSynth with SoundFont (.sf2) files. Must handle mixing multiple channels with low latency.

## Module

`src/keyfall/audio.py`

## Public API

```python
class AudioEngine:
    def __init__(self, soundfont_path: str | Path | None = None) -> None: ...
    def load_soundfont(self, path: str | Path) -> None: ...
    def note_on(self, pitch: int, velocity: int = 80, channel: int = 0) -> None: ...
    def note_off(self, pitch: int, channel: int = 0) -> None: ...
    def play_note_event(self, note: NoteEvent, channel: int = 0) -> None: ...
    def all_notes_off(self) -> None: ...
    def set_instrument(self, channel: int, program: int) -> None: ...
    def shutdown(self) -> None: ...
```

## Detailed Design

### FluidSynth Initialization

1. Create a `fluidsynth.Synth(gain=0.8)` instance.
2. Select audio driver based on platform:
   - Linux: `alsa` or `pulseaudio`
   - macOS: `coreaudio`
   - Windows: `dsound` or `wasapi`
   - Auto-detect via `sys.platform`.
3. Load a default SoundFont. Bundle a small GM SoundFont (e.g., FluidR3Mono_GM.sf3, ~15MB, MIT-compatible) or prompt the user to provide one.
4. Select program 0 (Acoustic Grand Piano) on channel 0.

### Channel Layout

| Channel | Purpose |
|---------|---------|
| 0 | Player's live input |
| 1 | Auto-play: right hand |
| 2 | Auto-play: left hand |
| 3 | Metronome click (percussion, channel 9 in GM) |

### Real-Time Note Playback

- `note_on()` / `note_off()` called directly from the game loop when:
  - Player presses/releases a key (channel 0).
  - Auto-play notes trigger in wait mode (channels 1/2).
- FluidSynth handles mixing and audio output internally via its own audio thread.

### Scheduled Playback

For normal (non-wait) mode, notes need to fire at exact song times:
1. The `PlaybackEngine` emits "newly active" notes each frame.
2. The game loop calls `audio.play_note_event(note, channel)` for each.
3. Schedule `note_off` after `note.duration` seconds using a simple timer list:
   ```python
   self._pending_offs: list[tuple[float, int, int]]  # (off_time, pitch, channel)
   ```
4. Each frame, flush any pending offs whose time has passed.

### Volume Control

- Master volume via FluidSynth gain.
- Per-channel volume via MIDI CC7.
- Expose simple API: `set_volume(channel, 0.0..1.0)`.
- Auto-play hands should be quieter than the player's input (default: 60% volume).

### Latency

- FluidSynth's internal buffer size determines latency. Default ~46ms (1024 samples at 22050 Hz).
- For better latency: set `audio.period-size=256` and `audio.periods=2` via FluidSynth settings.
- Target: < 20ms perceived latency.

### Bundled SoundFont

- Ship with a small, permissively-licensed GM SoundFont.
- Candidates: `FluidR3Mono_GM.sf3` (MIT), `MuseScore_General.sf3` (MIT).
- Allow user to load custom SoundFonts via settings.

## Testing Plan

| Test | Assertion |
|------|-----------|
| Init without soundfont | no crash, silent output |
| Load soundfont | `_sfid` is not None |
| note_on / note_off | no exceptions |
| all_notes_off | silences all channels |
| shutdown | clean cleanup, no segfault |
| Platform detection | correct driver string for OS |

## Dependencies

- `pyfluidsynth` (LGPL)
- A GM SoundFont file (MIT/public domain)

## Open Questions

- Should we support `pygame.mixer` as a lightweight fallback for users who can't install FluidSynth?
- Should we record the player's performance as a MIDI file for playback review?
