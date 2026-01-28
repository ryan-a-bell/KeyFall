# 0016 — Piano Synthesis Improvements

## Goal

Six improvements to make KeyFall's piano audio significantly better than competitors (Synthesia, Simply Piano, Flowkey) which all rely on basic SoundFont/sample playback with no physical modeling or expressive control.

---

## Improvement 1: Sympathetic Resonance Simulation

**What competitors do:** Play isolated samples per note. When you hold the sustain pedal or press a chord, each note sounds completely independent.

**What we do:** When a note sounds, scan all currently-held notes and the damper pedal state. For each undamped string whose fundamental or harmonic is close to the sounding note, mix in a quiet sympathetic partial using a short delay + filtered copy of the excitation signal. This is the hallmark of real piano tone — press C3 silently, strike C4 loudly, and C3 rings.

### Design

```python
class SympatheticResonator:
    """Post-process FluidSynth output to add sympathetic string coupling."""

    def __init__(self, held_notes: set[int], sample_rate: int = 44100):
        self.held_notes = held_notes
        self._comb_filters: dict[int, CombFilter] = {}  # pitch -> comb tuned to f0

    def process(self, audio_block: np.ndarray) -> np.ndarray:
        """Add sympathetic energy for each undamped string harmonically related
        to the current excitation spectrum."""
        ...
```

- Use lightweight comb filters (not full convolution) to keep CPU under 5% overhead.
- Only activate for notes sharing a harmonic relationship (frequency ratios within 1% of integer multiples).
- Gain envelope: fast attack (~5ms), slow decay tied to the held note's remaining sustain.

### Why this wins

No consumer piano learning app simulates sympathetic resonance. This single feature makes KeyFall sound like a concert instrument rather than a keyboard patch.

---

## Improvement 2: Per-Note Convolution Reverb with Soundboard IR

**What competitors do:** Apply a single global reverb (usually algorithmic) equally to all notes, or no reverb at all.

**What we do:** Ship a set of impulse responses (IRs) captured from real piano soundboards at different registers (bass, mid, treble). Apply short convolution reverb per-note, blending between IRs based on pitch. This captures the resonant character of the wooden soundboard rather than room reflections.

### Design

```python
class SoundboardReverb:
    """Per-register convolution reverb using piano soundboard IRs."""

    REGISTER_BREAKS = [40, 60, 80]  # MIDI pitch boundaries

    def __init__(self, ir_dir: Path):
        self._irs: list[np.ndarray] = self._load_irs(ir_dir)

    def apply(self, audio: np.ndarray, pitch: int) -> np.ndarray:
        """Convolve with interpolated soundboard IR for this register."""
        ...
```

- Ship 3-4 short IRs (~100ms each, <200KB total as 16-bit WAV).
- Use overlap-add FFT convolution for efficiency.
- Crossfade between adjacent register IRs for smooth transitions.
- Expose wet/dry mix as a user setting (default 15% wet).

### Why this wins

Competitors sound "dry" or use generic hall reverb. Soundboard IRs add the body and warmth specific to a real piano without the muddiness of room reverb.

---

## Improvement 3: Velocity-Curve Modeling with Timbral Morphing

**What competitors do:** Map MIDI velocity linearly to volume. Some use velocity layers (2-4 samples per note), switching abruptly between them.

**What we do:** Implement continuous timbral morphing across the full velocity range using spectral interpolation between FluidSynth's velocity layers plus a dynamic EQ that brightens tone with harder strikes.

### Design

```python
class VelocityShaper:
    """Shape timbre continuously across the velocity range."""

    def __init__(self):
        self._curve = self._steinway_curve()  # pedalboard-measured response curve
        self._brightness_eq = ParametricEQ(
            bands=[(2000, 0.7, 0), (5000, 0.5, 0), (8000, 0.4, 0)]
        )

    def shape(self, velocity: int) -> tuple[int, EQParams]:
        """Return adjusted velocity + EQ parameters for timbral shift."""
        mapped_v = self._curve[velocity]
        brightness = self._brightness_boost(mapped_v)
        return mapped_v, brightness
```

- Model the non-linear velocity-to-loudness curve of a Steinway D (logarithmic low end, compressed high end).
- Apply a 3-band parametric EQ post-FluidSynth: boost 2-8kHz proportionally to velocity for natural brightness on forte passages.
- Support user-selectable curves (Steinway, Bösendorfer, Yamaha C7) as presets.
- Calibrate against the user's MIDI controller via an optional velocity calibration wizard.

### Why this wins

Simply Piano and Synthesia sound flat across dynamics because they only adjust volume. Real pianos have dramatically different timbre at pp vs ff. This makes practice feel like playing an actual instrument.

---

## Improvement 4: Damper Pedal Physical Modeling (Half-Pedaling)

**What competitors do:** Treat sustain pedal as binary on/off (CC64 > 63 = on). All notes sustain equally or not at all.

**What we do:** Model continuous damper pedal position (0-127) with physically-accurate partial damping. At half-pedal positions, high notes sustain longer than low notes (because bass dampers are heavier and engage first), exactly like a real piano.

### Design

```python
class DamperModel:
    """Physical model of continuous damper pedal behavior."""

    def damper_factor(self, pedal_cc: int, pitch: int) -> float:
        """Return sustain multiplier (0.0 = fully damped, 1.0 = undamped).

        At half-pedal (cc ~64), bass strings are partially damped while
        treble strings remain mostly free — matching real piano mechanics.
        """
        normalized = pedal_cc / 127.0
        # Bass dampers engage before treble dampers
        pitch_offset = (pitch - 21) / 87.0  # 0=A0, 1=C8
        engagement = max(0.0, normalized - (1.0 - pitch_offset) * 0.3)
        return min(1.0, engagement / 0.7)
```

- Read CC64 as continuous 0-127 (not just on/off threshold).
- Modulate FluidSynth's note amplitude envelopes based on `damper_factor()`.
- For notes in the top 1.5 octaves (which have no dampers on real pianos), always return 1.0.
- Support una corda (CC67) as a brightness reduction filter (cut 3kHz+ by 3dB).

### Why this wins

Half-pedaling is a core expressive technique that no piano learning app supports. Advanced students will immediately notice the difference, and beginners will develop correct pedaling habits from day one.

---

## Improvement 5: Release Sample Synthesis with Key-Off Velocity

**What competitors do:** Abruptly cut sound on note-off, or apply a fixed release envelope regardless of context.

**What we do:** Synthesize realistic key-release sounds — the mechanical thump of the damper returning to the string, plus the brief resonant "bloom" as the damper makes initial contact. Scale this by key-off velocity (how fast the key was released) and the note's remaining energy.

### Design

```python
class ReleaseSynthesizer:
    """Generate realistic key-release transients."""

    def __init__(self, release_samples_dir: Path):
        self._samples: dict[int, np.ndarray] = {}  # register -> release noise
        self._load_samples(release_samples_dir)

    def trigger_release(
        self, pitch: int, release_velocity: int, note_energy: float
    ) -> np.ndarray:
        """Return a short release transient mixed with remaining note decay.

        Args:
            pitch: MIDI note number
            release_velocity: How fast the key was released (0-127)
            note_energy: Remaining amplitude of the note at release time
        """
        ...
```

- Ship 3 register-grouped release noise samples (~50ms each, <100KB total).
- Scale release transient amplitude by: `release_velocity * note_energy * 0.15`.
- Fast releases (staccato) produce a louder mechanical thump.
- Slow releases (legato) produce almost no transient.
- Crossfade the note's sustain tail into silence over 20-80ms based on damper model state.

### Why this wins

The absence of release sounds is the #1 reason SoundFont pianos sound "synthetic." Adding them transforms the perceived realism at minimal computational cost.

---

## Improvement 6: Adaptive Latency Engine with Predictive Scheduling

**What competitors do:** Use fixed audio buffer sizes, resulting in either high latency (~40-50ms) for stability or audio glitches when the system is under load.

**What we do:** Dynamically adjust FluidSynth's buffer configuration based on measured system performance, and use note-onset prediction from the falling-note display to pre-warm the synthesis pipeline before the player strikes a key.

### Design

```python
class AdaptiveLatencyEngine:
    """Dynamically tune audio latency based on system performance."""

    def __init__(self, target_latency_ms: float = 10.0):
        self.target_latency_ms = target_latency_ms
        self._xrun_count = 0
        self._current_period_size = 128

    def tick(self, frame_time_ms: float) -> None:
        """Called each frame. Adjusts buffer size if xruns detected."""
        if self._xrun_count > 2:
            self._increase_buffer()
            self._xrun_count = 0
        elif self._stable_for(seconds=10):
            self._try_decrease_buffer()

    def predictive_prewarm(self, upcoming_notes: list[NoteEvent], lookahead_ms: float = 50.0):
        """Pre-compute synthesis for notes the player is about to hit.

        Uses the waterfall display's upcoming notes to warm FluidSynth's
        voice allocation before the actual note-on event.
        """
        for note in upcoming_notes:
            if note.time_until_target <= lookahead_ms:
                self._preallocate_voice(note.pitch, note.velocity)
```

- Start with aggressive low-latency settings (period-size=128, periods=2 → ~6ms at 44100Hz).
- Monitor for audio underruns (xruns) and automatically increase buffer if unstable.
- After 10 seconds of stability, attempt to decrease buffer size again.
- **Predictive pre-warming:** Since we know which notes are coming (they're on screen), pre-allocate FluidSynth voices 50ms before expected note-on. This eliminates voice-allocation jitter.
- Expose a "latency priority" setting: "Ultra-Low" / "Balanced" / "Stable".
- Log latency metrics to the progress database for performance analysis.

### Why this wins

Competitors accept whatever latency their audio backend gives them. Our adaptive approach means KeyFall plays at <10ms latency on capable hardware while gracefully degrading on slower systems, and predictive scheduling eliminates the voice-allocation spikes that cause perceptible lag on chord attacks.

---

## Implementation Priority

| # | Improvement | Effort | Impact | Priority |
|---|------------|--------|--------|----------|
| 4 | Damper pedal half-pedaling | Medium | High | P0 — Unique differentiator |
| 3 | Velocity-curve timbral morphing | Low | High | P0 — Most noticeable improvement |
| 5 | Release sample synthesis | Low | High | P1 — Cheap realism boost |
| 6 | Adaptive latency engine | Medium | High | P1 — Core UX quality |
| 1 | Sympathetic resonance | High | Medium | P2 — Advanced realism |
| 2 | Soundboard convolution reverb | Medium | Medium | P2 — Polish layer |

## Dependencies

- `numpy` — audio DSP processing (all improvements)
- `scipy.signal` — FFT convolution for soundboard reverb
- Bundled IR/release WAV samples (~300KB total)
- FluidSynth settings API access (latency engine)
