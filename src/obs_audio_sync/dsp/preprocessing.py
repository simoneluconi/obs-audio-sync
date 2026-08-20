"""Preparation of captured signals before GCC-PHAT estimation."""

from __future__ import annotations

from math import gcd

import numpy as np
from scipy.signal import butter, resample_poly, sosfiltfilt


def to_mono(signal: np.ndarray) -> np.ndarray:
    """Reduce a multi-channel buffer (frames, channels) to mono by averaging channels."""
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim == 1:
        return signal
    return signal.mean(axis=1)


def resample_to(signal: np.ndarray, orig_fs: int, target_fs: int) -> np.ndarray:
    """Resample `signal` from `orig_fs` to `target_fs` using a polyphase filter.

    Necessary because different devices (USB interface, wireless receiver,
    HDMI capture card) may run at different native sample rates: cross-
    correlation requires all tracks to share the same fs.
    """
    if orig_fs == target_fs:
        return np.asarray(signal, dtype=np.float64)
    g = gcd(int(orig_fs), int(target_fs))
    up, down = target_fs // g, orig_fs // g
    return resample_poly(signal, up, down)


def remove_dc_offset(signal: np.ndarray) -> np.ndarray:
    return signal - np.mean(signal)


def apply_delay(signal: np.ndarray, delay_sec: float, fs: int) -> np.ndarray:
    """Shift `signal` by `delay_sec` (fractional, sub-sample) via linear
    interpolation. Positive `delay_sec` pushes the signal later in time.

    Used both to synthesize test signals with a known delay and, in the
    GUI, to render the "after alignment" waveform overlay by shifting a
    track's raw preview by its estimated delay.
    """
    n = len(signal)
    src_idx = np.arange(n) - delay_sec * fs
    return np.interp(src_idx, np.arange(n), signal, left=0.0, right=0.0)


def normalize_peak(signal: np.ndarray) -> np.ndarray:
    """Normalize the signal to its own absolute peak (into [-1, 1])."""
    peak = np.max(np.abs(signal))
    if peak <= 1e-12:
        return signal
    return signal / peak


def bandpass_voice_band(signal: np.ndarray, fs: int, low_hz: float = 100.0, high_hz: float = 6000.0) -> np.ndarray:
    """Filter to the typical voice/PA band, to emphasize content shared
    between tracks (e.g. the announcer's voice picked up both by the PA
    system and, via leakage, by the ambient microphones) and attenuate
    low-frequency noise (arena rumble, hum) and high-frequency content
    poorly correlated across different sources.
    """
    nyquist = fs / 2.0
    low = max(low_hz / nyquist, 1e-4)
    high = min(high_hz / nyquist, 0.999)
    sos = butter(4, [low, high], btype="bandpass", output="sos")
    return sosfiltfilt(sos, signal)


def prepare_for_correlation(
    signal: np.ndarray,
    orig_fs: int,
    target_fs: int,
    apply_bandpass: bool = False,
) -> np.ndarray:
    """Full pipeline: mono -> resample -> DC removal -> [bandpass] -> peak normalize.

    Bandpass is disabled by default: `gcc_phat`'s PHAT whitening is already
    effective at favoring phase across the whole spectrum, and narrowing
    the band can paradoxically lower the effective SNR if the content
    shared between tracks (e.g. the announcer's voice) has significant
    energy outside the typical voice band — enable it only after validating
    the benefit on real audio from the specific venue.
    """
    mono = to_mono(signal)
    resampled = resample_to(mono, orig_fs, target_fs)
    cleaned = remove_dc_offset(resampled)
    if apply_bandpass:
        cleaned = bandpass_voice_band(cleaned, target_fs)
    return normalize_peak(cleaned)
