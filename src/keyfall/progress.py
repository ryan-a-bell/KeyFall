"""Session progress tracking with SQLite persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from keyfall.models import SessionStats

DEFAULT_DB_PATH = Path.home() / ".keyfall" / "progress.db"


class ProgressTracker:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
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
        self.conn.commit()

    def save_session(self, stats: SessionStats) -> None:
        self.conn.execute(
            """INSERT INTO sessions
               (song_title, total_notes, perfect, good, ok, missed, max_streak, accuracy_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                stats.song_title,
                stats.total_notes,
                stats.perfect,
                stats.good,
                stats.ok,
                stats.missed,
                stats.max_streak,
                stats.accuracy_pct,
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

    def close(self) -> None:
        self.conn.close()
