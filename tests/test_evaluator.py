"""Tests for hit evaluation logic."""

from keyfall.evaluator import evaluate_hit
from keyfall.models import HitGrade, NoteEvent


def test_perfect_hit():
    note = NoteEvent(pitch=60, start_time=1.0, duration=0.5)
    result = evaluate_hit(note, played_pitch=60, played_time=1.02)
    assert result.grade == HitGrade.PERFECT


def test_good_hit():
    note = NoteEvent(pitch=60, start_time=1.0, duration=0.5)
    result = evaluate_hit(note, played_pitch=60, played_time=1.08)
    assert result.grade == HitGrade.GOOD


def test_wrong_pitch_is_miss():
    note = NoteEvent(pitch=60, start_time=1.0, duration=0.5)
    result = evaluate_hit(note, played_pitch=62, played_time=1.0)
    assert result.grade == HitGrade.MISS


def test_late_hit_is_miss():
    note = NoteEvent(pitch=60, start_time=1.0, duration=0.5)
    result = evaluate_hit(note, played_pitch=60, played_time=1.5)
    assert result.grade == HitGrade.MISS
