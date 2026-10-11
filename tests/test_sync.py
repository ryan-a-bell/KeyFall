"""Groundwork for account sync: ids, migrations, merging, and two devices syncing."""

import json
import sqlite3

import pytest

from keyfall import settings
from keyfall.coach import CoachState, CoachStep, merge_coach_docs, read_coach_docs
from keyfall.models import Hand, NoteEvent, SessionStats, Song, TempoChange
from keyfall.progress import ProgressTracker
from keyfall.settings import AppearanceSettings, DeviceSettings, PracticeSettings
from keyfall.song_loader import load_song
from keyfall.storage import device_id, file_hash
from keyfall.sync import InMemoryBackend, SyncEngine


class Device:
    """One install of KeyFall with its own data folder."""

    def __init__(self, folder, backend):
        self.folder = folder
        self.progress = ProgressTracker(folder / "progress.db")
        self.settings_path = folder / "settings.json"
        self.coach_dir = folder / "coach"
        self.engine = SyncEngine(backend, self.progress, folder=folder)

    def play(self, title, accuracy, song_hash=""):
        self.progress.save_session(SessionStats(song_title=title, song_hash=song_hash,
                                                total_notes=10, accuracy_pct=accuracy))

    def sync(self):
        return self.engine.sync()


@pytest.fixture
def devices(tmp_path):
    backend = InMemoryBackend()
    laptop = Device(tmp_path / "laptop", backend)
    desktop = Device(tmp_path / "desktop", backend)
    yield laptop, desktop
    laptop.progress.close()
    desktop.progress.close()


def _song(title="Tune", source_hash="abc123"):
    notes = [NoteEvent(60 + i % 4, i * 0.5, 0.4, hand=Hand.RIGHT) for i in range(16)]
    return Song(title=title, notes=notes, tempo_changes=[TempoChange(0.0, 120.0)],
                duration=8.0, source_hash=source_hash)


# ---------------------------------------------------------------------- identity
def test_device_id_is_created_once_and_kept(tmp_path):
    first = device_id(tmp_path)
    assert first and device_id(tmp_path) == first


def test_loaded_songs_carry_their_file_hash(tmp_path):
    import mido
    path = tmp_path / "a.mid"
    mid = mido.MidiFile()
    track = mido.MidiTrack([mido.Message("note_on", note=60, velocity=64, time=0),
                            mido.Message("note_off", note=60, velocity=0, time=480)])
    mid.tracks.append(track)
    mid.save(str(path))
    renamed = tmp_path / "renamed.mid"
    renamed.write_bytes(path.read_bytes())
    assert load_song(path).source_hash == file_hash(path) == load_song(renamed).source_hash


# ---------------------------------------------------------------------- progress
def test_old_progress_db_is_migrated_with_uuids(tmp_path):
    db = tmp_path / "progress.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT,
        song_title TEXT NOT NULL, total_notes INTEGER, perfect INTEGER, good INTEGER,
        ok INTEGER, missed INTEGER, max_streak INTEGER, accuracy_pct REAL,
        played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("INSERT INTO sessions (song_title, accuracy_pct, played_at) "
                 "VALUES ('Old', 80, '2025-01-02 03:04:05')")
    conn.commit()
    conn.close()

    tracker = ProgressTracker(db, device="dev-1")
    tracker.save_session(SessionStats(song_title="New", accuracy_pct=90))
    old, new = sorted(tracker.get_history(), key=lambda r: r["id"])
    assert old["uuid"] and old["device_id"] == "dev-1"
    assert old["played_at"] == "2025-01-02T03:04:05+00:00"
    assert new["uuid"] != old["uuid"] and new["played_at"] > old["played_at"]
    assert tracker.get_best("Old")["accuracy_pct"] == 80
    assert len(tracker.pending_sessions()) == 2
    tracker.close()
    ProgressTracker(db).close()  # opening again doesn't re-migrate


def test_merging_sessions_skips_known_ones(tmp_path):
    tracker = ProgressTracker(tmp_path / "p.db")
    tracker.save_session(SessionStats(song_title="A", accuracy_pct=50))
    rows = tracker.pending_sessions()
    assert tracker.merge_sessions(rows) == 0
    assert tracker.merge_sessions([{**rows[0], "uuid": "other"}]) == 1
    tracker.close()


# ---------------------------------------------------------------------- settings
def test_saving_a_section_stamps_it_and_newer_remote_wins(tmp_path):
    path = tmp_path / "s.json"
    settings.save_appearance(AppearanceSettings(theme="neon"), path)
    settings.save_devices(DeviceSettings(midi_input="My Piano"), path)
    sections = settings.synced_sections(path)
    assert set(sections) == {"appearance"}  # devices stay on this machine
    values, stamp = sections["appearance"]
    assert values["theme"] == "neon" and stamp

    older = {**values, "theme": "classic"}
    assert not settings.apply_remote_section("appearance", older, "2000-01-01", path)
    assert settings.apply_remote_section("appearance", older, "2999-01-01", path)
    assert settings.load_appearance(path).theme == "classic"
    assert not settings.apply_remote_section("devices", {}, "2999-01-01", path)


# ---------------------------------------------------------------------- coach
def test_coach_merge_keeps_every_pass_and_newest_progress():
    base = {"song_title": "T", "sections": [{"rung": "right"}], "full_run_tempo": 100}
    local = {**base, "updated_at": "2026-01-01", "history": [{"id": "a", "date": "2026-01-01"}]}
    remote = {**base, "updated_at": "2026-02-01", "sections": [{"rung": "left"}],
              "history": [{"id": "b", "date": "2026-02-01"}, {"id": "a", "date": "2026-01-01"}]}
    merged = merge_coach_docs(local, remote)
    assert merged["sections"] == [{"rung": "left"}]
    assert [r["id"] for r in merged["history"]] == ["a", "b"]
    assert merge_coach_docs(None, remote) is remote


# ---------------------------------------------------------------------- end to end
def test_two_devices_end_up_with_the_same_progress(devices):
    laptop, desktop = devices
    laptop.play("Fur Elise", 70, "h1")
    desktop.play("Fur Elise", 85, "h1")
    desktop.play("Clair de Lune", 60)

    laptop.sync()
    desktop.sync()
    laptop.sync()

    def sessions(d):
        return sorted(r["uuid"] for r in d.progress.get_history(limit=100))

    assert len(sessions(laptop)) == 3 and sessions(laptop) == sessions(desktop)
    assert laptop.progress.get_best("Fur Elise")["accuracy_pct"] == 85
    assert laptop.progress.pending_sessions() == desktop.progress.pending_sessions() == []
    assert laptop.sync().pushed == 0  # nothing new


def test_settings_follow_the_player_but_devices_do_not(devices):
    laptop, desktop = devices
    settings.save_devices(DeviceSettings(midi_input="Laptop Keys"), laptop.settings_path)
    settings.save_practice(PracticeSettings(metronome="on"), laptop.settings_path)
    laptop.sync()
    desktop.sync()
    assert settings.load_practice(desktop.settings_path).metronome == "on"
    assert settings.load_devices(desktop.settings_path).midi_input == "auto"

    settings.save_practice(PracticeSettings(metronome="off"), desktop.settings_path)
    desktop.sync()
    laptop.sync()
    assert settings.load_practice(laptop.settings_path).metronome == "off"


def test_coach_practice_on_both_devices_is_combined(devices):
    laptop, desktop = devices
    song = _song()
    step = CoachStep(1, 4, "right")

    state = CoachState.load(song, laptop.coach_dir)
    state.record_pass(step, 95, 10)
    state.save(laptop.coach_dir)
    laptop.sync()
    desktop.sync()

    state = CoachState.load(song, desktop.coach_dir)
    assert len(state.history) == 1 and state.sections[0].rung != "right"
    state.record_pass(CoachStep(1, 4, state.sections[0].rung), 50, 12)
    state.save(desktop.coach_dir)

    other = CoachState.load(song, laptop.coach_dir)  # offline practice on the laptop too
    other.record_pass(step, 40, 9)
    other.save(laptop.coach_dir)

    desktop.sync()
    laptop.sync()
    desktop.sync()

    for d in devices:
        (doc,) = read_coach_docs(d.coach_dir)
        assert len(doc["history"]) == 3
    assert json.loads(next(laptop.coach_dir.glob("*.json")).read_text())["song_hash"] == "abc123"
