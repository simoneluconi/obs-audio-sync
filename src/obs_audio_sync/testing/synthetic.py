"""Generation of synthetic signals with known delay, to validate GCC-PHAT
without needing real audio hardware."""

from __future__ import annotations

import numpy as np

from obs_audio_sync.dsp.preprocessing import apply_delay


def generate_base_signal(duration_sec: float, fs: int, seed: int = 0) -> np.ndarray:
    """Approximate pink noise (useful as a stand-in for voice/music: energy
    concentrated at low/mid frequency, unlike white noise).
    """
    rng = np.random.default_rng(seed)
    n = int(duration_sec * fs)
    white = rng.standard_normal(n)
    # Approximate 1/f filter in the frequency domain.
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    freqs[0] = freqs[1]  # avoid division by zero at DC
    pink_spectrum = spectrum / np.sqrt(freqs)
    pink = np.fft.irfft(pink_spectrum, n=n)
    return pink / (np.max(np.abs(pink)) + 1e-12)


def generate_delayed_signal(
    base: np.ndarray,
    fs: int,
    delay_sec: float,
    noise_std: float = 0.0,
    leakage_ratio: float = 1.0,
    seed: int = 1,
) -> np.ndarray:
    """Simulate a track derived from `base`, delayed by `delay_sec` and
    mixed with independent noise.

    `leakage_ratio` in [0, 1] simulates "partial leakage": how much of the
    observed signal is actually a shifted copy of `base` (e.g. the PA
    system's audio bleeding into an ambient microphone) versus independent
    noise/content (crowd noise, etc.).
    """
    rng = np.random.default_rng(seed)
    delayed = apply_delay(base, delay_sec, fs)

    independent = rng.standard_normal(len(base))
    independent /= np.max(np.abs(independent)) + 1e-12

    mixed = leakage_ratio * delayed + (1.0 - leakage_ratio) * independent
    if noise_std > 0:
        mixed = mixed + rng.normal(0.0, noise_std, size=len(mixed))
    return mixed
