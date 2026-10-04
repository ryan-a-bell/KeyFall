"""Tests for SoundFont discovery."""

from keyfall import soundfont


def test_explicit_path_wins(tmp_path, monkeypatch):
    sf = tmp_path / "mine.sf2"
    sf.write_bytes(b"x")
    monkeypatch.setenv(soundfont.ENV_VAR, "/nonexistent.sf2")
    assert soundfont.find_soundfont(sf) == sf


def test_env_var_used_when_no_explicit_path(tmp_path, monkeypatch):
    sf = tmp_path / "env.sf2"
    sf.write_bytes(b"x")
    monkeypatch.setenv(soundfont.ENV_VAR, str(sf))
    assert soundfont.find_soundfont() == sf


def test_user_dir_prefers_piano_named_files(tmp_path, monkeypatch):
    monkeypatch.delenv(soundfont.ENV_VAR, raising=False)
    monkeypatch.setattr(soundfont, "user_soundfont_dir", lambda: tmp_path)
    (tmp_path / "AAA_General.sf2").write_bytes(b"x")
    (tmp_path / "YDP-GrandPiano.sf2").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("not a soundfont")
    assert soundfont.find_soundfont().name == "YDP-GrandPiano.sf2"


def test_returns_none_when_nothing_found(tmp_path, monkeypatch):
    monkeypatch.delenv(soundfont.ENV_VAR, raising=False)
    monkeypatch.setattr(soundfont, "user_soundfont_dir", lambda: tmp_path / "missing")
    monkeypatch.setattr(soundfont, "_SYSTEM_PATHS", [])
    assert soundfont.find_soundfont() is None
