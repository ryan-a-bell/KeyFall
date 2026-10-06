"""Where KeyFall keeps the player's data, and the identity helpers sync relies on.

Everything lives under one folder, ``~/.keyfall`` by default (set ``KEYFALL_HOME``
to move it):

    progress.db      play history (SQLite)
    settings.json    settings, one section per area
    coach/           Practice Coach state, one JSON file per song
    recordings/      Free Play recordings
    device.json      this install's random device id
    sync.json        sync bookkeeping (cursor, last push), only once signed in

Records that may sync between devices carry a stable id (a UUID, or a song's
content hash) and a UTC ``updated_at`` stamp, so two devices can merge their data
without clashing. See ``docs/plans/0018_accounts_and_sync.md``.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import uuid
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("KEYFALL_HOME") or Path.home() / ".keyfall")


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string (sortable, timezone-explicit)."""
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="microseconds")


def new_id() -> str:
    return str(uuid.uuid4())


def device_id(folder: Path | None = None) -> str:
    """This install's id, created on first use. Not tied to the player or the machine."""
    path = (folder or data_dir()) / "device.json"
    try:
        value = json.loads(path.read_text()).get("device_id")
        if isinstance(value, str) and value:
            return value
    except (OSError, ValueError, AttributeError):
        pass
    value = new_id()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"device_id": value}, indent=2))
    return value


def file_hash(path: str | Path) -> str:
    """SHA-256 of a song file, so a song is recognized across renames and devices."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def song_key(song_hash: str, title: str) -> str:
    """Key for per-song records: the content hash when known, else the title."""
    return song_hash or f"title:{title}"
