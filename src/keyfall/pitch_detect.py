"""Polyphonic piano note detection from audio (for playing an acoustic piano).

Pitch estimation follows Klapuri's "estimate and cancel" method
(A. Klapuri, "Multiple fundamental frequency estimation by summing harmonic
amplitudes", ISMIR 2006), in plain numpy:

1. Every ``hop`` samples, FFT the last ``window`` samples (Hann, zero-padded).
2. Spectral whitening: divide out the broad spectral envelope (per band,
   compressed by ``nu``) so low and high registers compete fairly.
3. Salience of each candidate key = weighted sum of its harmonic peaks.
4. Iteratively take the strongest key, subtract its harmonics from the
   residual spectrum, and repeat while the normalised total salience grows.
   Cancelling a note's harmonics stops its overtones being reported as notes.

A tracking layer turns per-frame pitch sets into note-on/off events: a note
starts when a key appears (or re-appears with a jump in salience after a
fresh attack), and ends after it has been absent for a few frames.

Optional guidance: when the game says which notes are expected right now,
those keys get a salience bonus and other keys a small penalty. This
"score-informed" mode is what makes practicing with a microphone reliable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from keyfall.midi_input import LiveNoteEvent

SENSITIVITY = {"low": 1.25, "normal": 1.0, "high": 0.8}  # multiplies the detection threshold


def midi_to_hz(pitch: float) -> float:
    return 440.0 * 2.0 ** ((pitch - 69) / 12.0)


@dataclass
class DetectorConfig:
    sample_rate: int = 44100
    window: int = 4096
    hop: int = 512
    fft_size: int = 8192
    lowest: int = 36  # C2
    highest: int = 96  # C7
    harmonics: int = 20
    weight_norm: float = 1.0  # divide salience by (sum of harmonic weights) ** this (0 = off)
    max_freq: float = 6000.0  # ignore partials above this
    alpha: float = 27.0  # harmonic weight g(f0, h) = (f0 + alpha) / (h * f0 + beta)
    beta: float = 320.0
    nu: float = 0.33  # whitening compression
    gamma: float = 0.85  # polyphony stopping rule: maximise sum(salience) / j**gamma
    max_polyphony: int = 6
    threshold: float = 0.12  # salience (relative to the frame's best) needed to count
    min_level_db: float = -58.0  # frame loudness gate (dBFS)
    onset_jump: float = 1.6  # salience ratio vs. recent frames that counts as a new strike
    release_frames: int = 3  # absent this many frames -> note off
    guided_bonus: float = 1.6  # salience multiplier for expected keys
    guided_penalty: float = 0.75  # and for unexpected keys while guided
    refractory_s: float = 0.09
    cancel_bins: int = 3  # bins either side of a partial removed on cancellation
    persist_frames: int = 3  # a key must be found this many frames in a row to start
    method: str = "nnls"  # "nnls" (template fitting) or "klapuri" (estimate and cancel)
    fit_max_freq: float = 5000.0
    inharmonicity: float = 0.0004  # piano partials run sharp: f_h = h*f0*sqrt(1 + B*h^2)
    candidates: int = 10  # strongest keys considered per frame (plus expected keys)
    rel_activation: float = 0.35  # a key counts if its activation >= this * the strongest
    guided_rel_activation: float = 0.05  # lower bar for expected keys
    hold_rel_activation: float = 0.08  # once sounding, a key stays on down to this
    attack_ratio: float = 2.5  # a new note must have grown this much vs. a few frames ago
    evidence_peak: float = 3.0  # a harmonic "exists" if its peak is this x its surroundings
    shared_excess: float = 1.5  # a shared partial counts if this x louder than expected
    min_sparsity: float = 0.35  # frames flatter than this (noise) can't start notes
    flux_z: float = 2.5  # spectral-flux spike (in std devs) that marks a new strike
    restrike_ratio: float = 1.3  # on a flux spike, a sounding key re-strikes if it grew this much


class PianoDetector:
    """Turns a stream of mono float samples into note-on/off events."""

    def __init__(self, config: DetectorConfig | None = None, sensitivity: str = "normal") -> None:
        self.cfg = cfg = config or DetectorConfig()
        self.sensitivity = sensitivity
        self.pitches = np.arange(cfg.lowest, cfg.highest + 1)
        self._win = np.hanning(cfg.window).astype(np.float32)
        self._buf = np.zeros(cfg.window, dtype=np.float32)
        self._leftover = np.zeros(0, dtype=np.float32)
        self._prepare()
        n = len(self.pitches)
        self._active = np.zeros(n, dtype=bool)
        self._absent = np.zeros(n, dtype=int)
        self._streak = np.zeros(n, dtype=int)  # consecutive frames each key was found
        self._recent = np.zeros((4, n))  # recent activations (attack / re-strike detection)
        self._last_on = np.full(n, -1e9)
        self._last_y: np.ndarray | None = None
        self._prev_logy: np.ndarray | None = None
        self._flux_stats = (0.0, 1.0)  # running mean / variance of spectral flux
        self._flux_onset = False
        self.sparsity = 0.0
        self._frames = 0
        self.expected: set[int] | None = None  # None = unguided
        self.level_db = -120.0  # loudness of the last frame (for a level meter)
        self.time_s = 0.0  # stream time of the last processed frame

    # ------------------------------------------------------------------ setup
    def _prepare(self) -> None:
        cfg = self.cfg
        bin_hz = cfg.sample_rate / cfg.fft_size
        n_bins = cfg.fft_size // 2 + 1
        freqs = np.arange(n_bins) * bin_hz
        self._freqs = freqs

        # whitening bands: 30 overlapping triangles, log-spaced 50 Hz .. 6.4 kHz
        centres = np.geomspace(50.0, 6400.0, 30)
        self._white_centres = centres
        tri = np.zeros((len(centres), n_bins))
        for b, c in enumerate(centres):
            lo = centres[b - 1] if b > 0 else c / 1.2
            hi = centres[b + 1] if b < len(centres) - 1 else c * 1.2
            up = (freqs - lo) / (c - lo)
            down = (hi - freqs) / (hi - c)
            tri[b] = np.clip(np.minimum(up, down), 0, 1)
        self._tri = tri
        self._tri_norm = np.maximum(tri.sum(axis=1), 1e-9)

        # harmonic bands per (key, harmonic): +-40 cents, at least one bin
        half = 2 ** (0.4 / 12)
        rows, weights, owner = [], [], []
        for i, p in enumerate(self.pitches):
            f0 = midi_to_hz(p)
            for h in range(1, cfg.harmonics + 1):
                fh = f0 * h
                if fh > cfg.max_freq:
                    break
                lo = int(np.floor(fh / half / bin_hz))
                hi = max(int(np.ceil(fh * half / bin_hz)), lo + 1)
                rows.append((lo, min(hi, n_bins)))
                weights.append((f0 + cfg.alpha) / (h * f0 + cfg.beta))
                owner.append(i)
        width = max(hi - lo for lo, hi in rows)
        idx = np.zeros((len(rows), width), dtype=np.int64)
        mask = np.zeros((len(rows), width), dtype=bool)
        for r, (lo, hi) in enumerate(rows):
            span = np.arange(lo, hi)
            idx[r, : len(span)] = span
            mask[r, : len(span)] = True
        self._idx, self._mask = idx, mask
        self._weights = np.array(weights)
        self._owner = np.array(owner)
        self._rows_of = [np.nonzero(self._owner == i)[0] for i in range(len(self.pitches))]
        # harmonic templates for least-squares fitting (whitened magnitude domain)
        fit_bins = int(cfg.fit_max_freq / bin_hz)
        self._fit_bins = fit_bins
        f = freqs[:fit_bins]
        templates = np.zeros((fit_bins, len(self.pitches)))
        for i, p in enumerate(self.pitches):
            f0 = midi_to_hz(p)
            for h in range(1, 31):
                fh = h * f0 * np.sqrt(1 + cfg.inharmonicity * h * h)
                if fh > cfg.fit_max_freq:
                    break
                width = max(fh * (2 ** (25 / 1200) - 1), 1.5 * bin_hz)  # ~25 cents
                templates[:, i] += (1.0 / h ** 0.5) * np.exp(-0.5 * ((f - fh) / width) ** 2)
            templates[:, i] /= np.linalg.norm(templates[:, i]) + 1e-12
        self._templates = templates
        wsum = np.bincount(self._owner, weights=self._weights, minlength=len(self.pitches))
        self._key_norm = 1.0 / np.maximum(wsum, 1e-9) ** cfg.weight_norm
        self._n_keys = len(self.pitches)

    # ------------------------------------------------------------------ stream
    def feed(self, samples: np.ndarray) -> list[LiveNoteEvent]:
        """Add samples (mono, float -1..1); returns events detected in them."""
        data = np.concatenate([self._leftover, np.asarray(samples, dtype=np.float32).ravel()])
        hop = self.cfg.hop
        events: list[LiveNoteEvent] = []
        n_hops = len(data) // hop
        for k in range(n_hops):
            self._buf = np.concatenate([self._buf[hop:], data[k * hop:(k + 1) * hop]])
            events.extend(self._process())
        self._leftover = data[n_hops * hop:]
        return events

    def _salience(self, spec: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Per-key salience and, per harmonic row, the bin holding its peak."""
        vals = np.where(self._mask, spec[self._idx], -1.0)
        arg = vals.argmax(axis=1)
        rows = np.arange(len(arg))
        peaks = vals[rows, arg]
        sal = np.bincount(self._owner, weights=self._weights * np.maximum(peaks, 0.0),
                          minlength=self._n_keys) * self._key_norm
        return sal, self._idx[rows, arg]

    def _whiten(self, frame: np.ndarray) -> np.ndarray:
        cfg = self.cfg
        x = np.abs(np.fft.rfft(frame * self._win, n=cfg.fft_size))
        sigma = np.sqrt((self._tri @ (x * x)) / self._tri_norm)
        gain = np.interp(self._freqs, self._white_centres, (sigma + 1e-12) ** (cfg.nu - 1.0))
        return gain * x

    def estimate_pitches(self, frame: np.ndarray) -> dict[int, float]:
        """Keys sounding in this frame: {key index: strength}."""
        if self.cfg.method == "nnls":
            return self._estimate_nnls(frame)
        return self._estimate_klapuri(frame)

    def _band_peak(self, y: np.ndarray, f: float, cents: float = 40.0) -> float:
        bin_hz = self.cfg.sample_rate / self.cfg.fft_size
        lo = int(f * 2 ** (-cents / 1200) / bin_hz)
        hi = int(np.ceil(f * 2 ** (cents / 1200) / bin_hz)) + 1
        return float(y[lo:hi].max()) if hi > lo and lo < len(y) else 0.0

    def _has_own_evidence(self, i: int, stronger: list[int]) -> bool:
        """Does key ``i`` show a partial that stronger keys don't already explain?

        Rejects octave/twelfth "ghosts" below or above real notes, while still
        allowing real octaves (the shared partial is then unusually loud).
        """
        y = self._last_y
        if y is None:
            return True
        bin_hz = self.cfg.sample_rate / self.cfg.fft_size
        f0 = midi_to_hz(self.pitches[i])
        for h in range(1, 5):
            fh = f0 * h
            peak = self._band_peak(y, fh)
            centre = int(round(fh / bin_hz))
            span = max(int(fh * (2 ** (1.5 / 12) - 1) / bin_hz), 8)  # wider than the peak itself
            lo, hi = max(centre - span, 0), centre + span + 1
            context = float(y[lo:hi].mean()) if hi > lo else 0.0
            if peak < self.cfg.evidence_peak * context:
                continue
            claimed = False
            for j in stronger:
                fj = midi_to_hz(self.pitches[j])
                m = round(fh / fj)
                if m >= 1 and abs(1200 * np.log2(fh / (m * fj))) < 40:
                    neighbours = [self._band_peak(y, fj * k) for k in (m - 1, m + 1) if k >= 1]
                    expected = float(np.mean(neighbours)) if neighbours else peak
                    if peak < self.cfg.shared_excess * expected:
                        claimed = True
                        break
            if not claimed:
                return True
        return False

    def _estimate_nnls(self, frame: np.ndarray) -> dict[int, float]:
        """Explain the spectrum as a non-negative mix of harmonic templates."""
        cfg = self.cfg
        y = self._whiten(frame)
        logy = np.log1p(y[: self._fit_bins] * 50.0)
        if self._prev_logy is not None:
            flux = float(np.maximum(logy - self._prev_logy, 0.0).sum())
            mean, var = self._flux_stats
            self._flux_onset = flux > mean + self.cfg.flux_z * np.sqrt(var) and flux > 1.0
            self._flux_stats = (0.95 * mean + 0.05 * flux,
                                0.95 * var + 0.05 * (flux - mean) ** 2)
        self._prev_logy = logy
        self._last_y = y
        sal, _ = self._salience(y)
        n = self._n_keys
        cand = set(np.argsort(-sal)[: cfg.candidates].tolist())
        expected_idx: set[int] = set()
        if self.expected is not None:
            expected_idx = {int(p - cfg.lowest) for p in self.expected
                            if cfg.lowest <= p <= cfg.highest}
            cand |= expected_idx
        for i in list(cand):  # let octave / neighbour keys compete for shared partials
            for d in (-12, -1, 1, 12):
                if 0 <= i + d < n:
                    cand.add(i + d)
        cand_list = sorted(cand)
        t = self._templates[:, cand_list]
        target = y[: self._fit_bins]
        a = np.maximum(t.T @ target, 1e-9)
        gram = t.T @ t
        tty = t.T @ target
        for _ in range(60):  # multiplicative NNLS updates
            a *= tty / (gram @ a + 1e-12)
        # how much of the spectrum harmonic templates explain: low for noise, high for notes
        power = target * target
        k = max(1, len(power) // 20)
        # share of energy in the loudest 5% of bins: ~0.2 for noise, much higher for notes
        self.sparsity = float(np.partition(power, -k)[-k:].sum() / (power.sum() + 1e-12))
        top = float(a.max()) if len(a) else 0.0
        if top <= 0:
            return {}
        return {i: float(a[k]) for k, i in enumerate(cand_list)}

    def _estimate_klapuri(self, frame: np.ndarray) -> dict[int, float]:
        """Klapuri iterative estimation for one frame: {key index: salience}."""
        cfg = self.cfg
        y = self._whiten(frame)
        residual = y.copy()

        bias = np.ones(self._n_keys)
        if self.expected is not None:
            bias *= cfg.guided_penalty
            bias[np.isin(self.pitches, list(self.expected))] = cfg.guided_bonus

        found: dict[int, float] = {}
        best_score = total = 0.0
        first = None
        limit = cfg.threshold * SENSITIVITY.get(self.sensitivity, 1.0)
        for j in range(1, cfg.max_polyphony + 1):
            sal, peak_bins = self._salience(residual)
            sal *= bias
            if found:
                sal[list(found)] = 0.0
            i = int(np.argmax(sal))
            s = float(sal[i])
            if first is None:
                first = s
            if s <= 0 or s < first * limit:
                break
            score = (total + s) / j ** cfg.gamma
            if score <= best_score:
                break
            best_score, total = score, total + s
            found[i] = s
            c = cfg.cancel_bins
            for k in peak_bins[self._rows_of[i]]:  # cancel this note's partials
                lo, hi = max(k - c, 0), k + c + 1
                residual[lo:hi] = np.maximum(residual[lo:hi] - y[k] * 0.9, 0.0)
        return found

    def _process(self) -> list[LiveNoteEvent]:
        cfg = self.cfg
        self._frames += 1
        self.time_s = self._frames * cfg.hop / cfg.sample_rate
        frame = self._buf
        rms = float(np.sqrt(np.mean(frame * frame)) + 1e-12)
        self.level_db = 20 * np.log10(rms)

        found = self.estimate_pitches(frame) if self.level_db > cfg.min_level_db else {}
        if cfg.method == "nnls":
            return self._track(found)
        sal = np.zeros(self._n_keys)
        for i, s in found.items():
            sal[i] = s
        recent = self._recent.max(axis=0)
        self._recent = np.roll(self._recent, 1, axis=0)
        self._recent[0] = sal

        events: list[LiveNoteEvent] = []
        now = time.time()
        found_now = sal > 0
        self._streak = np.where(found_now, self._streak + 1, 0)
        present = self._streak >= cfg.persist_frames
        self._absent = np.where(found_now, 0, self._absent + 1)
        for i in np.nonzero(self._active & (self._absent >= cfg.release_frames))[0]:
            self._active[i] = False
            events.append(LiveNoteEvent(int(self.pitches[i]), 0, now, False))
        fresh = present & ~self._active
        restrike = found_now & self._active & (recent > 0) & (sal > recent * cfg.onset_jump)
        ready = (self.time_s - self._last_on) > cfg.refractory_s
        top = max(found.values()) if found else 1.0
        for i in np.nonzero((fresh | restrike) & ready)[0]:
            if self._active[i]:
                events.append(LiveNoteEvent(int(self.pitches[i]), 0, now, False))
            self._active[i] = True
            self._last_on[i] = self.time_s
            velocity = int(np.clip(50 + 70 * sal[i] / top, 30, 120))
            events.append(LiveNoteEvent(int(self.pitches[i]), velocity, now, True))
        return events

    def _track(self, activations: dict[int, float]) -> list[LiveNoteEvent]:
        """Note on/off from per-key activations, with hysteresis and attack checks."""
        cfg = self.cfg
        act = np.zeros(self._n_keys)
        for i, v in activations.items():
            act[i] = v
        top = act.max()
        rel = act / top if top > 0 else act
        before = self._recent.min(axis=0)  # quietest of the last few frames
        self._recent = np.roll(self._recent, 1, axis=0)
        self._recent[0] = act

        limit = SENSITIVITY.get(self.sensitivity, 1.0)
        on_rel = np.full(self._n_keys, cfg.rel_activation * limit)
        if self.expected is not None:
            exp = np.isin(self.pitches, list(self.expected))
            on_rel[exp] = cfg.guided_rel_activation * limit
        strong = rel >= on_rel
        rising = act >= cfg.attack_ratio * before + 1e-12
        self._streak = np.where(strong & (rising | (self._streak > 0)), self._streak + 1, 0)

        events: list[LiveNoteEvent] = []
        now = time.time()
        holding = rel >= cfg.hold_rel_activation
        self._absent = np.where(holding, 0, self._absent + 1)
        for i in np.nonzero(self._active & (self._absent >= cfg.release_frames))[0]:
            self._active[i] = False
            events.append(LiveNoteEvent(int(self.pitches[i]), 0, now, False))
        ready = (self.time_s - self._last_on) > cfg.refractory_s
        start = (self._streak >= cfg.persist_frames) & ~self._active
        if self.sparsity < cfg.min_sparsity:  # noise, not notes
            start[:] = False
        restrike = self._active & strong & (before > 0) & (
            rising | (self._flux_onset & (act >= cfg.restrike_ratio * before)))
        order = np.argsort(-act)
        rank = {int(k): r for r, k in enumerate(order)}
        sounding = [int(k) for k in order if rel[k] >= cfg.hold_rel_activation]
        for i in np.nonzero((start | restrike) & ready)[0]:
            stronger = [j for j in sounding if rank[j] < rank[int(i)]]
            if not self._has_own_evidence(int(i), stronger):
                self._streak[i] = 0
                continue
            if self._active[i]:
                events.append(LiveNoteEvent(int(self.pitches[i]), 0, now, False))
            self._active[i] = True
            self._last_on[i] = self.time_s
            self._streak[i] = 0
            velocity = int(np.clip(45 + 75 * rel[i], 30, 120))
            events.append(LiveNoteEvent(int(self.pitches[i]), velocity, now, True))
        return events

    @property
    def latency_s(self) -> float:
        """Rough delay from key strike to detection (about half the analysis window)."""
        return (self.cfg.window / 2 + self.cfg.hop * self.cfg.persist_frames) / \
            self.cfg.sample_rate
