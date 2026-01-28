"""Hit evaluation — compare player input to expected notes."""

from __future__ import annotations

from keyfall.config import GOOD_WINDOW_MS, OK_WINDOW_MS, PERFECT_WINDOW_MS
from keyfall.models import HitGrade, HitResult, NoteEvent, SessionStats


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


class HitTracker:
    """Stateful evaluator that matches played notes to expected notes and tracks stats."""

    def __init__(self, song_notes: list[NoteEvent], song_title: str = "") -> None:
        self._expected = list(song_notes)
        self._song_title = song_title
        self._pending: list[tuple[int, NoteEvent]] = []  # (original_index, note)
        self._next_idx = 0
        self._results: list[HitResult] = []
        self._streak = 0
        self._max_streak = 0

    def _activate_pending(self, current_time: float) -> None:
        """Move notes within the OK window into the pending set."""
        window_s = OK_WINDOW_MS / 1000.0
        while self._next_idx < len(self._expected):
            note = self._expected[self._next_idx]
            if note.start_time <= current_time + window_s:
                self._pending.append((self._next_idx, note))
                self._next_idx += 1
            else:
                break

    def feed(self, played_pitch: int, played_time: float) -> HitResult | None:
        """Match a played note to the nearest pending expected note.

        Returns HitResult if matched, None if no match (extra note).
        """
        self._activate_pending(played_time)

        best_idx: int | None = None
        best_offset = float("inf")

        for i, (orig_idx, note) in enumerate(self._pending):
            if note.pitch == played_pitch:
                offset = abs(played_time - note.start_time)
                if offset < best_offset:
                    best_offset = offset
                    best_idx = i

        if best_idx is None:
            return None

        _, note = self._pending.pop(best_idx)
        result = evaluate_hit(note, played_pitch, played_time)
        self._record(result)
        return result

    def flush_misses(self, current_time: float) -> list[HitResult]:
        """Mark any pending notes whose window has fully passed as MISS."""
        self._activate_pending(current_time)
        window_s = OK_WINDOW_MS / 1000.0
        missed: list[HitResult] = []
        remaining: list[tuple[int, NoteEvent]] = []

        for orig_idx, note in self._pending:
            if current_time - note.start_time > window_s:
                result = HitResult(
                    expected=note,
                    played_pitch=None,
                    grade=HitGrade.MISS,
                    timing_offset_ms=(current_time - note.start_time) * 1000.0,
                )
                self._record(result)
                missed.append(result)
            else:
                remaining.append((orig_idx, note))

        self._pending = remaining
        return missed

    def _record(self, result: HitResult) -> None:
        self._results.append(result)
        if result.grade != HitGrade.MISS:
            self._streak += 1
            self._max_streak = max(self._max_streak, self._streak)
        else:
            self._streak = 0

    def get_stats(self) -> SessionStats:
        """Aggregate all results into SessionStats."""
        perfect = sum(1 for r in self._results if r.grade == HitGrade.PERFECT)
        good = sum(1 for r in self._results if r.grade == HitGrade.GOOD)
        ok = sum(1 for r in self._results if r.grade == HitGrade.OK)
        missed = sum(1 for r in self._results if r.grade == HitGrade.MISS)
        total = len(self._results)
        hits = perfect + good + ok
        accuracy = (hits / total * 100.0) if total > 0 else 0.0

        return SessionStats(
            song_title=self._song_title,
            total_notes=total,
            perfect=perfect,
            good=good,
            ok=ok,
            missed=missed,
            max_streak=self._max_streak,
            accuracy_pct=round(accuracy, 1),
        )
