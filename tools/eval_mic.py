"""Measure microphone note detection on rendered piano audio of the starter songs.

Renders each starter song with the installed piano SoundFont (FluidSynth),
feeds the audio through PianoDetector in real-time-sized chunks, and scores
detected note onsets against the true notes (pitch match, -80..+120 ms).

    python tools/eval_mic.py            # clean audio
    python tools/eval_mic.py -45        # with white noise at -45 dBFS

Needs FluidSynth and a SoundFont (Settings > Piano sound, or
`keyfall --download-soundfont`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import fluidsynth
import numpy as np

from keyfall.library import STARTER_DIR
from keyfall.pitch_detect import DetectorConfig, PianoDetector
from keyfall.song_loader import load_song
from keyfall.soundfont import find_soundfont

SR = 44100


def render(song, seconds: float, soundfont: Path) -> tuple[np.ndarray, list]:
    fs = fluidsynth.Synth(samplerate=float(SR), gain=0.5)
    sfid = fs.sfload(str(soundfont))
    fs.program_select(0, sfid, 0, 0)
    notes = [n for n in song.notes if n.start_time < seconds]
    events = sorted([(n.start_time, 1, n) for n in notes]
                    + [(n.start_time + n.duration, 0, n) for n in notes],
                    key=lambda e: (e[0], e[1]))
    out, t = [], 0.0
    for when, on, n in events + [(seconds + 1.0, 0, None)]:
        k = int((when - t) * SR)
        if k > 0:
            out.append(fs.get_samples(k))
            t += k / SR
        if n is not None:
            (fs.noteon if on else lambda c, p, v=0: fs.noteoff(c, p))(0, n.pitch, n.velocity)
    fs.delete()
    stereo = np.concatenate(out).astype(np.float32).reshape(-1, 2)
    return stereo.mean(axis=1) / 32768.0, notes


def score(path: Path, guided: bool, soundfont: Path, noise_db: float | None = None,
          seconds: float = 25.0, cfg: DetectorConfig | None = None):
    audio, notes = render(load_song(path), seconds, soundfont)
    if noise_db is not None:
        rng = np.random.default_rng(0)
        audio = audio + rng.normal(0, 10 ** (noise_db / 20), len(audio)).astype(np.float32)
    det = PianoDetector(cfg)
    truth = [(n.start_time, n.pitch) for n in notes if 36 <= n.pitch <= 96]
    found = []
    for i in range(0, len(audio), det.cfg.hop):
        if guided:
            t = i / SR
            det.expected = {n.pitch for n in notes if -0.15 <= n.start_time - t <= 0.25}
        found += [(det.time_s - det.latency_s, e.pitch)
                  for e in det.feed(audio[i:i + det.cfg.hop]) if e.is_note_on]
    used, tp = set(), 0
    for t, p in truth:
        best = None
        for k, (ft, fp) in enumerate(found):
            if k not in used and fp == p and -0.08 <= ft - t <= 0.12:
                if best is None or abs(ft - t) < abs(found[best][0] - t):
                    best = k
        if best is not None:
            used.add(best)
            tp += 1
    precision = tp / max(1, len(found))
    recall = tp / max(1, len(truth))
    return precision, recall


def main() -> None:
    soundfont = find_soundfont()
    if soundfont is None:
        sys.exit("No SoundFont found; run `keyfall --download-soundfont` first.")
    noise = float(sys.argv[1]) if len(sys.argv) > 1 else None
    for guided in (False, True):
        rows = []
        for path in sorted(STARTER_DIR.glob("*.mid")):
            p, r = score(path, guided, soundfont, noise)
            rows.append((p, r))
            print(f"{'guided' if guided else 'blind '}  {path.stem[:48]:48} P={p:.2f} R={r:.2f}")
        p, r = np.mean(rows, axis=0)
        print(f"== {'GUIDED' if guided else 'BLIND'} mean precision={p:.2f} recall={r:.2f}\n")


if __name__ == "__main__":
    main()
