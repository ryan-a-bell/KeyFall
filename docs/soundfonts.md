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

## Default piano

```
keyfall --download-soundfont
```

Downloads **YDP Grand Piano** (~37 MB compressed, ~118 MB installed) into the per-user folder and verifies its SHA-256 checksum.

> YDP Grand Piano by Zenph Studios / OLPC, packaged by [FreePats](https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html). Licensed [CC-BY 3.0](https://creativecommons.org/licenses/by/3.0/).

The higher-quality Salamander Grand Piano (CC-BY 3.0, ~310 MB compressed) is also available from FreePats. Drop its `.sf2` into the per-user folder to use it.
