"""Entry point for `python -m keyfall` or the `keyfall` console script."""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="KeyFall — piano learning game")
    parser.add_argument("--songs-dir", default="", help="Directory containing MIDI/MusicXML files")
    parser.add_argument("--soundfont", default=None, help="Path to a .sf2/.sf3 SoundFont")
    parser.add_argument(
        "--download-soundfont", action="store_true",
        help="Download the default piano SoundFont (YDP Grand, ~37 MB) and exit",
    )
    args = parser.parse_args()

    if args.download_soundfont:
        from keyfall.soundfont import DEFAULT_SOUNDFONT_ATTRIBUTION, download_default_soundfont
        print("Downloading default piano SoundFont...")
        try:
            path = download_default_soundfont()
        except Exception as exc:
            sys.exit(f"Download failed: {exc}")
        print(f"Installed {path}\n{DEFAULT_SOUNDFONT_ATTRIBUTION}")
        return

    from keyfall.app import App
    app = App(songs_dir=args.songs_dir, soundfont=args.soundfont)
    app.run()


if __name__ == "__main__":
    main()
