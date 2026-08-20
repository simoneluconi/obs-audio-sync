"""Delay estimation via onset-strength envelope correlation.

Raw-waveform GCC-PHAT is fragile on tonal/periodic content: a sustained
bass note or chord has no unique time-delay solution under phase
correlation, since it repeats every cycle — the correlation can lock onto
a razor-sharp but wrong peak purely because the tone is so periodic.
Verified on real hardware: this happened repeatedly and confidently with
continuous music playing, resisting several rounds of algorithmic
hardening on top of GCC-PHAT itself.

This instead correlates each signal's *onset-strength envelope* — a
low-rate signal (~1 value per `hop_length` samples) that peaks at note/beat
attacks and is near zero during sustained, steady-state content. This is
close to what professional multicam audio-sync tools actually correlate
(structure/rhythm rather than raw phase), and it doesn't suffer the same
tonal ambiguity: even music with a strong sustained bassline has onset
timing (attacks, transients) that isn't purely periodic at the phrase
level.
"""

from __future__ import annotations

import librosa
import numpy as np
from scipy.signal import correlate, correlation_lags

_EPS = 1e-12


def onset_align_delay(
    sig: np.ndarray,
    ref: np.ndarray,
    fs: int,
    max_tau: float | None = 2.0,
    hop_length: int = 512,
) -> tuple[float, float]:
    """Estimate the delay of `sig` relative to `ref` from onset timing.

    Returns (delay_sec, confidence), same sign convention as `gcc_phat`:
    delay_sec > 0 means `sig` arrived after `ref`.
    """
    sig_env = librosa.onset.onset_strength(y=np.asarray(sig, dtype=np.float32), sr=fs, hop_length=hop_length)
    ref_env = librosa.onset.onset_strength(y=np.asarray(ref, dtype=np.float32), sr=fs, hop_length=hop_length)

    # onset_strength always reports a spurious, artificially tall spike in
    # the first few frames of ANY input (there's no history yet for its
    # frame-to-frame difference) — verified directly: two completely
    # independent white-noise signals both had their single tallest onset
    # value at the exact same frame index near the start of the buffer,
    # producing a strong but musically meaningless 0-lag correlation peak
    # that swamped the real (or absent) content-driven signal. Drop that
    # startup transient from both envelopes before correlating.
    startup_frames = max(1, int(round(0.2 * fs / hop_length)))
    sig_env = sig_env[startup_frames:]
    ref_env = ref_env[startup_frames:]

    sig_env = sig_env - sig_env.mean()
    ref_env = ref_env - ref_env.mean()

    corr = correlate(sig_env, ref_env, mode="full")
    lags = correlation_lags(len(sig_env), len(ref_env), mode="full")

    frame_rate = fs / hop_length
    if max_tau is not None:
        max_lag_frames = max(1, int(round(max_tau * frame_rate)))
        mask = np.abs(lags) <= max_lag_frames
        corr = corr[mask]
        lags = lags[mask]

    abs_corr = np.abs(corr)
    if abs_corr.size == 0:
        return 0.0, 0.0

    peak_idx = int(np.argmax(abs_corr))
    peak_val = abs_corr[peak_idx]
    fractional_offset = _refine_peak_quadratic(abs_corr, peak_idx)
    delay_sec = (float(lags[peak_idx]) + fractional_offset) / frame_rate

    confidence = _peak_to_sidelobe_confidence(abs_corr, peak_idx, peak_val)
    return delay_sec, confidence


def _refine_peak_quadratic(abs_corr: np.ndarray, peak_idx: int) -> float:
    """Sub-frame peak refinement via quadratic interpolation of the 3
    samples around the peak. Matters here more than it would for
    `gcc_phat`: onset envelope frames are ~10ms apart (at the default
    hop_length), a coarse native resolution compared to raw-audio-sample
    correlation.
    """
    if peak_idx <= 0 or peak_idx >= len(abs_corr) - 1:
        return 0.0
    y0, y1, y2 = abs_corr[peak_idx - 1], abs_corr[peak_idx], abs_corr[peak_idx + 1]
    denom = y0 - 2 * y1 + y2
    if abs(denom) < _EPS:
        return 0.0
    return float(0.5 * (y0 - y2) / denom)


def _peak_to_sidelobe_confidence(abs_corr: np.ndarray, peak_idx: int, peak_val: float) -> float:
    if peak_val <= _EPS:
        return 0.0
    exclusion = max(1, len(abs_corr) // 50)
    masked = abs_corr.copy()
    lo = max(0, peak_idx - exclusion)
    hi = min(len(masked), peak_idx + exclusion + 1)
    masked[lo:hi] = 0.0
    second_val = float(np.max(masked)) if masked.size else 0.0
    confidence = 1.0 - (second_val / peak_val)
    return float(np.clip(confidence, 0.0, 1.0))
