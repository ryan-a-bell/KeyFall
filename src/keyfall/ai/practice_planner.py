"""Practice plan generation from session history and song analysis."""

from __future__ import annotations

from dataclasses import dataclass, field

from keyfall.models import Hand, NoteEvent, Song


@dataclass
class PracticeStep:
    """A single step in a practice plan."""

    bar_range: tuple[int, int]
    hand: Hand
    tempo_pct: int  # percentage of original tempo (e.g. 70 = 70%)
    repetitions: int
    focus: str  # human-readable goal for this step


@dataclass
class PracticePlan:
    """A structured practice plan for a song."""

    song_title: str
    steps: list[PracticeStep] = field(default_factory=list)
    estimated_sessions: int = 1
    current_mastery_pct: float = 0.0


def _notes_in_bar_range(
    notes: list[NoteEvent], bar_start: int, bar_end: int, beat_duration: float
) -> list[NoteEvent]:
    """Return notes whose start_time falls within the given bar range."""
    t_start = bar_start * beat_duration * 4  # assume 4/4 for simplicity
    t_end = bar_end * beat_duration * 4
    return [n for n in notes if t_start <= n.start_time < t_end]


def _bar_for_time(time: float, beat_duration: float, beats_per_bar: int = 4) -> int:
    """Convert a time in seconds to a bar number (0-indexed)."""
    if beat_duration <= 0:
        return 0
    return int(time / (beat_duration * beats_per_bar))


def _compute_section_accuracy(
    history: list[dict], song_title: str
) -> dict[str, float]:
    """Extract per-session accuracy from progress history.

    Returns a dict with keys like 'overall' and individual metric ratios.
    """
    relevant = [h for h in history if h.get("song_title") == song_title]
    if not relevant:
        return {"overall": 0.0, "sessions_played": 0}

    latest = relevant[:5]  # most recent 5 sessions
    avg_accuracy = sum(s.get("accuracy_pct", 0.0) for s in latest) / len(latest)
    avg_perfect = sum(s.get("perfect", 0) for s in latest) / len(latest)
    avg_total = sum(s.get("total_notes", 1) for s in latest) / len(latest)

    return {
        "overall": avg_accuracy,
        "perfect_ratio": avg_perfect / max(avg_total, 1),
        "sessions_played": len(relevant),
    }


def _identify_weak_sections(
    song: Song, history: list[dict], beat_duration: float
) -> list[tuple[int, int, str, Hand]]:
    """Identify bar ranges that need the most work.

    Since we don't yet have per-note history, we analyze the song structure
    to find inherently difficult passages and pair them with overall accuracy.
    Returns list of (bar_start, bar_end, reason, hand).
    """
    if not song.notes:
        return []

    beats_per_bar = 4
    bar_duration = beat_duration * beats_per_bar
    total_bars = _bar_for_time(song.duration, beat_duration, beats_per_bar) + 1

    weak_sections: list[tuple[int, int, str, Hand]] = []

    # Scan in 4-bar windows for density spikes and large intervals
    window = 4
    for bar in range(0, total_bars, window):
        bar_end = min(bar + window, total_bars)
        t_start = bar * bar_duration
        t_end = bar_end * bar_duration

        window_notes = [n for n in song.notes if t_start <= n.start_time < t_end]
        if not window_notes:
            continue

        # Check note density (notes per second)
        window_duration = t_end - t_start
        density = len(window_notes) / max(window_duration, 0.01)

        # Check for large interval jumps
        pitches = sorted(set(n.pitch for n in window_notes))
        max_jump = 0
        for i in range(1, len(pitches)):
            max_jump = max(max_jump, pitches[i] - pitches[i - 1])

        # Check hand independence (both hands active with different rhythms)
        lh_notes = [n for n in window_notes if n.hand == Hand.LEFT]
        rh_notes = [n for n in window_notes if n.hand == Hand.RIGHT]
        has_independence = len(lh_notes) > 2 and len(rh_notes) > 2

        # Flag as weak if any difficulty indicator is high
        if density > 4.0:
            weak_sections.append(
                (bar, bar_end, f"High note density ({density:.1f} notes/sec)", Hand.BOTH)
            )
        elif max_jump > 12:
            hand = Hand.BOTH
            if all(n.hand == Hand.LEFT for n in window_notes if abs(n.pitch - min(pitches)) < 3):
                hand = Hand.LEFT
            elif all(n.hand == Hand.RIGHT for n in window_notes if abs(n.pitch - max(pitches)) < 3):
                hand = Hand.RIGHT
            weak_sections.append(
                (bar, bar_end, f"Large interval leap ({max_jump} semitones)", hand)
            )
        elif has_independence:
            weak_sections.append(
                (bar, bar_end, "Complex hand independence", Hand.BOTH)
            )

    return weak_sections


def generate_plan(
    song: Song,
    history: list[dict],
    target_accuracy: float = 0.95,
    max_steps: int = 8,
) -> PracticePlan:
    """Generate a structured practice plan for a song.

    Args:
        song: The song to practice.
        history: Session history from ProgressTracker.get_history().
        target_accuracy: Accuracy goal (0.0 - 1.0).
        max_steps: Maximum number of steps in the plan.

    Returns:
        A PracticePlan with ordered steps.
    """
    plan = PracticePlan(song_title=song.title)

    if not song.notes:
        plan.steps.append(
            PracticeStep(
                bar_range=(0, 0),
                hand=Hand.BOTH,
                tempo_pct=100,
                repetitions=1,
                focus="No notes found in this song",
            )
        )
        return plan

    # Determine beat duration from tempo
    bpm = 120.0
    if song.tempo_changes:
        bpm = song.tempo_changes[0].bpm
    beat_duration = 60.0 / bpm

    # Analyze history
    stats = _compute_section_accuracy(history, song.title)
    mastery = stats["overall"] / 100.0 if stats["overall"] > 1.0 else stats["overall"]
    plan.current_mastery_pct = mastery * 100.0
    sessions_played = stats.get("sessions_played", 0)

    # Determine starting tempo based on mastery
    if sessions_played == 0:
        base_tempo_pct = 60
    elif mastery < 0.5:
        base_tempo_pct = 50
    elif mastery < 0.7:
        base_tempo_pct = 65
    elif mastery < 0.85:
        base_tempo_pct = 80
    elif mastery < target_accuracy:
        base_tempo_pct = 90
    else:
        base_tempo_pct = 100

    total_bars = _bar_for_time(song.duration, beat_duration) + 1

    # Find weak sections
    weak_sections = _identify_weak_sections(song, history, beat_duration)

    # Build steps: weak sections first (hands separate, then together)
    for bar_start, bar_end, reason, hand in weak_sections[:max_steps // 2]:
        # Hands separate first if the section involves both hands
        if hand == Hand.BOTH:
            plan.steps.append(
                PracticeStep(
                    bar_range=(bar_start, bar_end),
                    hand=Hand.RIGHT,
                    tempo_pct=max(base_tempo_pct - 10, 40),
                    repetitions=3,
                    focus=f"RH alone: {reason} (bars {bar_start + 1}-{bar_end})",
                )
            )
            plan.steps.append(
                PracticeStep(
                    bar_range=(bar_start, bar_end),
                    hand=Hand.LEFT,
                    tempo_pct=max(base_tempo_pct - 10, 40),
                    repetitions=3,
                    focus=f"LH alone: {reason} (bars {bar_start + 1}-{bar_end})",
                )
            )
            plan.steps.append(
                PracticeStep(
                    bar_range=(bar_start, bar_end),
                    hand=Hand.BOTH,
                    tempo_pct=base_tempo_pct,
                    repetitions=3,
                    focus=f"Hands together: {reason} (bars {bar_start + 1}-{bar_end})",
                )
            )
        else:
            plan.steps.append(
                PracticeStep(
                    bar_range=(bar_start, bar_end),
                    hand=hand,
                    tempo_pct=max(base_tempo_pct - 10, 40),
                    repetitions=4,
                    focus=f"{reason} (bars {bar_start + 1}-{bar_end})",
                )
            )

    # Add a full run-through at the end
    if len(plan.steps) < max_steps:
        plan.steps.append(
            PracticeStep(
                bar_range=(0, total_bars),
                hand=Hand.BOTH,
                tempo_pct=base_tempo_pct,
                repetitions=2,
                focus="Full run-through at practice tempo",
            )
        )

    # If mastery is close to target, add a performance tempo pass
    if mastery >= target_accuracy * 0.85 and len(plan.steps) < max_steps:
        plan.steps.append(
            PracticeStep(
                bar_range=(0, total_bars),
                hand=Hand.BOTH,
                tempo_pct=100,
                repetitions=1,
                focus="Performance run at full tempo",
            )
        )

    # Trim to max_steps
    plan.steps = plan.steps[:max_steps]

    # Estimate sessions to mastery
    if mastery >= target_accuracy:
        plan.estimated_sessions = 0
    else:
        gap = target_accuracy - mastery
        plan.estimated_sessions = max(1, int(gap / 0.05) + 1)

    return plan
