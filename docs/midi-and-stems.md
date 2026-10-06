# MIDI keyboards and Suno stems

## Choosing a MIDI keyboard

Open **Settings** (`S` on the main menu) and change **MIDI keyboard**:

| Choice | Behavior |
|---|---|
| **Auto** (default) | Uses the first MIDI input found. |
| *A device name* | Always uses that keyboard. The choice survives reboots and replugging (ALSA's changing port numbers are ignored). |
| **Off (computer keys)** | Ignores MIDI; play with the computer keyboard. |

- The list is rescanned every time you change the setting, so a keyboard plugged in while KeyFall is running shows up right away.
- In **Auto**, returning to the main menu also retries automatically.
- The menu's Devices panel shows what's connected.
- The choice is saved in `~/.keyfall/settings.json` under `devices`.

## Playing a Suno song from its stems

In Suno Studio, use **Advanced Split** (or Auto Split) on your song, then **Get MIDI** for each instrument stem you want. Put all of one song's MIDI files in their own folder inside your songs directory:

```
songs/
  Neon Rain/
    Neon Rain (Bass).mid
    Neon Rain (Lead).mid
    Neon Rain (Guitar).mid
    Neon Rain (Drums).mid
```

The folder shows up in the library as one song (`Stems · 4`). Starting it opens the **Stems** screen, where each stem gets a role:

| Role | Meaning |
|---|---|
| Right hand / Left hand | You play it with that hand. |
| Both hands | You play it, split at middle C (good for a piano stem). |
| Backing | Heard but not played or scored. |
| Off | Ignored. |

KeyFall guesses roles from the file names:
- Drums are off.
- A piano/keys stem is played with both hands, and everything else becomes backing.
- Without a piano stem, the bass is the left hand and the lead/vocal line (or the highest-pitched stem) the right hand. The rest is backing.

A piano roll on the right previews the result as you change roles.

Suno's MIDI is transcribed from audio, so two options help:
- **Clean up transcription** (on by default) removes very short and very quiet ghost notes and merges double-triggered notes.
- **Snap to grid** (off by default) quantizes timing to 1/8 or 1/16 notes. Use it only if the stem's tempo is correct.

Your choices are saved next to the stems in `keyfall-stems.json`, so the song opens the same way next time.

Screenshots: `docs/screenshots/stems/`.
