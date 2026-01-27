"""Hit evaluation — compare player input to expected notes."""

from __future__ import annotations

from keyfall.config import GOOD_WINDOW_MS, OK_WINDOW_MS, PERFECT_WINDOW_MS
from keyfall.models import HitGrade, HitResult, NoteEvent


def evaluate_hit(
    expected: NoteEvent,
    played_pitch: int,
    played_time: float,
) -> HitResult:
    """Grade a single note hit based on pitch match and timing offset."""
    offset_ms = (played_time - expected.start_time) * 1000.0

    if played_pitch != expected.pitch:
        return HitResult(
            expected=expected,
            played_pitch=played_pitch,
            grade=HitGrade.MISS,
            timing_offset_ms=offset_ms,
        )

    abs_offset = abs(offset_ms)
    if abs_offset <= PERFECT_WINDOW_MS:
        grade = HitGrade.PERFECT
    elif abs_offset <= GOOD_WINDOW_MS:
        grade = HitGrade.GOOD
    elif abs_offset <= OK_WINDOW_MS:
        grade = HitGrade.OK
    else:
        grade = HitGrade.MISS

    return HitResult(
        expected=expected,
        played_pitch=played_pitch,
        grade=grade,
        timing_offset_ms=offset_ms,
    )
