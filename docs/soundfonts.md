# SoundFonts

KeyFall plays notes through FluidSynth, which needs a SoundFont (`.sf2`/`.sf3`).
SoundFonts are too large to ship in the repository, so KeyFall looks for one at startup in this order:

1. `--soundfont PATH` on the command line
2. The `KEYFALL_SOUNDFONT` environment variable
3. The per-user SoundFont folder (files with "piano" in the name are preferred)
   - Linux: `~/.local/share/keyfall/soundfonts/`
   - macOS: `~/Library/Application Support/keyfall/soundfonts/`
   - Windows: `%APPDATA%\keyfall\soundfonts\`
4. System General MIDI SoundFonts, e.g. `/usr/share/sounds/sf2/FluidR3_GM.sf2`
   (Debian/Ubuntu: `apt install fluid-soundfont-gm`)

The main menu shows which SoundFont is in use, or why sound is off.

## Downloading free SoundFonts

The easiest way is **Settings → Piano sound / Instrument sounds → Download**:
- Downloads run in the background with a progress bar.
- Each file is checked against a known SHA-256 checksum before it's installed.
- The new sound is used immediately, without a restart.

From the command line:

```
keyfall --download-soundfont          # piano (same as "piano")
keyfall --download-soundfont gm       # instruments + drums
keyfall --download-soundfont all
```

| Download | Used for | Size | License |
|---|---|---|---|
| **YDP Grand Piano** | your playing | ~37 MB (~118 MB installed) | CC-BY 3.0 |
| **MuseScore General** (`.sf3`) | backing stems: guitar, strings, bass, pads, voices, drum kit | ~40 MB | MIT |

Credits are written next to each file as `<file>.ATTRIBUTION.txt`.

> MuseScore General by S. Christian Collins, based on FluidR3 by Frank Wen and FluidR3Mono by Michael Cowgill; Temple Blocks by Ethan Winer; Drumline Cymbals by Michael Schorsch. MIT license. [Source](https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/).

> YDP Grand Piano by Zenph Studios / OLPC, packaged by [FreePats](https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html). Licensed [CC-BY 3.0](https://creativecommons.org/licenses/by/3.0/).

The higher-quality Salamander Grand Piano (CC-BY 3.0, ~310 MB compressed) is also available from FreePats. Drop its `.sf2` into the per-user folder to use it.
