# Starter songs, count-in and results

## Your songs folder

Without `--songs-dir`, KeyFall uses `~/KeyFall/Songs` (created automatically).
- **Starter songs:** the first time, 10 public-domain pieces from the Mutopia Project are copied in. They range from Bach minuets to Clair de Lune; sources are in `src/keyfall/assets/songs/SOURCES.md`.
- **Deleting them:** they won't come back. A hidden marker file records that they were added once.
- **Your own folder:** a folder that already contains music is left untouched.

Press **O** on the main menu to open the folder in your file manager. Drop in MIDI or MusicXML files, or a folder of Suno stems.

## Count-in and metronome

**Settings → Metronome**:

| Option | Behavior |
|---|---|
| **Count-in only** (default) | One bar of wood-block clicks before each song and each practice loop. The first notes fall into view during the count. |
| **Always** | Clicks every beat throughout. |
| **Off** | No clicks and no count-in. |

- **Stays in sync:** clicks follow the song's position, so they speed up and slow down with the tempo and pause while wait mode waits for you.
- **Sound:** with the instrument sounds installed they use the General MIDI wood blocks; otherwise a short high piano note.

## Results screen

When a song ends you see:
- your grade and accuracy
- your best before this run ("New best! +4.2%")
- longest streak
- a Perfect / Good / OK / Missed breakdown
- a timing chart with your average lean (early or late)
- the two bars where you missed the most notes

Buttons:
- **Practice bars X–Y** (selected by default when you missed anything) opens Practice mode looping exactly those bars.
- **Play again** (`R`)
- **Menu** (`Esc`)

## Screen layout and sheet music

**Settings → Screen layout**:

| Option | Arrangement (top to bottom) |
|---|---|
| **Notes fall · piano at bottom** (default) | sheet music → notes falling down → piano |
| **Notes rise · piano on top** | piano → notes rising up → sheet music |

**Settings → Sheet music**:
- **Practice only** (default)
- **Play and Practice**
- **Off**

Press **N** during a song to show or hide it.

To move from falling notes to reading the score, use "Notes rise" with sheet music on. The score then sits at the bottom of the screen, closest to the music on a real piano's stand. Your eyes can move from the notes to the staff as you get comfortable.

How the flip works: each theme draws the playing field (notes, lanes, hit line, keyboard, sparks) as usual, then flips that region vertically. Text inside it (note names, bar numbers, octave labels) is drawn upright at its mirrored position. Score, stats and combo stay at the far end of the notes, away from where they land.

Screenshots: `docs/screenshots/layout/`.
