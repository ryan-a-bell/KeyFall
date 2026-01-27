# 0008 — track_progress

## Summary

Record per-session statistics to a local SQLite database and surface improvement over time. Players should see that they're getting better.

## Module

`src/keyfall/progress.py`

## Public API

```python
class ProgressTracker:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None: ...
    def save_session(self, stats: SessionStats) -> None: ...
    def get_history(self, song_title: str | None = None, limit: int = 50) -> list[dict]: ...
    def get_best(self, song_title: str) -> dict | None: ...
    def get_streak_history(self, song_title: str) -> list[int]: ...
    def close(self) -> None: ...
```

## Detailed Design

### Database Schema

```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_title TEXT NOT NULL,
    song_hash TEXT,            -- SHA256 of file for identity across renames
    total_notes INTEGER,
    perfect INTEGER,
    good INTEGER,
    ok INTEGER,
    missed INTEGER,
    max_streak INTEGER,
    accuracy_pct REAL,
    tempo_scale REAL DEFAULT 1.0,
    hand_mode TEXT DEFAULT 'both',  -- 'left', 'right', 'both'
    wait_mode BOOLEAN DEFAULT 0,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sessions_song ON sessions(song_title);
CREATE INDEX idx_sessions_played ON sessions(played_at);
```

### Data Path

- Default: `~/.keyfall/progress.db`
- XDG-compliant on Linux: `$XDG_DATA_HOME/keyfall/progress.db`
- Configurable via settings.

### Session Recording

After the player finishes a song (or exits mid-song if > 25% complete):
1. Build `SessionStats` from `HitTracker.get_stats()`.
2. Include metadata: `tempo_scale`, `hand_mode`, `wait_mode`.
3. Call `tracker.save_session(stats)`.

### Queries

- `get_history(song_title)` — last N sessions for a song, ordered by date.
- `get_best(song_title)` — highest accuracy session.
- `get_streak_history(song_title)` — list of max streaks over time (for trend charts).

### Progress UI

A dedicated "Progress" screen showing:
1. **Song list** with best accuracy and play count.
2. **Per-song detail**: accuracy trend line chart (last 20 sessions).
3. **Overall stats**: total songs played, total notes hit, hours practiced.

Render charts with pygame drawing primitives (line graphs with `pygame.draw.lines`).

### Data Export

- `export_csv(output_path)` — dump all sessions to CSV for external analysis.
- Future: JSON export.

## Testing Plan

| Test | Assertion |
|------|-----------|
| save_session writes to DB | row count increases |
| get_history returns ordered list | most recent first |
| get_best returns highest accuracy | correct row |
| Empty DB returns empty list | no crash |
| DB file created on first use | file exists after init |
| close() is idempotent | no error on double close |

## Dependencies

- `sqlite3` (stdlib)
- Internal: `models.py`
