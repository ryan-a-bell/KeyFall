"""Account sync: keep a player's progress the same on every device they sign in on.

KeyFall works fully offline; the files under ``~/.keyfall`` are always the source of
truth on a device. Syncing (for signed-in, paid accounts) swaps changes with a
server through a ``SyncBackend``:

1. **pull** everything the server got since our last cursor and merge it in,
2. **push** what changed here since our last push (including merge results).

What syncs, and how conflicts resolve:

==========  ======================  ==========================================
kind        key                     merge
==========  ======================  ==========================================
session     session UUID            never changes once played: union
settings    section name            newest ``updated_at`` wins (per section)
coach       song hash (or title)    union of passes; newest section progress
==========  ======================  ==========================================

The server applies the same rule to everything it's sent: an item replaces the
stored one only if its ``updated_at`` is strictly newer (sessions: only if new).
The Supabase table and function that implement this are in
``docs/supabase/schema.sql``; ``InMemoryBackend`` mirrors them for tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from keyfall import coach, settings
from keyfall.progress import ProgressTracker
from keyfall.storage import data_dir, device_id, now_iso, song_key

KINDS = ("session", "settings", "coach")


@dataclass
class SyncItem:
    kind: str  # one of KINDS
    key: str
    updated_at: str  # UTC ISO time
    payload: dict[str, Any]
    device_id: str = ""
    seq: int = 0  # set by the server: its change counter when this item was stored


class SyncBackend(Protocol):
    """The signed-in account's copy of the data on a server."""

    def pull(self, since: int) -> tuple[list[SyncItem], int]:
        """Items stored after change ``since``, and the cursor to pass next time."""
        ...

    def push(self, items: list[SyncItem]) -> None: ...


class InMemoryBackend:
    """One account's server-side storage, in memory (tests and offline development)."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], SyncItem] = {}
        self.seq = 0

    def pull(self, since: int) -> tuple[list[SyncItem], int]:
        fresh = sorted((i for i in self.items.values() if i.seq > since), key=lambda i: i.seq)
        return [SyncItem(**vars(i)) for i in fresh], self.seq

    def push(self, items: list[SyncItem]) -> None:
        for item in items:
            stored = self.items.get((item.kind, item.key))
            if stored is not None and (item.kind == "session"
                                       or item.updated_at <= stored.updated_at):
                continue
            self.seq += 1
            self.items[(item.kind, item.key)] = SyncItem(**{**vars(item), "seq": self.seq})


@dataclass
class SyncReport:
    pulled: int = 0  # items downloaded
    applied: int = 0  # of those, how many changed something here
    pushed: int = 0
    errors: list[str] = field(default_factory=list)


class SyncEngine:
    """Syncs one device's local data with a backend. Paths default to ``data_dir()``."""

    def __init__(self, backend: SyncBackend, progress: ProgressTracker,
                 folder: Path | None = None, settings_path: Path | None = None,
                 coach_dir: Path | None = None) -> None:
        self.backend = backend
        self.progress = progress
        self.folder = folder or data_dir()
        self.settings_path = settings_path or self.folder / "settings.json"
        self.coach_dir = coach_dir or self.folder / "coach"
        self.state_path = self.folder / "sync.json"
        self.device_id = device_id(self.folder)

    # ------------------------------------------------------------------ state
    def _read_state(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_state(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2))

    # ------------------------------------------------------------------ sync
    def sync(self) -> SyncReport:
        report = SyncReport()
        state = self._read_state()
        started = now_iso()

        items, cursor = self.backend.pull(int(state.get("cursor", 0)))
        report.pulled = len(items)
        for item in items:
            try:
                report.applied += self._apply(item)
            except Exception as exc:  # one bad item mustn't block the rest
                report.errors.append(f"{item.kind} {item.key}: {exc}")

        outgoing = self._changes_since(str(state.get("pushed_at", "")))
        if outgoing:
            self.backend.push(outgoing)
            self.progress.mark_synced([i.key for i in outgoing if i.kind == "session"])
        report.pushed = len(outgoing)

        self._write_state({**state, "cursor": cursor, "pushed_at": started})
        return report

    def _apply(self, item: SyncItem) -> int:
        if item.kind == "session":
            return self.progress.merge_sessions([item.payload])
        if item.kind == "settings":
            return int(settings.apply_remote_section(item.key, item.payload, item.updated_at,
                                                     self.settings_path))
        if item.kind == "coach":
            return self._apply_coach(item)
        return 0  # from a newer KeyFall; leave it on the server

    def _apply_coach(self, item: SyncItem) -> int:
        local = next((d for d in coach.read_coach_docs(self.coach_dir)
                      if _coach_key(d) == item.key), None)
        merged = coach.merge_coach_docs(local, item.payload)
        if local is not None:
            merged["song_title"] = local["song_title"]  # keep this device's file name
            if merged == local:
                return 0
        if _without_title(merged) != _without_title(item.payload):
            merged["updated_at"] = now_iso()  # has passes the server lacks: push it back
        coach.write_coach_doc(merged, self.coach_dir)
        return 1

    def _changes_since(self, pushed_at: str) -> list[SyncItem]:
        me = self.device_id
        items = [SyncItem("session", row["uuid"], row["played_at"] or "", row, me)
                 for row in self.progress.pending_sessions()]
        for name, (values, stamp) in settings.synced_sections(self.settings_path).items():
            if stamp >= pushed_at:  # first sync (pushed_at ""): unstamped ones too
                items.append(SyncItem("settings", name, stamp, values, me))
        for doc in coach.read_coach_docs(self.coach_dir):
            stamp = doc.get("updated_at", "")
            if stamp >= pushed_at:
                items.append(SyncItem("coach", _coach_key(doc), stamp, doc, me))
        return items


def _coach_key(doc: dict) -> str:
    return song_key(doc.get("song_hash", ""), doc["song_title"])


def _without_title(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "song_title"}
