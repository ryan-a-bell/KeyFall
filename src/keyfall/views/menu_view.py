"""Main menu and song picker view."""

from __future__ import annotations

from pathlib import Path

import pygame

from keyfall.renderer.skins.frames import MenuFrame, MenuSong, SongDetails
from keyfall.song_loader import HandSplitStrategy, load_song
from keyfall.stems import MIDI_SUFFIXES, StemSet, is_stem_folder
from keyfall.views.base import ViewAction, ViewContext

_KIND = {".mid": "MIDI", ".midi": "MIDI", ".xml": "MusicXML", ".musicxml": "MusicXML",
         ".mxl": "MusicXML"}


class MenuView:
    name = "menu"
    display_name = "Main Menu"

    def __init__(self) -> None:
        self._context: ViewContext | None = None
        self._song_files: list[Path] = []
        self._songs: list[MenuSong] = []
        self._details: dict[Path, SongDetails | None] = {}
        self._selected: int = 0
        self._mode: int = 0  # index into _modes
        self._modes = ["Play", "Practice", "Coach", "Free Play"]
        self._mode_targets = ["waterfall", "practice", "coach", "freeplay"]
        self._hand_splits = list(HandSplitStrategy)
        self._hand_split: int = 0  # AUTO
        self._error: str = ""
        self._clock: float = 0.0

    def on_enter(self, context: ViewContext) -> None:
        self._context = context
        ensure = getattr(context.midi_input, "ensure", None)
        if ensure:
            ensure()  # pick up a keyboard plugged in after launch
        self._details.clear()  # stem roles may have changed
        self._scan_songs()

    def on_exit(self) -> None:
        pass

    def _scan_songs(self) -> None:
        self._song_files = []
        if self._context and self._context.songs_dir:
            songs_path = Path(self._context.songs_dir)
            if songs_path.is_dir():
                entries = [f for f in songs_path.iterdir()
                           if (f.is_file() and f.suffix.lower() in _KIND) or is_stem_folder(f)]
                self._song_files = sorted(entries, key=lambda f: f.stem.lower() if f.is_file()
                                          else f.name.lower())
        progress = self._context.progress if self._context else None
        self._songs = []
        for f in self._song_files:
            title = f.name if f.is_dir() else f.stem
            best = None
            if progress is not None:
                try:
                    row = progress.get_best(title)
                    best = row["accuracy_pct"] if row else None
                except Exception:
                    best = None
            self._songs.append(MenuSong(title=title, kind=self._kind(f), best_accuracy=best))
        self._selected = min(self._selected, max(0, len(self._songs) - 1))

    @staticmethod
    def _kind(path: Path) -> str:
        if path.is_dir():
            count = sum(1 for f in path.iterdir() if f.suffix.lower() in MIDI_SUFFIXES)
            return f"Stems · {count}"
        return _KIND[path.suffix.lower()]

    def _selected_details(self) -> SongDetails | None:
        """Load and analyse the highlighted song once, on demand."""
        if not self._song_files:
            return None
        path = self._song_files[self._selected]
        if path not in self._details:
            try:
                if path.is_dir():
                    song = StemSet.load(path).combine()
                else:
                    song = load_song(path, self._hand_splits[self._hand_split])
                from keyfall.ai.difficulty import estimate
                report = estimate(song)
                self._details[path] = SongDetails(
                    duration=song.duration, note_count=len(song.notes),
                    difficulty_level=report.overall_level,
                    difficulty_label=report.overall_label,
                )
            except Exception:
                self._details[path] = None
        return self._details[path]

    def handle_event(self, event: pygame.event.Event) -> ViewAction | None:
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_ESCAPE:
            return ViewAction(kind="quit")

        count = len(self._songs)
        if event.key in (pygame.K_UP, pygame.K_LEFT):
            self._selected = max(0, self._selected - 1)
        elif event.key in (pygame.K_DOWN, pygame.K_RIGHT):
            self._selected = min(count - 1, self._selected + 1) if count else 0
        elif event.key == pygame.K_TAB:
            self._mode = (self._mode + 1) % len(self._modes)
        elif event.key == pygame.K_h:
            self._hand_split = (self._hand_split + 1) % len(self._hand_splits)
            self._details.clear()
        elif event.key == pygame.K_s:
            return ViewAction(kind="push", target="settings")
        elif event.key == pygame.K_o and self._context and self._context.songs_dir:
            from keyfall.library import open_folder
            folder = self._context.songs_dir
            self._error = "" if open_folder(folder) else f"Could not open {folder}"
        elif event.key == pygame.K_RETURN:
            return self._launch()

        return None

    def _launch(self) -> ViewAction | None:
        target = self._mode_targets[self._mode]

        if target == "freeplay":
            return ViewAction(kind="push", target="freeplay")

        if not self._song_files:
            self._error = "No songs to play. Start KeyFall with --songs-dir PATH."
            return None

        song_path = self._song_files[self._selected]
        if song_path.is_dir():
            return ViewAction(kind="push", target="stems",
                              context_patch={"stem_folder": str(song_path), "next_view": target})
        try:
            song = load_song(str(song_path), self._hand_splits[self._hand_split])
        except Exception as exc:
            self._error = str(exc)
            return None
        self._error = ""

        # push (not switch) so Esc in the song returns here instead of quitting
        return ViewAction(kind="push", target=target, context_patch={"song": song})

    def update(self, dt: float) -> ViewAction | None:
        self._clock += dt
        ctx = self._context
        if ctx is not None and ctx.ui is not None:
            ctx.ui.apply_downloads(ctx.audio)  # a download may finish after leaving Settings
        return None

    def draw(self, surface: pygame.Surface) -> None:
        ctx = self._context
        if ctx is None:
            return
        status = ctx.audio.status_text() if hasattr(ctx.audio, "status_text") else (
            ctx.audio_status or "Sound: off")
        midi = ctx.midi_input
        midi_ok = bool(getattr(midi, "connected", midi is not None))
        mic_on = bool(getattr(ctx.mic_input, "connected", False))
        midi_name = getattr(midi, "port_name", None) or "Connected"
        out = ctx.midi_output
        out_ok = bool(getattr(out, "connected", False))
        mode = ctx.ui.devices.output_mode if ctx.ui else "accompaniment"
        mode_name = {"accompaniment": "accompaniment", "lights": "key lights",
                     "both": "sound + lights"}.get(mode, mode)
        out_status = f"{out.port_name} · {mode_name}" if out_ok else "Off · sound on computer"
        ctx.skin.draw_menu(surface, MenuFrame(
            songs=self._songs,
            selected=self._selected,
            modes=self._modes,
            mode=self._mode,
            hand_split=self._hand_splits[self._hand_split].name.replace("_", " ").title(),
            audio_status=status,
            midi_status=(midi_name if midi_ok else
                         f"Mic: {ctx.mic_input.port_name}" if mic_on else
                         "Not found · using computer keys"),
            midi_connected=midi_ok or mic_on,
            sound_ok=not status.startswith("Sound: off"),
            details=self._selected_details(),
            output_status=out_status,
            output_connected=out_ok,
            mic_status=(f"Mic: {ctx.mic_input.port_name}"
                        if getattr(ctx.mic_input, "connected", False) else ""),
            error=self._error,
            songs_dir=ctx.songs_dir,
            clock=self._clock,
        ))
