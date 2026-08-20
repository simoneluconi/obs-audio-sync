"""Relative delay estimation between two audio signals via GCC-PHAT.

GCC-PHAT (Generalized Cross-Correlation with PHAse Transform) is robust to
the background noise and reverberation typical of an environment like a
sports arena, because it whitens the cross-correlation spectrum before
searching for its peak: it counts on phase (where the delay shows up), not
amplitude (which ambient noise heavily distorts).
"""

from __future__ import annotations

import numpy as np
from scipy.fft import irfft, next_fast_len, rfft

from obs_audio_sync.core.models import CorrelationTrace

_EPS = 1e-12


def gcc_phat(
    sig: np.ndarray,
    ref: np.ndarray,
    fs: int,
    max_tau: float | None = 2.0,
    interp: int = 16,
) -> tuple[float, float]:
    """Estimate the delay of `sig` relative to `ref`.

    Returns (delay_sec, confidence):
      - delay_sec > 0  => `sig` arrived AFTER `ref` (it is delayed).
      - delay_sec < 0  => `sig` arrived BEFORE `ref` (it is ahead).
      - confidence in [0, 1], the peak-to-sidelobe ratio of the PHAT
        cross-correlation: how much the main peak dominates the second
        local peak. Low values indicate an unreliable estimate (e.g.
        uncorrelated signals).

    `max_tau` limits the peak search to +/- max_tau seconds, useful both for
    speed and to avoid false peaks far from the physically plausible delay.
    `interp` is the time-domain upsampling factor used to obtain sub-sample
    resolution.
    """
    delay_sec, confidence, _abs_cc, _peak_idx, _max_shift = _gcc_phat_core(sig, ref, fs, max_tau, interp)
    return delay_sec, confidence


def gcc_phat_robust(
    sig: np.ndarray,
    ref: np.ndarray,
    fs: int,
    max_tau: float | None = 2.0,
    interp: int = 16,
    num_segments: int = 8,
    agreement_tol_sec: float = 0.01,
    min_segment_confidence: float = 0.2,
) -> tuple[float, float]:
    """Delay estimate robust to spurious peaks from periodic or reverberant
    content, by finding which independent sub-windows agree with each other.

    A single GCC-PHAT pass over one capture window can lock onto the wrong
    peak: reverberation and repetitive content (music with a beat, a
    recurring phrase, echo in a large venue) produce secondary correlation
    peaks that are occasionally just as tall as — or taller than — the true
    one, purely by chance in that particular window. Verified on real
    hardware: repeated captures of the same physical setup produced wildly
    different single-window estimates even though a consistent true peak
    was present in every capture, just not always the tallest one — and
    the *wrong* peak can be just as individually "confident" as the right
    one, so filtering by a single segment's own confidence isn't enough
    either (also verified on real hardware: 4 of 8 segments confidently
    agreed with each other on a wrong ~-830ms answer while the other 3,
    equally confidently, agreed on the true ~138ms one — a plain
    median-of-all-segments approach lands in the gap between the two
    groups and reports neither).

    This splits `sig`/`ref` into `num_segments` equal chunks, runs
    `gcc_phat` on each, discards segments below `min_segment_confidence`
    (a segment that happens to contain none of the correlated content, in
    an otherwise sparse/quiet capture, reports a meaningless peak), then
    clusters the survivors by mutual agreement (within `agreement_tol_sec`).

    Each segment's vote is weighted by its *spectral flatness*, not just
    counted equally: a sustained tone or bassline (low flatness — energy
    concentrated in a few narrow bands) can produce a razor-sharp, highly
    "confident"-looking correlation peak at the wrong lag purely because
    it's so periodic, while broadband/transient content (voice, applause,
    a clap — high flatness) doesn't have that ambiguity. Verified on real
    hardware: segments landing on the true delay had consistently higher
    spectral flatness (~0.21 average) than segments landing on a wrong,
    equally "confident" periodicity-locked answer (~0.15 average) from the
    same capture. The winning cluster is whichever has the highest total
    weight (segment confidence * flatness summed across its members), not
    just whichever has the most members — a handful of genuinely broadband
    segments can (correctly) outvote a larger group of confident-but-tonal
    ones.

    Falls back to plain `gcc_phat` on the full signal when there aren't at
    least two confident segments to compare.
    """
    plain_delay, plain_confidence = gcc_phat(sig, ref, fs, max_tau=max_tau, interp=interp)

    n = min(len(sig), len(ref))
    segment_len = n // num_segments
    min_useful_len = int(fs * 0.5)
    if num_segments < 2 or segment_len < min_useful_len:
        return plain_delay, plain_confidence

    segment_delays = []
    segment_confidences = []
    segment_weights = []
    for i in range(num_segments):
        start = i * segment_len
        end = start + segment_len
        delay_sec, confidence = gcc_phat(sig[start:end], ref[start:end], fs, max_tau=max_tau, interp=interp)
        if confidence >= min_segment_confidence:
            flatness = min(_spectral_flatness(sig[start:end]), _spectral_flatness(ref[start:end]))
            segment_delays.append(delay_sec)
            segment_confidences.append(confidence)
            segment_weights.append(confidence * flatness)

    if len(segment_delays) < 2:
        # Not enough confident segments to form a consensus: the full-window
        # estimate is the best information available.
        return plain_delay, plain_confidence

    order = np.argsort(segment_delays)
    sorted_delays = np.asarray(segment_delays)[order]
    sorted_confidences = np.asarray(segment_confidences)[order]
    sorted_weights = np.asarray(segment_weights)[order]

    # Greedily chain sorted values into clusters: a new cluster starts
    # whenever the gap to the previous (sorted) value exceeds the
    # tolerance. This groups mutually-close values together regardless of
    # where the global median happens to fall.
    clusters: list[list[int]] = [[0]]
    for i in range(1, len(sorted_delays)):
        if sorted_delays[i] - sorted_delays[i - 1] <= agreement_tol_sec:
            clusters[-1].append(i)
        else:
            clusters.append([i])

    best_cluster = max(clusters, key=lambda idxs: sum(sorted_weights[idxs]))

    if len(best_cluster) < 2:
        # No two segments agree on anything: genuinely ambiguous content.
        return plain_delay, 0.0

    delay_sec = float(np.mean(sorted_delays[best_cluster]))
    agreement_ratio = len(best_cluster) / len(segment_delays)
    confidence = agreement_ratio * float(np.mean(sorted_confidences[best_cluster]))
    return delay_sec, confidence


def _spectral_flatness(signal: np.ndarray) -> float:
    """Geometric mean / arithmetic mean of the magnitude spectrum, in
    (0, 1]. Near 1 means broadband/noise-like content (a clap, applause,
    unvoiced speech); near 0 means energy concentrated in a few narrow
    bands (a sustained tone, a bassline) — exactly the kind of content
    that makes correlation-based delay estimation ambiguous, since a pure
    periodic signal has no unique time-delay solution.
    """
    spectrum = np.abs(rfft(signal * np.hanning(len(signal))))
    spectrum = spectrum[spectrum > _EPS]
    if spectrum.size == 0:
        return 0.0
    geometric_mean = np.exp(np.mean(np.log(spectrum)))
    arithmetic_mean = np.mean(spectrum)
    return float(geometric_mean / arithmetic_mean) if arithmetic_mean > _EPS else 0.0


def gcc_phat_with_trace(
    sig: np.ndarray,
    ref: np.ndarray,
    fs: int,
    max_tau: float | None = 2.0,
    interp: int = 16,
    trace_half_window_sec: float = 0.05,
    trace_max_points: int = 1500,
) -> tuple[float, float, CorrelationTrace]:
    """Same as `gcc_phat`, plus a `CorrelationTrace` for visualization.

    Kept as a separate function (rather than an optional-return-value flag
    on `gcc_phat`) so the common, high-frequency call path — CLI, auto mode
    drift checks, tests — never pays for building the trace excerpt.
    """
    delay_sec, confidence, abs_cc, peak_idx, max_shift = _gcc_phat_core(sig, ref, fs, max_tau, interp)
    trace = _extract_trace(abs_cc, peak_idx, max_shift, interp, fs, trace_half_window_sec, trace_max_points)
    return delay_sec, confidence, trace


def _gcc_phat_core(
    sig: np.ndarray,
    ref: np.ndarray,
    fs: int,
    max_tau: float | None,
    interp: int,
) -> tuple[float, float, np.ndarray, int, int]:
    """Shared implementation. Returns (delay_sec, confidence, abs_cc, peak_idx, max_shift)."""
    sig = np.asarray(sig, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    if sig.ndim != 1 or ref.ndim != 1:
        raise ValueError("gcc_phat requires 1D mono signals")
    if len(sig) == 0 or len(ref) == 0:
        raise ValueError("gcc_phat requires non-empty signals")

    n = len(sig) + len(ref)
    nfft = next_fast_len(n)

    SIG = rfft(sig, n=nfft)
    REF = rfft(ref, n=nfft)
    cross = SIG * np.conj(REF)

    # PHAT whitening: normalize by magnitude, keeping only the phase.
    cross /= np.abs(cross) + _EPS

    cc = irfft(cross, n=nfft * interp)

    max_shift = nfft * interp // 2
    if max_tau is not None:
        max_shift = min(max_shift, int(round(max_tau * fs * interp)))

    # cc[0] = lag 0; negative lags live at the tail of the array (FFT convention).
    cc = np.concatenate((cc[-max_shift:], cc[: max_shift + 1]))

    abs_cc = np.abs(cc)
    peak_idx = int(np.argmax(abs_cc))
    peak_val = abs_cc[peak_idx]

    shift = peak_idx - max_shift
    delay_sec = shift / float(interp * fs)

    confidence = _peak_to_sidelobe_confidence(abs_cc, peak_idx, peak_val)

    return delay_sec, confidence, abs_cc, peak_idx, max_shift


def _extract_trace(
    abs_cc: np.ndarray,
    peak_idx: int,
    max_shift: int,
    interp: int,
    fs: int,
    half_window_sec: float,
    max_points: int,
) -> CorrelationTrace:
    """Crop a window around the peak and, if still too dense to plot
    usefully, subsample it to at most `max_points`."""
    half_window_samples = max(1, int(round(half_window_sec * interp * fs)))
    lo = max(0, peak_idx - half_window_samples)
    hi = min(len(abs_cc), peak_idx + half_window_samples + 1)

    window = abs_cc[lo:hi]
    lags_sec = (np.arange(lo, hi) - max_shift) / float(interp * fs)

    if len(window) > max_points:
        stride = len(window) // max_points
        window = window[::stride]
        lags_sec = lags_sec[::stride]

    peak = np.max(window) if window.size else 0.0
    values = window / peak if peak > _EPS else window

    return CorrelationTrace(lags_sec=lags_sec, values=values)


def _peak_to_sidelobe_confidence(abs_cc: np.ndarray, peak_idx: int, peak_val: float) -> float:
    """Peak-to-sidelobe ratio: how much the main peak dominates the second local peak.

    Excludes a neighborhood around the main peak before searching for the
    second peak, so it doesn't just fall back on the shoulder of the same peak.
    """
    if peak_val <= _EPS:
        return 0.0

    exclusion = max(1, len(abs_cc) // 200)
    masked = abs_cc.copy()
    lo = max(0, peak_idx - exclusion)
    hi = min(len(masked), peak_idx + exclusion + 1)
    masked[lo:hi] = 0.0

    second_val = float(np.max(masked)) if masked.size else 0.0
    confidence = 1.0 - (second_val / peak_val)
    return float(np.clip(confidence, 0.0, 1.0))
