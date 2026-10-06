"""Microphone input: play an acoustic piano and KeyFall hears the notes.

Audio is captured through SDL (pygame's own audio capture, no extra
dependencies). The capture callback only queues raw samples; detection runs
on the game thread when the input is polled, so there is no extra threading
in the analysis code.
"""

from __future__ import annotations

import collections
import threading

import numpy as np

from keyfall.midi_input import AUTO, NONE, LiveNoteEvent
from keyfall.pitch_detect import DetectorConfig, PianoDetector

SAMPLE_RATE = 44100
SENSITIVITIES = ("low", "normal", "high")


class SdlCaptureBackend:
    """Microphone capture via pygame._sdl2.audio. Any failure means "no devices"."""

    def list_devices(self) -> list[str]:
        try:
            from pygame._sdl2.audio import get_audio_device_names
            return list(get_audio_device_names(True))
        except Exception:
            return []

    def open(self, name: str | None, on_samples):
        from pygame._sdl2.audio import AUDIO_F32, AudioDevice

        def callback(_device, memory):
            on_samples(np.frombuffer(bytes(memory), dtype=np.float32).copy())

        device = AudioDevice(devicename=name, iscapture=True, frequency=SAMPLE_RATE,
                             audioformat=AUDIO_F32, numchannels=1, chunksize=512,
                             allowed_changes=0, callback=callback)
        device.pause(0)
        return device


class MicInputHub:
    """The app's microphone input. Behaves like the MIDI input hub for views.

    ``expected`` notes (set by gameplay each frame) make detection far more
    reliable; ``latency_s`` lets gameplay credit notes at the time they were
    actually struck. Player notes from the microphone are not echoed through
    the synth: the acoustic piano already makes the sound.
    """

    echo = False

    def __init__(self, backend=None, choice: str = NONE, sensitivity: str = "normal") -> None:
        self.backend = backend if backend is not None else SdlCaptureBackend()
        self.choice = choice
        self.sensitivity = sensitivity
        self.device_name: str | None = None
        self.error = ""
        self._device = None
        self._queue: collections.deque[np.ndarray] = collections.deque(maxlen=400)
        self._lock = threading.Lock()
        self._events: collections.deque[LiveNoteEvent] = collections.deque()
        self.detector = PianoDetector(DetectorConfig(sample_rate=SAMPLE_RATE), sensitivity)

    # ------------------------------------------------------------------ devices
    @property
    def connected(self) -> bool:
        return self._device is not None

    @property
    def port_name(self) -> str | None:  # same attribute name as the MIDI hubs
        return self.device_name

    def ports(self) -> list[str]:
        return self.backend.list_devices()

    def select(self, choice: str) -> bool:
        self.close()
        self.choice = choice
        self.error = ""
        if choice == NONE:
            return False
        devices = self.ports()
        if choice != AUTO and choice not in devices:
            self.error = f"{choice} is not connected" if devices else "No microphones found"
            return False
        name = None if choice == AUTO else choice
        try:
            self._device = self.backend.open(name, self._on_samples)
            self.device_name = choice if name else (devices[0] if devices else "Default microphone")
        except Exception as exc:
            self._device = None
            self.error = f"Could not open microphone: {exc}"
        self.detector = PianoDetector(DetectorConfig(sample_rate=SAMPLE_RATE), self.sensitivity)
        return self.connected

    def set_sensitivity(self, sensitivity: str) -> None:
        self.sensitivity = sensitivity
        self.detector.sensitivity = sensitivity

    def close(self) -> None:
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
        self._device = None
        self.device_name = None
        with self._lock:
            self._queue.clear()
        self._events.clear()

    # ------------------------------------------------------------------ audio
    def _on_samples(self, samples: np.ndarray) -> None:
        """Called from the capture thread: just queue the audio."""
        with self._lock:
            self._queue.append(samples)

    def feed(self, samples: np.ndarray) -> None:
        """Queue samples directly (tests, or a custom audio source)."""
        self._on_samples(np.asarray(samples, dtype=np.float32))

    def set_expected(self, pitches: set[int] | None) -> None:
        self.detector.expected = pitches

    def _analyse(self) -> None:
        with self._lock:
            chunks = list(self._queue)
            self._queue.clear()
        if chunks:
            self._events.extend(self.detector.feed(np.concatenate(chunks)))

    def poll(self) -> LiveNoteEvent | None:
        if not self._events:
            self._analyse()
        return self._events.popleft() if self._events else None

    @property
    def level(self) -> float:
        """Input loudness 0..1 for a level meter (-60 dBFS .. 0 dBFS)."""
        return float(np.clip((self.detector.level_db + 60.0) / 60.0, 0.0, 1.0))

    @property
    def latency_s(self) -> float:
        return self.detector.latency_s
