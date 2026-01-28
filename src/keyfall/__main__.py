"""Entry point for `python -m keyfall` or the `keyfall` console script."""

import argparse

from keyfall.app import App


def main() -> None:
    parser = argparse.ArgumentParser(description="KeyFall — piano learning game")
    parser.add_argument("--songs-dir", default="", help="Directory containing MIDI/MusicXML files")
    args = parser.parse_args()
    app = App(songs_dir=args.songs_dir)
    app.run()


if __name__ == "__main__":
    main()
