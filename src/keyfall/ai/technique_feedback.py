"""Real-time technique feedback — detect *why* a player is struggling."""

from __future__ import annotations

from dataclasses import dataclass

from keyfall.models import Hand, HitGrade, HitResult


@dataclass
class TechniqueInsight:
    """A single piece of technique feedback."""

    category: str  # "timing", "dynamics", "articulation", "evenness"
    severity: float  # 0.0 (minor) - 1.0 (critical)
    message: str
    bar_range: tuple[int, int] | None = None
    hand: Hand | None = None


def _split_by_hand(results: list[HitResult]) -> dict[Hand, list[HitResult]]:
    """Group results by hand."""
    by_hand: dict[Hand, list[HitResult]] = {
        Hand.LEFT: [],
        Hand.RIGHT: [],
    }
    for r in results:
        hand = r.expected.hand
        if hand in by_hand:
            by_hand[hand].append(r)
        else:
            # BOTH — attribute to both
            by_hand[Hand.LEFT].append(r)
            by_hand[Hand.RIGHT].append(r)
    return by_hand


def _detect_timing_drift(results: list[HitResult], hand: Hand) -> TechniqueInsight | None:
    """Detect systematic early/late tendency using mean offset.

    If a hand is consistently >15ms early or late across 10+ notes,
    flag it as a timing drift issue.
    """
    hits = [r for r in results if r.grade != HitGrade.MISS and r.played_pitch is not None]
    if len(hits) < 10:
        return None

    offsets = [r.timing_offset_ms for r in hits]
    mean_offset = sum(offsets) / len(offsets)

    if abs(mean_offset) < 15.0:
        return None

    direction = "early" if mean_offset < 0 else "late"
    hand_name = "Left hand" if hand == Hand.LEFT else "Right hand"

    return TechniqueInsight(
        category="timing",
        severity=min(1.0, abs(mean_offset) / 80.0),
        message=f"{hand_name} is consistently {abs(mean_offset):.0f}ms {direction}",
        hand=hand,
    )


def _detect_timing_variance(results: list[HitResult], hand: Hand) -> TechniqueInsight | None:
    """Detect inconsistent timing (high variance even if mean is centered)."""
    hits = [r for r in results if r.grade != HitGrade.MISS and r.played_pitch is not None]
    if len(hits) < 10:
        return None

    offsets = [r.timing_offset_ms for r in hits]
    mean = sum(offsets) / len(offsets)
    variance = sum((o - mean) ** 2 for o in offsets) / len(offsets)
    std_dev = variance ** 0.5

    if std_dev < 30.0:
        return None

    hand_name = "Left hand" if hand == Hand.LEFT else "Right hand"

    return TechniqueInsight(
        category="timing",
        severity=min(1.0, std_dev / 100.0),
        message=f"{hand_name} timing is unsteady (±{std_dev:.0f}ms variance)",
        hand=hand,
    )


def _detect_rush_or_drag(results: list[HitResult]) -> TechniqueInsight | None:
    """Detect accelerando/ritardando tendency across the session.

    Compare average timing offset in the first half vs second half.
    If the second half is significantly earlier, the player is rushing.
    """
    hits = [r for r in results if r.grade != HitGrade.MISS and r.played_pitch is not None]
    if len(hits) < 20:
        return None

    mid = len(hits) // 2
    first_half_mean = sum(r.timing_offset_ms for r in hits[:mid]) / mid
    second_half_mean = sum(r.timing_offset_ms for r in hits[mid:]) / (len(hits) - mid)

    drift = second_half_mean - first_half_mean

    if abs(drift) < 20.0:
        return None

    if drift < 0:
        return TechniqueInsight(
            category="timing",
            severity=min(1.0, abs(drift) / 80.0),
            message=f"Rushing: timing drifts {abs(drift):.0f}ms earlier by end of passage",
        )
    else:
        return TechniqueInsight(
            category="timing",
            severity=min(1.0, abs(drift) / 80.0),
            message=f"Dragging: timing drifts {abs(drift):.0f}ms later by end of passage",
        )


def _detect_dynamic_mismatch(results: list[HitResult]) -> list[TechniqueInsight]:
    """Detect velocity mismatches — too loud in soft passages or vice versa.

    Compares expected velocity to played velocity (approximated from
    the expected note's velocity as the target dynamic).
    """
    insights: list[TechniqueInsight] = []
    hits = [r for r in results if r.grade != HitGrade.MISS and r.played_pitch is not None]
    if len(hits) < 5:
        return insights

    # Group notes into soft (velocity < 60) and loud (velocity > 100)
    soft_notes = [r for r in hits if r.expected.velocity < 60]
    loud_notes = [r for r in hits if r.expected.velocity > 100]

    # Check if soft passages have too many missed/OK grades (suggests pounding)
    if len(soft_notes) >= 5:
        soft_miss_rate = sum(1 for r in soft_notes if r.grade in (HitGrade.OK, HitGrade.MISS)) / len(soft_notes)
        if soft_miss_rate > 0.3:
            insights.append(
                TechniqueInsight(
                    category="dynamics",
                    severity=min(1.0, soft_miss_rate),
                    message="Struggling in piano (soft) passages — try lighter touch",
                )
            )

    if len(loud_notes) >= 5:
        loud_miss_rate = sum(1 for r in loud_notes if r.grade in (HitGrade.OK, HitGrade.MISS)) / len(loud_notes)
        if loud_miss_rate > 0.3:
            insights.append(
                TechniqueInsight(
                    category="dynamics",
                    severity=min(1.0, loud_miss_rate),
                    message="Struggling in forte (loud) passages — need more confident attack",
                )
            )

    return insights


def _detect_uneven_fingers(results: list[HitResult], hand: Hand) -> TechniqueInsight | None:
    """Detect uneven velocity in scale/run passages.

    Look for sequences of 5+ consecutive notes with small intervals (1-2 semitones)
    and check if velocity varies more than expected.
    """
    hits = [r for r in results if r.grade != HitGrade.MISS and r.played_pitch is not None]
    if len(hits) < 8:
        return None

    # Find runs: sequences where each note is 1-2 semitones from the previous
    run_start = 0
    runs: list[list[HitResult]] = []

    for i in range(1, len(hits)):
        interval = abs(hits[i].expected.pitch - hits[i - 1].expected.pitch)
        if interval > 2:
            if i - run_start >= 5:
                runs.append(hits[run_start:i])
            run_start = i

    if len(hits) - run_start >= 5:
        runs.append(hits[run_start:])

    if not runs:
        return None

    # Check velocity variance within runs
    for run in runs:
        velocities = [r.expected.velocity for r in run]
        mean_vel = sum(velocities) / len(velocities)
        if mean_vel == 0:
            continue
        variance = sum((v - mean_vel) ** 2 for v in velocities) / len(velocities)
        # Check timing variance instead (what we can actually measure)
        timing_offsets = [abs(r.timing_offset_ms) for r in run]
        mean_timing = sum(timing_offsets) / len(timing_offsets)

        if mean_timing > 40.0:
            hand_name = "Left hand" if hand == Hand.LEFT else "Right hand"
            return TechniqueInsight(
                category="evenness",
                severity=min(1.0, mean_timing / 100.0),
                message=f"{hand_name} runs are uneven — average {mean_timing:.0f}ms timing error in scale passages",
                hand=hand,
            )

    return None


def _detect_articulation_errors(results: list[HitResult]) -> TechniqueInsight | None:
    """Detect articulation issues by checking for patterns of OK/MISS
    grades in passages with short note durations (staccato) vs long (legato).

    Short notes (<0.2s) that are graded MISS often indicate the player
    is holding too long (playing legato instead of staccato).
    """
    short_notes = [r for r in results if r.expected.duration < 0.2]
    if len(short_notes) < 5:
        return None

    miss_rate = sum(1 for r in short_notes if r.grade == HitGrade.MISS) / len(short_notes)
    if miss_rate > 0.4:
        return TechniqueInsight(
            category="articulation",
            severity=min(1.0, miss_rate),
            message="Staccato passages need crisper release — notes are held too long",
        )

    return None


def analyze(results: list[HitResult]) -> list[TechniqueInsight]:
    """Analyze a sequence of HitResults and return technique insights.

    Args:
        results: HitResults from the evaluator, in chronological order.

    Returns:
        List of TechniqueInsight, sorted by severity (highest first).
    """
    if not results:
        return []

    insights: list[TechniqueInsight] = []

    # Per-hand analysis
    by_hand = _split_by_hand(results)
    for hand, hand_results in by_hand.items():
        if not hand_results:
            continue

        drift = _detect_timing_drift(hand_results, hand)
        if drift:
            insights.append(drift)

        variance = _detect_timing_variance(hand_results, hand)
        if variance:
            insights.append(variance)

        evenness = _detect_uneven_fingers(hand_results, hand)
        if evenness:
            insights.append(evenness)

    # Whole-session analysis
    rush_drag = _detect_rush_or_drag(results)
    if rush_drag:
        insights.append(rush_drag)

    dynamics = _detect_dynamic_mismatch(results)
    insights.extend(dynamics)

    articulation = _detect_articulation_errors(results)
    if articulation:
        insights.append(articulation)

    # Sort by severity, highest first
    insights.sort(key=lambda i: i.severity, reverse=True)

    return insights
