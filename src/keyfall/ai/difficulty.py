"""Sight-reading difficulty estimation for arbitrary MIDI/MusicXML files."""

from __future__ import annotations

from dataclasses import dataclass, field

from keyfall.models import Hand, Song


@dataclass
class DifficultyReport:
    """Difficulty analysis of a song."""

    overall_level: int  # 1-18 (aligned with RCM/ABRSM grade scale)
    overall_label: str  # "Beginner", "Early Intermediate", etc.
    factors: dict[str, float] = field(default_factory=dict)  # dimension -> 0.0-1.0
    hardest_bars: list[int] = field(default_factory=list)
    description: str = ""


# Level labels aligned with standard grading
_LEVEL_LABELS = {
    (1, 3): "Beginner",
    (4, 6): "Early Intermediate",
    (7, 9): "Intermediate",
    (10, 12): "Late Intermediate",
    (13, 15): "Advanced",
    (16, 18): "Expert",
}


def _label_for_level(level: int) -> str:
    for (lo, hi), label in _LEVEL_LABELS.items():
        if lo <= level <= hi:
            return label
    return "Expert"


def _note_density_score(song: Song) -> float:
    """Score based on notes per second per hand (0.0 - 1.0).

    < 1 nps = 0.0, > 8 nps = 1.0, linear in between.
    """
    if not song.notes or song.duration <= 0:
        return 0.0

    # Compute per-hand density using the denser hand
    lh = [n for n in song.notes if n.hand in (Hand.LEFT, Hand.BOTH)]
    rh = [n for n in song.notes if n.hand in (Hand.RIGHT, Hand.BOTH)]

    lh_density = len(lh) / song.duration if lh else 0.0
    rh_density = len(rh) / song.duration if rh else 0.0
    max_density = max(lh_density, rh_density)

    return min(1.0, max(0.0, (max_density - 1.0) / 7.0))


def _pitch_range_score(song: Song) -> float:
    """Score based on total pitch span used (0.0 - 1.0).

    < 1 octave = 0.0, > 5 octaves = 1.0.
    """
    if not song.notes:
        return 0.0

    pitches = [n.pitch for n in song.notes]
    span = max(pitches) - min(pitches)

    return min(1.0, max(0.0, (span - 12) / 48.0))


def _hand_independence_score(song: Song) -> float:
    """Score based on rhythmic divergence between hands (0.0 - 1.0).

    Measures how often both hands play simultaneously vs alternating.
    High simultaneous + different rhythms = high independence requirement.
    """
    if not song.notes:
        return 0.0

    lh_times = set()
    rh_times = set()

    # Quantize to 50ms buckets for comparison
    for n in song.notes:
        bucket = round(n.start_time / 0.05)
        if n.hand == Hand.LEFT:
            lh_times.add(bucket)
        elif n.hand == Hand.RIGHT:
            rh_times.add(bucket)
        else:
            lh_times.add(bucket)
            rh_times.add(bucket)

    if not lh_times or not rh_times:
        return 0.0

    # Overlap: buckets where both hands are active
    overlap = len(lh_times & rh_times)
    # Non-overlap: buckets unique to one hand
    total = len(lh_times | rh_times)

    if total == 0:
        return 0.0

    # High overlap with different total counts = independent parts
    overlap_ratio = overlap / total
    size_ratio = min(len(lh_times), len(rh_times)) / max(len(lh_times), len(rh_times))

    # Both hands active and roughly equal activity = independence
    independence = overlap_ratio * size_ratio

    return min(1.0, independence * 2.0)


def _interval_complexity_score(song: Song) -> float:
    """Score based on frequency of large leaps (0.0 - 1.0).

    Measures consecutive-note intervals > octave within each hand.
    """
    if len(song.notes) < 2:
        return 0.0

    # Sort notes per hand by time
    by_hand: dict[Hand, list[int]] = {Hand.LEFT: [], Hand.RIGHT: []}
    for n in sorted(song.notes, key=lambda x: x.start_time):
        if n.hand in by_hand:
            by_hand[n.hand].append(n.pitch)
        else:
            by_hand[Hand.LEFT].append(n.pitch)
            by_hand[Hand.RIGHT].append(n.pitch)

    large_leaps = 0
    total_intervals = 0

    for pitches in by_hand.values():
        for i in range(1, len(pitches)):
            interval = abs(pitches[i] - pitches[i - 1])
            total_intervals += 1
            if interval > 12:
                large_leaps += 1

    if total_intervals == 0:
        return 0.0

    leap_ratio = large_leaps / total_intervals
    return min(1.0, leap_ratio * 5.0)  # 20% large leaps = max score


def _rhythmic_complexity_score(song: Song) -> float:
    """Score based on variety of note durations and syncopation (0.0 - 1.0).

    More unique duration values and off-beat starts = higher complexity.
    """
    if not song.notes:
        return 0.0

    durations = [round(n.duration, 3) for n in song.notes]
    unique_durations = len(set(durations))

    # Variety score: many different durations = complex rhythm
    variety = min(1.0, unique_durations / 12.0)

    # Syncopation: notes starting on off-beats
    # Assume quarter note = beat_duration from tempo
    bpm = 120.0
    if song.tempo_changes:
        bpm = song.tempo_changes[0].bpm
    beat_duration = 60.0 / bpm

    offbeat_count = 0
    for n in song.notes:
        beat_position = (n.start_time % beat_duration) / beat_duration
        # Off-beat if not near 0.0 or 0.5
        if beat_position > 0.1 and abs(beat_position - 0.5) > 0.1:
            offbeat_count += 1

    syncopation = offbeat_count / max(len(song.notes), 1)

    return min(1.0, (variety * 0.5 + syncopation * 0.5))


def _tempo_score(song: Song) -> float:
    """Score based on tempo (0.0 - 1.0).

    < 60 BPM = 0.0, > 180 BPM = 1.0.
    """
    bpm = 120.0
    if song.tempo_changes:
        bpm = song.tempo_changes[0].bpm

    return min(1.0, max(0.0, (bpm - 60.0) / 120.0))


def _key_complexity_score(song: Song) -> float:
    """Score based on pitch class distribution (0.0 - 1.0).

    More distinct pitch classes used = likely more accidentals.
    All 12 pitch classes = chromatic / atonal = max complexity.
    """
    if not song.notes:
        return 0.0

    pitch_classes = set(n.pitch % 12 for n in song.notes)
    # C major uses 7 pitch classes. 7 = baseline (0.0), 12 = max (1.0)
    return min(1.0, max(0.0, (len(pitch_classes) - 7) / 5.0))


def _chord_density_score(song: Song) -> float:
    """Score based on simultaneous notes (0.0 - 1.0).

    Measures average number of notes sounding at each onset time.
    Single notes = 0.0, 6+ note chords = 1.0.
    """
    if not song.notes:
        return 0.0

    # Group by quantized onset time (10ms buckets)
    onsets: dict[int, int] = {}
    for n in song.notes:
        bucket = round(n.start_time / 0.01)
        onsets[bucket] = onsets.get(bucket, 0) + 1

    if not onsets:
        return 0.0

    avg_simultaneous = sum(onsets.values()) / len(onsets)

    return min(1.0, max(0.0, (avg_simultaneous - 1.0) / 5.0))


def _find_hardest_bars(song: Song, beat_duration: float, beats_per_bar: int = 4) -> list[int]:
    """Return the bar numbers with the highest local difficulty."""
    if not song.notes or beat_duration <= 0:
        return []

    bar_duration = beat_duration * beats_per_bar
    total_bars = int(song.duration / bar_duration) + 1

    bar_scores: list[tuple[float, int]] = []
    for bar in range(total_bars):
        t_start = bar * bar_duration
        t_end = t_start + bar_duration
        bar_notes = [n for n in song.notes if t_start <= n.start_time < t_end]

        if not bar_notes:
            continue

        # Simple local difficulty: density + interval jumps
        density = len(bar_notes) / bar_duration
        pitches = [n.pitch for n in bar_notes]
        max_jump = 0
        for i in range(1, len(pitches)):
            max_jump = max(max_jump, abs(pitches[i] - pitches[i - 1]))

        score = density * 0.7 + (max_jump / 24.0) * 0.3
        bar_scores.append((score, bar + 1))  # 1-indexed bar numbers

    bar_scores.sort(reverse=True)
    return [bar for _, bar in bar_scores[:5]]


# Dimension weights for the weighted sum
_WEIGHTS = {
    "note_density": 0.20,
    "pitch_range": 0.08,
    "hand_independence": 0.18,
    "interval_complexity": 0.12,
    "rhythmic_complexity": 0.15,
    "tempo": 0.10,
    "key_complexity": 0.07,
    "chord_density": 0.10,
}


def estimate(song: Song) -> DifficultyReport:
    """Estimate the difficulty of a song on a 1-18 scale.

    Args:
        song: A loaded Song object.

    Returns:
        A DifficultyReport with overall level, per-dimension scores,
        hardest bars, and a human-readable description.
    """
    factors = {
        "note_density": _note_density_score(song),
        "pitch_range": _pitch_range_score(song),
        "hand_independence": _hand_independence_score(song),
        "interval_complexity": _interval_complexity_score(song),
        "rhythmic_complexity": _rhythmic_complexity_score(song),
        "tempo": _tempo_score(song),
        "key_complexity": _key_complexity_score(song),
        "chord_density": _chord_density_score(song),
    }

    weighted_sum = sum(factors[k] * _WEIGHTS[k] for k in _WEIGHTS)

    # Map 0.0-1.0 weighted sum to 1-18 level
    level = max(1, min(18, round(weighted_sum * 17) + 1))
    label = _label_for_level(level)

    bpm = 120.0
    if song.tempo_changes:
        bpm = song.tempo_changes[0].bpm
    beat_duration = 60.0 / bpm

    hardest = _find_hardest_bars(song, beat_duration)

    # Build description
    top_factors = sorted(factors.items(), key=lambda x: x[1], reverse=True)[:3]
    factor_strs = [f"{k.replace('_', ' ')} ({v:.0%})" for k, v in top_factors]
    description = (
        f"Level {level}/18 ({label}). "
        f"Primary challenges: {', '.join(factor_strs)}."
    )
    if hardest:
        description += f" Hardest bars: {', '.join(str(b) for b in hardest)}."

    return DifficultyReport(
        overall_level=level,
        overall_label=label,
        factors=factors,
        hardest_bars=hardest,
        description=description,
    )
