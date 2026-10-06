"""Practice Coach: section ladder, adaptation, persistence, and the screen flow."""

import pygame
import pytest

from keyfall.coach import TEMPOS, CoachState, CoachStep, technique_tips
from keyfall.models import Hand, HitGrade, HitResult, NoteEvent, Song, TempoChange
from keyfall.ui_state import UIState
from keyfall.views.base import ViewContext, ViewManager
from keyfall.views.coach_view import CoachView
from keyfall.views.menu_view import MenuView
from keyfall.views.practice_view import PracticeView


def _song(bars=8, left_hand=True, title="Coach Tune"):
    notes = []
    for b in range(bars):  # 120 BPM, 2 s per bar
        for beat in range(4):
            t = b * 2.0 + beat * 0.5
            notes.append(NoteEvent(60 + beat, t, 0.4, hand=Hand.RIGHT))
            if left_hand and beat == 0:
                notes.append(NoteEvent(48, t, 1.8, hand=Hand.LEFT))
    return Song(title=title, notes=notes, tempo_changes=[TempoChange(0.0, 120.0)],
                duration=bars * 2.0)


def test_song_is_split_into_four_bar_sections_with_hands():
    state = CoachState.for_song(_song(bars=10))
    assert [(s.first_bar, s.last_bar) for s in state.sections] == [(1, 4), (5, 8), (9, 10)]
    assert state.sections[0].hands == ["right", "left"]
    assert CoachState.for_song(_song(left_hand=False)).sections[0].ladder() == [
        "right", "together", "tempo"]


def test_ladder_from_hands_to_full_tempo():
    state = CoachState.for_song(_song(bars=4))
    seen = []
    while state.current_section() is not None:
        step = state.next_step()
        seen.append((step.rung, step.tempo_pct, step.wait_mode, step.hand))
        state.record_pass(step, 95.0, 10.0)
    assert seen == [("right", 100, True, Hand.RIGHT), ("left", 100, True, Hand.LEFT),
                    ("together", 100, True, Hand.BOTH)] + [
        ("tempo", t, False, Hand.BOTH) for t in TEMPOS]
    assert state.mastery == 1.0
    assert state.next_step().rung == "full"


def test_struggling_slows_down_and_middling_repeats():
    state = CoachState.for_song(_song(bars=4, left_hand=False))
    for _ in range(2):
        state.record_pass(state.next_step(), 95.0, 5.0)  # right, together
    state.record_pass(state.next_step(), 95.0, 5.0)  # 60 -> 70
    assert state.next_step().tempo_pct == 70
    msg = state.record_pass(state.next_step(), 40.0, 5.0)
    assert "slow down" in msg and state.next_step().tempo_pct == 60
    msg = state.record_pass(state.next_step(), 75.0, 5.0)
    assert "Once more" in msg and state.next_step().tempo_pct == 60


def test_progress_is_saved_and_reloaded(tmp_path):
    song = _song()
    state = CoachState.for_song(song)
    state.record_pass(state.next_step(), 92.0, 30.0)
    state.save(tmp_path)
    again = CoachState.load(song, tmp_path)
    assert again.next_step().rung == "left"
    assert again.today() == (1, 0.5)
    assert again.daily_accuracy()[-1][1] == 92.0


def test_technique_tips_spot_a_late_hand():
    notes = [NoteEvent(60 + i % 5, i * 0.5, 0.3, hand=Hand.RIGHT) for i in range(20)]
    hits = [HitResult(n, n.pitch, HitGrade.GOOD, 60.0) for n in notes]
    tips = technique_tips(hits)
    assert tips and any("late" in t.lower() for t in tips)


@pytest.fixture
def coach_app(tmp_path, monkeypatch):
    pygame.init()
    monkeypatch.setattr(CoachView, "coach_dir", tmp_path)
    ctx = ViewContext(screen_size=(1280, 720), midi_input=None, audio=None, progress=None,
                      ui=UIState(persist=False))
    vm = ViewManager(ctx)
    for cls in (MenuView, CoachView, PracticeView):
        vm.register(cls)
    vm.push("menu")
    vm.push("coach", song=_song())
    return vm


def _key(vm, k):
    vm.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""))


def test_coach_screen_runs_a_step_and_advances(coach_app):
    vm = coach_app
    coach = vm.active_view
    assert coach.frame().step_label == "Bars 1–4 · Right hand alone · Wait mode"
    vm.draw(pygame.Surface((1280, 720)))
    _key(vm, pygame.K_RETURN)
    practice = vm.active_view
    assert practice.name == "practice"
    assert practice._engine.wait_mode and practice._engine.active_hand == Hand.RIGHT
    assert practice._coach_label().startswith("Coach · Bars 1–4")
    for _ in range(60 * 30):  # play the right-hand notes perfectly
        if vm.active_view is not practice:
            break
        eng = practice._engine
        practice._pressed = {n.pitch for n in eng.song.notes if n.hand == Hand.RIGHT
                             and n.start_time <= eng.position < n.start_time + n.duration}
        vm.update(1 / 60)
    coach = vm.active_view
    assert coach.name == "coach"
    assert coach._verdict.startswith("100%") and "left hand" in coach._verdict
    assert coach.frame().step_label.endswith("Left hand alone · Wait mode")
    vm.draw(pygame.Surface((1280, 720)))


def test_leaving_a_step_early_returns_without_a_verdict(coach_app):
    vm = coach_app
    _key(vm, pygame.K_RETURN)
    _key(vm, pygame.K_ESCAPE)
    coach = vm.active_view
    assert coach.name == "coach" and "stopped early" in coach._verdict
    assert coach.frame().step_label.endswith("Right hand alone · Wait mode")


def test_skip_moves_on(coach_app):
    vm = coach_app
    coach = vm.active_view
    coach._selected = 1
    _key(vm, pygame.K_RETURN)
    assert coach.frame().step_label.endswith("Left hand alone · Wait mode")


def test_coach_step_label():
    assert CoachStep(5, 8, "tempo", 70).label == "Bars 5–8 · Hands together · 70% tempo"
