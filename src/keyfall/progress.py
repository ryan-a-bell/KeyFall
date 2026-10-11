"""Session progress tracking with SQLite persistence.

Each session row has a UUID and the id of the device that played it, so rows from
several devices can be merged without clashing. Sessions never change once saved:
syncing just copies rows each device hasn't seen (``pending_sessions`` /
``mark_synced`` / ``merge_sessions``).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from keyfall.models import SessionStats
from keyfall.storage import data_dir, device_id, new_id, now_iso

DEFAULT_DB_PATH = data_dir() / "progress.db"
SCHEMA_VERSION = 2

# Columns a session carries between devices (everything but the local row id and sync flag)
SYNC_COLUMNS = ("uuid", "device_id", "song_title", "song_hash", "total_notes", "perfect",
                "good", "ok", "missed", "max_streak", "accuracy_pct", "played_at")


class ProgressTracker:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH, device: str | None = None) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.device_id = device or device_id(db_path.parent)
        self._init_db()

    def _init_db(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_title TEXT NOT NULL,
                total_notes INTEGER,
                perfect INTEGER,
                good INTEGER,
                ok INTEGER,
                missed INTEGER,
                max_streak INTEGER,
                accuracy_pct REAL,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 2:
            self._migrate_to_v2()
        self.conn.commit()

    def _migrate_to_v2(self) -> None:
        """Add sync columns; give existing rows a UUID and claim them for this device."""
        have = {row[1] for row in self.conn.execute("PRAGMA table_info(sessions)")}
        for column in ("uuid TEXT", "device_id TEXT", "song_hash TEXT DEFAULT ''",
                       "synced_at TEXT"):
            if column.split()[0] not in have:
                self.conn.execute(f"ALTER TABLE sessions ADD COLUMN {column}")
        for (row_id,) in self.conn.execute(
                "SELECT id FROM sessions WHERE uuid IS NULL").fetchall():
            self.conn.execute("UPDATE sessions SET uuid = ?, device_id = ? WHERE id = ?",
                              (new_id(), self.device_id, row_id))
        # SQLite's CURRENT_TIMESTAMP ("2026-01-02 03:04:05", UTC) -> ISO-8601 like new rows
        self.conn.execute("UPDATE sessions SET played_at = replace(played_at, ' ', 'T') "
                          "|| '+00:00' WHERE played_at NOT LIKE '%T%'")
        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS sessions_uuid ON sessions(uuid)")
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def save_session(self, stats: SessionStats) -> None:
        self.conn.execute(
            """INSERT INTO sessions
               (uuid, device_id, song_title, song_hash, total_notes, perfect, good, ok,
                missed, max_streak, accuracy_pct, played_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id(),
                self.device_id,
                stats.song_title,
                stats.song_hash,
                stats.total_notes,
                stats.perfect,
                stats.good,
                stats.ok,
                stats.missed,
                stats.max_streak,
                stats.accuracy_pct,
                now_iso(),
            ),
        )
        self.conn.commit()

    def get_history(self, song_title: str | None = None, limit: int = 50) -> list[dict]:
        if song_title:
            cur = self.conn.execute(
                "SELECT * FROM sessions WHERE song_title = ? ORDER BY played_at DESC LIMIT ?",
                (song_title, limit),
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM sessions ORDER BY played_at DESC LIMIT ?", (limit,)
            )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_best(self, song_title: str) -> dict | None:
        """Return the session with the highest accuracy for a given song, or None."""
        cur = self.conn.execute(
            "SELECT * FROM sessions WHERE song_title = ? ORDER BY accuracy_pct DESC LIMIT 1",
            (song_title,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))

    def get_streak_history(self, song_title: str) -> list[int]:
        """Return a list of max_streak values over time for a song (oldest first)."""
        cur = self.conn.execute(
            "SELECT max_streak FROM sessions WHERE song_title = ? ORDER BY played_at ASC",
            (song_title,),
        )
        return [row[0] for row in cur.fetchall()]

    # ------------------------------------------------------------------ sync
    def pending_sessions(self) -> list[dict]:
        """Sessions not yet uploaded, as plain dicts of SYNC_COLUMNS."""
        cur = self.conn.execute(
            f"SELECT {', '.join(SYNC_COLUMNS)} FROM sessions WHERE synced_at IS NULL "
            "ORDER BY id")
        return [dict(zip(SYNC_COLUMNS, row)) for row in cur.fetchall()]

    def mark_synced(self, uuids: list[str]) -> None:
        stamp = now_iso()
        self.conn.executemany("UPDATE sessions SET synced_at = ? WHERE uuid = ?",
                              [(stamp, u) for u in uuids])
        self.conn.commit()

    def merge_sessions(self, rows: list[dict]) -> int:
        """Add sessions downloaded from another device; already-known UUIDs are skipped.

        Returns how many were new.
        """
        stamp = now_iso()
        before = self.conn.total_changes
        self.conn.executemany(
            f"INSERT OR IGNORE INTO sessions ({', '.join(SYNC_COLUMNS)}, synced_at) "
            f"VALUES ({', '.join('?' * len(SYNC_COLUMNS))}, ?)",
            [tuple(row.get(c) for c in SYNC_COLUMNS) + (stamp,) for row in rows
             if row.get("uuid") and row.get("song_title") is not None])
        self.conn.commit()
        return self.conn.total_changes - before

    def close(self) -> None:
        self.conn.close()
