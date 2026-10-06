"""Entry point for `python -m keyfall` or the `keyfall` console script."""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="KeyFall — piano learning game")
    parser.add_argument("--songs-dir", default="", help="Directory containing MIDI/MusicXML files")
    parser.add_argument("--soundfont", default=None, help="Path to a .sf2/.sf3 SoundFont")
    parser.add_argument(
        "--theme", choices=["classic", "studio", "neon"], default=None,
        help="Visual theme for this run (overrides the saved setting)",
    )
    parser.add_argument(
        "--download-soundfont", nargs="?", const="piano", choices=["piano", "gm", "all"],
        help="Download free SoundFonts and exit: piano (YDP Grand, ~37 MB), "
             "gm (MuseScore General instruments + drums, ~40 MB), or all",
    )
    args = parser.parse_args()

    if args.download_soundfont:
        from keyfall.soundfont import DOWNLOADS, download
        keys = ["piano", "gm"] if args.download_soundfont == "all" else [args.download_soundfont]
        for key in keys:
            spec = DOWNLOADS[key]
            print(f"Downloading {spec.label} (~{spec.size_mb} MB)...")
            try:
                path = download(spec)
            except Exception as exc:
                sys.exit(f"Download failed: {exc}")
            print(f"Installed {path}\n{spec.attribution}")
        return

    from keyfall.app import App
    app = App(songs_dir=args.songs_dir, soundfont=args.soundfont, theme=args.theme)
    app.run()


if __name__ == "__main__":
    main()
