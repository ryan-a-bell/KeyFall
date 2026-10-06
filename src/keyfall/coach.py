"""Practice Coach: a guided, adaptive way to learn a whole song.

The song is cut into short sections (4 bars). Each section climbs a ladder:

    right hand alone -> left hand alone -> hands together (wait mode)
        -> real time at 60% -> 70% -> 80% -> 90% -> 100% tempo

One coach "step" is a single pass over one section at one rung. After each
pass the coach decides:

- accuracy >= ADVANCE_AT  -> climb to the next rung
- accuracy <  STRUGGLE_AT -> on a tempo rung, drop back 10%; otherwise repeat
- in between              -> repeat the same step

It always works on the earliest section that isn't mastered yet, so the song
is learned front to back. Once every section is mastered, it suggests a full
run-through. Progress is saved per song in ~/.keyfall/coach/; ``merge_coach_docs``
combines the same song's progress from two devices.

Between passes, technique tips come from :mod:`keyfall.ai.technique_feedback`
(timing drift per hand, unevenness, dynamics...).
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from keyfall.models import Hand, HitResult, Song
from keyfall.playback import BEATS_PER_BAR, beat_length
from keyfall.storage import data_dir, new_id, now_iso

COACH_DIR = data_dir() / "coach"
SECTION_BARS = 4
ADVANCE_AT = 90.0
STRUGGLE_AT = 60.0
TEMPOS = (60, 70, 80, 90, 100)

# Rungs of the ladder. Hand rungs are skipped for sections with no notes in that hand.
HAND_RUNGS = ("right", "left", "together")
RUNG_NAMES = {"right": "Right hand alone", "left": "Left hand alone",
              "together": "Hands together"}


@dataclass
class CoachStep:
    first_bar: int
    last_bar: int
    rung: str  # right | left | together | tempo | full
    tempo_pct: int = 100

    @property
    def hand(self) -> Hand:
        return {"right": Hand.RIGHT, "left": Hand.LEFT}.get(self.rung, Hand.BOTH)

    @property
    def wait_mode(self) -> bool:
        return self.rung in HAND_RUNGS

    @property
    def label(self) -> str:
        bars = f"Bars {self.first_bar}–{self.last_bar}"
        if self.rung == "full":
            return f"Full song at {self.tempo_pct}% tempo"
        if self.rung == "tempo":
            return f"{bars} · Hands together · {self.tempo_pct}% tempo"
        return f"{bars} · {RUNG_NAMES[self.rung]} · Wait mode"


@dataclass
class SectionState:
    first_bar: int
    last_bar: int
    hands: list[str]  # which hand rungs apply ("right", "left")
    rung: str = ""  # current rung; "" = not started
    tempo_pct: int = TEMPOS[0]
    mastered: bool = False
    passes: int = 0
    best: float = 0.0

    def ladder(self) -> list[str]:
        rungs = [r for r in ("right", "left") if r in self.hands]
        rungs.append("together")
        return rungs + ["tempo"]

    @property
    def progress(self) -> float:
        """0..1 position on the ladder (for the section map)."""
        if self.mastered:
            return 1.0
        ladder = self.ladder()
        rung = self.rung or ladder[0]
        steps = len(ladder) - 1 + len(TEMPOS)
        done = ladder.index(rung) if rung in ladder else 0
        if rung == "tempo":
            done = len(ladder) - 1 + TEMPOS.index(self.tempo_pct)
        return done / steps


@dataclass
class PassRecord:
    date: str
    first_bar: int
    last_bar: int
    rung: str
    tempo_pct: int
    accuracy: float
    seconds: float
    id: str = ""  # unique per pass, so merging two devices' history doesn't double up


@dataclass
class CoachState:
    song_title: str
    sections: list[SectionState] = field(default_factory=list)
    history: list[PassRecord] = field(default_factory=list)
    full_run_tempo: int = 100
    song_hash: str = ""  # Song.source_hash
    updated_at: str = ""  # UTC ISO time of the last save

    # ------------------------------------------------------------------ building
    @classmethod
    def for_song(cls, song: Song) -> CoachState:
        bar_len = beat_length(song) * BEATS_PER_BAR
        n_bars = max(1, math.ceil(song.duration / bar_len - 1e-6))
        sections = []
        for first in range(1, n_bars + 1, SECTION_BARS):
            last = min(first + SECTION_BARS - 1, n_bars)
            t0, t1 = (first - 1) * bar_len, last * bar_len
            notes = [n for n in song.notes if t0 <= n.start_time < t1]
            if not notes:
                continue
            hands = []
            if any(n.hand == Hand.RIGHT for n in notes):
                hands.append("right")
            if any(n.hand == Hand.LEFT for n in notes):
                hands.append("left")
            sections.append(SectionState(first, last, hands))
        return cls(song_title=song.title, sections=sections, song_hash=song.source_hash)

    # ------------------------------------------------------------------ planning
    def current_section(self) -> SectionState | None:
        return next((s for s in self.sections if not s.mastered), None)

    def next_step(self) -> CoachStep:
        section = self.current_section()
        if section is None:
            last = self.sections[-1].last_bar if self.sections else 1
            return CoachStep(1, last, "full", self.full_run_tempo)
        rung = section.rung or section.ladder()[0]
        return CoachStep(section.first_bar, section.last_bar, rung,
                         section.tempo_pct if rung == "tempo" else 100)

    @property
    def mastery(self) -> float:
        if not self.sections:
            return 0.0
        return sum(s.progress for s in self.sections) / len(self.sections)

    # ------------------------------------------------------------------ results
    def record_pass(self, step: CoachStep, accuracy: float, seconds: float) -> str:
        """Apply one pass and return the coach's verdict for the player."""
        self.history.append(PassRecord(_dt.date.today().isoformat(), step.first_bar,
                                       step.last_bar, step.rung, step.tempo_pct,
                                       round(accuracy, 1), round(seconds, 1), new_id()))
        if step.rung == "full":
            if accuracy >= ADVANCE_AT:
                return f"Full run at {step.tempo_pct}%: {accuracy:.0f}%. You've learned this song!"
            return (f"Full run: {accuracy:.0f}%. Polish the sections you stumbled on and try "
                    "again.")

        section = next((s for s in self.sections
                        if s.first_bar == step.first_bar and s.last_bar == step.last_bar), None)
        if section is None:
            return ""
        section.passes += 1
        section.best = max(section.best, accuracy)
        ladder = section.ladder()
        rung = section.rung or ladder[0]

        if accuracy >= ADVANCE_AT:
            if rung == "tempo":
                if section.tempo_pct >= TEMPOS[-1]:
                    section.mastered = True
                    return f"{accuracy:.0f}% at full tempo. Bars {section.first_bar}–" \
                           f"{section.last_bar} mastered!"
                section.tempo_pct = TEMPOS[TEMPOS.index(section.tempo_pct) + 1]
                return f"{accuracy:.0f}%. Speeding up to {section.tempo_pct}%."
            section.rung = ladder[ladder.index(rung) + 1]
            nxt = section.rung
            if nxt == "tempo":
                section.tempo_pct = TEMPOS[0]
                return f"{accuracy:.0f}%. Now in real time, starting at {TEMPOS[0]}% tempo."
            return f"{accuracy:.0f}%. Next: {RUNG_NAMES[nxt].lower()}."

        section.rung = rung
        if accuracy < STRUGGLE_AT and rung == "tempo" and section.tempo_pct > TEMPOS[0]:
            section.tempo_pct = TEMPOS[TEMPOS.index(section.tempo_pct) - 1]
            return f"{accuracy:.0f}%. Let's slow down to {section.tempo_pct}% and lock it in."
        if accuracy < STRUGGLE_AT:
            return f"{accuracy:.0f}%. Take it slowly; same step again."
        return f"{accuracy:.0f}%. Close! {ADVANCE_AT:.0f}% moves you on. Once more."

    # ------------------------------------------------------------------ stats
    def today(self) -> tuple[int, float]:
        """(passes, minutes) practiced today."""
        today = _dt.date.today().isoformat()
        records = [r for r in self.history if r.date == today]
        return len(records), sum(r.seconds for r in records) / 60.0

    def daily_accuracy(self, days: int = 14) -> list[tuple[str, float]]:
        """Average pass accuracy per practice day (most recent ``days``)."""
        by_day: dict[str, list[float]] = {}
        for r in self.history:
            by_day.setdefault(r.date, []).append(r.accuracy)
        return [(d, sum(v) / len(v)) for d, v in sorted(by_day.items())][-days:]

    # ------------------------------------------------------------------ storage
    @staticmethod
    def path_for(title: str, folder: Path | None = None) -> Path:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_") or "song"
        return (folder or COACH_DIR) / f"{safe}.json"

    def save(self, folder: Path | None = None) -> None:
        self.updated_at = now_iso()
        write_coach_doc(asdict(self), folder)

    @classmethod
    def load(cls, song: Song, folder: Path | None = None) -> CoachState:
        """Saved state for this song, or a fresh plan if none (or the song changed)."""
        fresh = cls.for_song(song)
        try:
            data = json.loads(cls.path_for(song.title, folder).read_text())
        except (OSError, ValueError):
            return fresh
        sections = [SectionState(**s) for s in data.get("sections", [])]
        if [(s.first_bar, s.last_bar) for s in sections] != \
                [(s.first_bar, s.last_bar) for s in fresh.sections]:
            return fresh  # the song's structure changed (e.g. different hand split)
        return cls(song_title=song.title, sections=sections,
                   history=[PassRecord(**r) for r in data.get("history", [])],
                   full_run_tempo=data.get("full_run_tempo", 100),
                   song_hash=song.source_hash or data.get("song_hash", ""),
                   updated_at=data.get("updated_at", ""))


# ---------------------------------------------------------------------- sync
def read_coach_docs(folder: Path | None = None) -> list[dict]:
    """Every saved coach state, as the raw dicts written by ``CoachState.save``."""
    docs = []
    for path in sorted((folder or COACH_DIR).glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("song_title"):
            docs.append(data)
    return docs


def write_coach_doc(doc: dict, folder: Path | None = None) -> None:
    path = CoachState.path_for(doc["song_title"], folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1))


def merge_coach_docs(local: dict | None, remote: dict) -> dict:
    """One song's coach progress from two devices, combined.

    Every practice pass from both is kept. Section progress comes from whichever was
    saved most recently, since the ladder position can't be added together.
    """
    if not local:
        return remote
    newer, older = (remote, local) if remote.get("updated_at", "") > \
        local.get("updated_at", "") else (local, remote)

    def key(record: dict) -> tuple:
        return (record.get("id"),) if record.get("id") else tuple(sorted(record.items()))

    seen, history = set(), []
    for record in older.get("history", []) + newer.get("history", []):
        if key(record) not in seen:
            seen.add(key(record))
            history.append(record)
    history.sort(key=lambda r: r.get("date", ""))  # stable: same-day passes keep their order
    return {**newer, "history": history,
            "song_hash": newer.get("song_hash") or older.get("song_hash", "")}


def technique_tips(results: list[HitResult], limit: int = 2) -> list[str]:
    """Short, most important technique observations from one pass."""
    from keyfall.ai.technique_feedback import analyze
    try:
        insights = analyze(results)
    except Exception:
        return []
    insights.sort(key=lambda i: i.severity, reverse=True)
    return [i.message for i in insights[:limit]]


@dataclass
class CoachPass:
    """Handed from Practice back to the Coach screen after one step."""

    step: CoachStep
    accuracy: float
    seconds: float
    hits: list[HitResult] = field(default_factory=list)
    completed: bool = True  # False if the player left early (no verdict)
