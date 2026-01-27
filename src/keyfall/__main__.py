"""Entry point for `python -m keyfall` or the `keyfall` console script."""

from keyfall.app import App


def main() -> None:
    app = App()
    app.run()


if __name__ == "__main__":
    main()
