# Acoustic piano (microphone) and the Practice Coach

## Playing an acoustic piano

**Settings → Microphone** → pick your microphone (or *Default mic*).
- **Level meter:** the row shows a live level meter. Play a note to test it.
- **Mic sensitivity:**
  - *Low* for noisy rooms (fewer phantom notes)
  - *High* for a quiet or distant piano (fewer missed notes)

Capture uses pygame's own audio (SDL), so there's nothing extra to install.

**Use headphones for the song's sound.** Otherwise the microphone hears KeyFall's own backing and auto-played hand.

### How it works

`src/keyfall/pitch_detect.py`, pure numpy, about 10% of one CPU core:

1. **Frequency analysis:** a 93 ms window, analysed every 11.6 ms. The spectrum is *whitened* so low and high notes compete fairly.
2. **Template fitting:** the spectrum is explained as a non-negative mix of harmonic templates, one per key (C2–C7), including the slight sharpening of a piano's upper partials. Octaves and other shared partials are resolved jointly.
3. **Note starts:** a note starts only on a real attack (its activation jumps), if the frame is tonal rather than noise, and if the key shows a partial that a louder note doesn't already explain. That rejects "ghost" octaves and twelfths.
4. **Guidance:** during a song the game tells the detector which notes are expected. Those need less evidence, which catches soft notes under a loud melody.

There's also latency correction: notes are credited at the moment they were struck (about 60 ms before detection). In wait mode, 60% of a chord is enough to continue, so one missed detection doesn't stall you.

### How well it works (measured, not guessed)

`python tools/eval_mic.py` renders all 10 starter songs with the YDP grand piano and scores the detected notes against the score (the first 25 s of each piece):

| | Precision | Recall |
|---|---|---|
| Guided (during a song) | 0.66 | 0.80 |
| Guided, with background noise at -45 dBFS | 0.62 | 0.80 |
| Unguided (free play) | 0.64 | 0.75 |

- **Best pieces:** 87–98% recall on Bach, Handel, Clair de Lune, Für Elise and Tchaikovsky.
- **Weakest:** about 45% recall on the two Chopin preludes. Soft, repeated chords under held notes are the hardest case.
- **End to end:** a *perfect* performance of the Bach Minuet in A minor, heard only through the microphone path, scored **86.7%** in the game.
- **Caveat:** these are synthesised recordings. A real piano in a real room will differ, so please try it and adjust the sensitivity.

## Practice Coach

Choose the **Coach** mode on the menu and pick a song. The Coach cuts the song into 4-bar sections and moves each one up a ladder:

```
right hand alone → left hand alone → hands together (wait mode) → real time at 60 → 70 → 80 → 90 → 100% tempo
```

- **One step:** each step is a single pass over one section. Hand rungs are skipped for sections that use only one hand.
- **After each pass:**
  - **90% or better:** next rung.
  - **Below 60%:** on a tempo rung, slow down 10%; otherwise repeat.
  - **In between:** "Once more."
- **Order:** the Coach always works on the earliest section that isn't mastered yet, then suggests a full run-through.
- **Technique tips:** on real-time rungs, tips come from `ai/technique_feedback.py`, e.g. "Right hand is consistently 58 ms late".
- **Coach screen:** shows a section map, overall % learned, today's passes and minutes, and accuracy by day.
- **Saved progress:** stored per song in `~/.keyfall/coach/<song>.json`.

Screenshots: `docs/screenshots/mic-coach/`.
