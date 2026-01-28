# 0017 — AI Features

## Summary

Six AI-powered features that transform KeyFall from a note-matching game into an intelligent piano tutor. No competitor integrates AI at the engine level — they use it only for basic pitch recognition.

---

## Feature 1: Adaptive Difficulty Engine

### Problem

Players manually select tempo, hand mode, and section. If a passage is too hard they get frustrated; too easy and they plateau. No competitor adjusts difficulty in real time.

### Design

```python
class AdaptiveDifficulty:
    def __init__(self, history: list[HitResult]):
        self.error_model = ErrorModel()  # tracks per-pitch, per-interval error rates
        self.tempo_controller = TempoController()

    def update(self, result: HitResult) -> DifficultyAdjustment:
        """After each hit/miss, return adjustments to apply."""
        ...

@dataclass
class DifficultyAdjustment:
    tempo_scale: float          # 0.5 - 1.5
    isolate_hand: Hand | None   # suggest single-hand practice
    loop_bars: tuple[int, int] | None  # suggest section to repeat
    simplify: bool              # drop ornaments / reduce voicing
```

- Track rolling accuracy over last 20 notes per hand.
- If accuracy < 70%, slow tempo by 5% and suggest hand isolation.
- If accuracy > 95% for 2 consecutive passes, increase tempo by 5%.
- Identify "trouble spots" — 4+ bar regions where accuracy drops below the session average by >15%.
- Use exponential moving average to avoid oscillating adjustments.

### Dependencies

- `evaluator.py` — HitResult stream
- `playback.py` — tempo control API
- `progress.py` — historical session data

---

## Feature 2: Practice Plan Generation

### Problem

Students don't know what to practice or in what order. Teachers create structured plans; apps don't. Simply opening a song and playing start-to-finish is inefficient.

### Design

```python
class PracticePlanner:
    def generate_plan(
        self, song: Song, history: list[dict], target_accuracy: float = 0.95
    ) -> PracticePlan: ...

@dataclass
class PracticeStep:
    bar_range: tuple[int, int]
    hand: Hand
    tempo_pct: int              # percentage of original tempo
    repetitions: int
    focus: str                  # human-readable goal

@dataclass
class PracticePlan:
    song_title: str
    steps: list[PracticeStep]
    estimated_sessions: int
    current_mastery_pct: float
```

- Analyze progress history to find weakest sections (highest miss rate, worst timing).
- Order steps: weakest sections first, hands separate before hands together.
- Start each section at the tempo where accuracy was last > 80%, ramp up 5% per successful pass.
- Generate human-readable focus notes ("smooth out the LH octave leap in bars 12-14").
- Cap plan at 6-8 steps per session to avoid cognitive overload.

### Implementation — `src/keyfall/ai/practice_planner.py`

---

## Feature 3: Real-Time Technique Feedback

### Problem

Hit/miss grading tells you *what* you got wrong but not *why*. A teacher would say "your left hand is rushing" or "too heavy in this quiet section." No app provides this.

### Design

```python
class TechniqueFeedback:
    def analyze(self, results: list[HitResult]) -> list[TechniqueInsight]: ...

@dataclass
class TechniqueInsight:
    category: str       # "timing", "dynamics", "articulation", "evenness"
    severity: float     # 0.0 - 1.0
    message: str        # "Left hand consistently 30ms early in bars 8-12"
    bar_range: tuple[int, int] | None
    hand: Hand | None
```

Detectors:
1. **Timing drift** — Detect systematic early/late tendency per hand using linear regression on timing offsets.
2. **Dynamic mismatch** — Compare played velocity to expected velocity. Flag passages where the player is too loud in piano sections or too soft in forte.
3. **Evenness** — Measure velocity variance in passages that should be uniform (runs, scales). High variance = uneven fingers.
4. **Articulation** — Compare played note durations to expected. Staccato played as legato, or vice versa.
5. **Rush/drag** — Detect accelerando/ritardando tendencies by windowed tempo estimation.

### Implementation — `src/keyfall/ai/technique_feedback.py`

---

## Feature 4: Intelligent Fingering Suggestion

### Problem

Correct fingering is essential but most apps show nothing, and published fingerings assume average-sized adult hands. A beginner with small hands needs different fingerings.

### Design

```python
class FingeringSuggester:
    def suggest(
        self, notes: list[NoteEvent], hand: Hand, hand_span: int = 9
    ) -> list[int]:
        """Return finger numbers (1-5) for each note, minimizing repositioning."""
        ...
```

- Model as a shortest-path problem: each note has 5 possible fingers, transitions have costs based on interval + finger pair ergonomics.
- Use dynamic programming (Viterbi-like) to find the minimum-cost fingering path.
- Cost model penalizes: thumb-under for intervals > 5 semitones, 4-5 finger pairs, hand repositioning, same finger consecutively.
- `hand_span` parameter (in semitones) adjusts for hand size. Default 9 (octave reach). Calibrate by asking the user to stretch on their keyboard.

### Dependencies

- `models.py` — NoteEvent sequence
- No external ML libraries needed — this is pure algorithmic optimization

---

## Feature 5: Audio-Based Assessment (No MIDI Required)

### Problem

MIDI keyboards cost $50-200+. Simply Piano and Flowkey offer mic-based recognition but it's unreliable. Removing the MIDI requirement expands the addressable market to anyone with an acoustic piano and a laptop.

### Design

```python
class AudioAssessor:
    def __init__(self, sample_rate: int = 44100):
        self.onset_detector = OnsetDetector()
        self.pitch_estimator = PolyphonicPitchEstimator()
        self.velocity_estimator = VelocityEstimator()

    def process_frame(self, audio: np.ndarray) -> list[DetectedNote]: ...

@dataclass
class DetectedNote:
    pitch: int          # MIDI note number
    onset_time: float
    velocity: int       # estimated from amplitude
    confidence: float   # 0.0 - 1.0
```

- Use a pre-trained polyphonic pitch detection model (e.g., basic-pitch from Spotify, MIT license).
- Onset detection via spectral flux + peak picking.
- Velocity estimation from onset amplitude envelope.
- Confidence threshold to avoid false positives (default 0.7).
- Feed DetectedNote into the same evaluator pipeline as MIDI input.

### Dependencies

- `numpy`, `scipy` — DSP
- `basic-pitch` or similar lightweight model — polyphonic pitch estimation
- Optional: `sounddevice` for cross-platform mic input

---

## Feature 6: Sight-Reading Difficulty Estimation

### Problem

When importing a MIDI/MusicXML file, users have no idea if it's appropriate for their level. Piano Marvel has curated difficulty ratings but only for their library. No app auto-rates arbitrary files.

### Design

```python
class DifficultyEstimator:
    def estimate(self, song: Song) -> DifficultyReport: ...

@dataclass
class DifficultyReport:
    overall_level: int          # 1-18 (aligned with RCM/ABRSM grades)
    overall_label: str          # "Beginner", "Intermediate", etc.
    factors: dict[str, float]   # individual scores per dimension
    hardest_bars: list[int]     # bar numbers with highest difficulty
    description: str            # human-readable summary
```

Scoring dimensions (each 0.0-1.0):
1. **Note density** — notes per second per hand
2. **Pitch range** — span in semitones, use of extreme registers
3. **Hand independence** — rhythmic divergence between hands (cross-correlation)
4. **Interval complexity** — frequency of leaps > octave, awkward intervals
5. **Rhythmic complexity** — syncopation, polyrhythm, tuplets, ties across barlines
6. **Tempo** — raw BPM adjusted for note subdivision
7. **Key complexity** — number of accidentals, key changes
8. **Chord density** — simultaneous notes per beat

Weighted sum mapped to 1-18 scale via calibrated breakpoints.

### Implementation — `src/keyfall/ai/difficulty.py`

---

## Implementation Priority

| # | Feature | Effort | Impact | Status |
|---|---------|--------|--------|--------|
| 2 | Practice plan generation | Medium | High | Implementing now |
| 3 | Technique feedback | Medium | High | Implementing now |
| 6 | Difficulty estimation | Low | High | Implementing now |
| 1 | Adaptive difficulty | Medium | High | Planned |
| 4 | Fingering suggestion | Medium | Medium | Planned |
| 5 | Audio assessment | High | High | Planned |

## Dependencies

- `numpy` — statistical analysis (technique feedback, difficulty estimation)
- `scipy.stats` — linear regression for timing drift detection
- `basic-pitch` — polyphonic pitch detection (feature 5 only, deferred)
- Existing modules: `models.py`, `evaluator.py`, `progress.py`, `song_loader.py`
