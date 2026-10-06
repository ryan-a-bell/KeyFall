"""Microphone input: detection on synthetic piano-like tones, and game integration."""

import numpy as np

from keyfall.mic_input import SAMPLE_RATE, MicInputHub
from keyfall.midi_input import NONE, LiveNoteEvent
from keyfall.models import Hand, NoteEvent, Song
from keyfall.pitch_detect import PianoDetector, midi_to_hz
from keyfall.playback import PlaybackEngine
from keyfall.views.base import ViewContext, poll_inputs


def tone(pitches, seconds=0.6, start_silence=0.3, amp=0.15):
    """Piano-like: 12 slightly sharp partials, fast attack, exponential decay."""
    n = int((start_silence + seconds) * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    out = np.zeros(n)
    on = t >= start_silence
    tt = t[on] - start_silence
    for p in pitches:
        f0 = midi_to_hz(p)
        for h in range(1, 13):
            fh = h * f0 * np.sqrt(1 + 0.0004 * h * h)
            if fh > 8000:
                break
            out[on] += amp / h * np.sin(2 * np.pi * fh * tt) * np.exp(-tt * (2 + h * 0.6))
    return out.astype(np.float32)


def detect(audio, expected=None):
    det = PianoDetector()
    det.expected = expected
    on = []
    for i in range(0, len(audio), 512):
        on += [e.pitch for e in det.feed(audio[i:i + 512]) if e.is_note_on]
    return on, det


def test_single_notes_across_the_keyboard():
    for p in (40, 52, 60, 69, 76, 88):
        found, _ = detect(tone([p]))
        assert found == [p], (p, found)


def test_c_major_chord():
    found, _ = detect(tone([60, 64, 67]))
    assert sorted(found) == [60, 64, 67]


def test_octave_is_not_reported_as_extra_note():
    found, _ = detect(tone([48]))
    assert 60 not in found and 36 not in found


def test_silence_and_noise_give_nothing():
    rng = np.random.default_rng(1)
    found, det = detect(rng.normal(0, 0.003, SAMPLE_RATE).astype(np.float32))
    assert found == []
    assert det.level_db < -40


def test_guidance_catches_a_quiet_expected_note():
    loud = tone([72], amp=0.2)
    quiet = tone([55], amp=0.04)  # 14 dB softer, like a soft left hand under a melody
    found_blind, _ = detect(loud + quiet)
    found_guided, _ = detect(loud + quiet, expected={55, 72})
    assert 55 not in found_blind  # too quiet to trust without knowing the score
    assert sorted(found_guided) == [55, 72]  # knowing it's expected, it's heard


class FakeCapture:
    def __init__(self):
        self.devices = ["USB Mic"]
        self.callback = None

    def list_devices(self):
        return self.devices

    def open(self, name, on_samples):
        self.callback = on_samples

        class Device:
            def close(self):
                pass
        return Device()


def test_hub_opens_device_and_polls_events():
    cap = FakeCapture()
    hub = MicInputHub(cap)
    assert not hub.select(NONE)
    assert hub.select("auto") and hub.port_name == "USB Mic"
    cap.callback(tone([64]))  # the capture thread delivers audio
    events = []
    while (e := hub.poll()) is not None:
        events.append(e)
    assert [e.pitch for e in events if e.is_note_on] == [64]
    assert 0.0 < hub.level <= 1.0
    assert not hub.select("Missing Mic") and "not connected" in hub.error


class ScriptedSource:
    echo = False
    connected = True
    latency_s = 0.06

    def __init__(self, events):
        self.events = list(events)
        self.expected = "unset"

    def set_expected(self, pitches):
        self.expected = pitches

    def poll(self):
        return self.events.pop(0) if self.events else None


class Audio:
    def __init__(self):
        self.on = []

    def note_on(self, pitch, velocity):
        self.on.append(pitch)

    def note_off(self, pitch):
        pass


def test_poll_inputs_corrects_latency_and_does_not_echo_mic():
    mic = ScriptedSource([LiveNoteEvent(60, 90, 0.0, True)])
    audio = Audio()
    ctx = ViewContext(screen_size=(1, 1), midi_input=None, audio=audio, progress=None,
                      mic_input=mic)
    pressed, press_pos = set(), {}
    poll_inputs(ctx, pressed, press_pos, position=2.0, expected={60, 64})
    assert pressed == {60}
    assert abs(press_pos[60] - 1.94) < 1e-9  # credited when it was really struck
    assert audio.on == []  # the acoustic piano already made the sound
    assert mic.expected == {60, 64}


def test_wait_mode_chord_tolerance_for_microphone():
    chord = [NoteEvent(p, 0.0, 1.0, hand=Hand.RIGHT) for p in (60, 64, 67)]
    engine = PlaybackEngine(Song(notes=chord + [NoteEvent(72, 2.0, 0.5)]))
    engine.wait_mode = True
    engine.update(0.01, set())
    assert engine.update(0.01, {60, 64}) == []  # strict: whole chord needed
    engine.required_fraction = 0.6
    assert len(engine.update(0.01, {60, 64})) == 3  # 2 of 3 heard is enough
    assert engine.expected_pitches(after=2.5) >= {72}
