"""Global constants and default settings."""

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FPS = 60
WINDOW_TITLE = "KeyFall"

# Piano range (standard 88 keys: A0 = MIDI 21, C8 = MIDI 108)
MIDI_NOTE_MIN = 21
MIDI_NOTE_MAX = 108

# Hit evaluation timing windows (milliseconds)
PERFECT_WINDOW_MS = 50
GOOD_WINDOW_MS = 100
OK_WINDOW_MS = 200

# Waterfall
NOTE_FALL_SPEED = 300  # pixels per second
