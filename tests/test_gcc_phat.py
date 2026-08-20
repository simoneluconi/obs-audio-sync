import numpy as np
import pytest

from obs_audio_sync.dsp.gcc_phat import gcc_phat, gcc_phat_robust, gcc_phat_with_trace
from obs_audio_sync.testing.synthetic import generate_base_signal, generate_delayed_signal

FS = 48000
DURATION = 4.0


@pytest.fixture
def base_signal():
    return generate_base_signal(DURATION, FS, seed=0)


@pytest.mark.parametrize("true_delay_sec", [0.0, 0.037, -0.12, 0.5, -1.0])
def test_gcc_phat_recovers_known_delay_clean(base_signal, true_delay_sec):
    delayed = generate_delayed_signal(base_signal, FS, delay_sec=true_delay_sec, noise_std=0.0, leakage_ratio=1.0)

    estimated_delay, confidence = gcc_phat(delayed, base_signal, FS, max_tau=2.0)

    assert estimated_delay == pytest.approx(true_delay_sec, abs=1e-3)
    assert confidence > 0.5


def test_gcc_phat_robust_to_noise_and_partial_leakage(base_signal):
    true_delay_sec = 0.213
    delayed = generate_delayed_signal(
        base_signal,
        FS,
        delay_sec=true_delay_sec,
        noise_std=0.15,
        leakage_ratio=0.5,
        seed=7,
    )

    estimated_delay, confidence = gcc_phat(delayed, base_signal, FS, max_tau=2.0)

    assert estimated_delay == pytest.approx(true_delay_sec, abs=1e-3)
    assert confidence > 0.15


def test_gcc_phat_uncorrelated_signals_low_confidence():
    rng = np.random.default_rng(42)
    sig = rng.standard_normal(int(DURATION * FS))
    ref = rng.standard_normal(int(DURATION * FS))

    _, confidence = gcc_phat(sig, ref, FS, max_tau=2.0)

    assert confidence < 0.3


def test_gcc_phat_respects_max_tau(base_signal):
    # True delay well beyond max_tau: the estimate must still stay within the search range.
    delayed = generate_delayed_signal(base_signal, FS, delay_sec=1.8, noise_std=0.0, leakage_ratio=1.0)

    estimated_delay, _ = gcc_phat(delayed, base_signal, FS, max_tau=0.5)

    assert abs(estimated_delay) <= 0.5 + 1e-6


def test_gcc_phat_rejects_empty_signal():
    with pytest.raises(ValueError):
        gcc_phat(np.array([]), np.array([1.0, 2.0]), FS)


def test_gcc_phat_with_trace_matches_gcc_phat_estimate(base_signal):
    true_delay_sec = 0.037
    delayed = generate_delayed_signal(base_signal, FS, delay_sec=true_delay_sec, noise_std=0.0, leakage_ratio=1.0)

    delay_sec, confidence = gcc_phat(delayed, base_signal, FS, max_tau=2.0)
    trace_delay_sec, trace_confidence, trace = gcc_phat_with_trace(delayed, base_signal, FS, max_tau=2.0)

    assert trace_delay_sec == pytest.approx(delay_sec)
    assert trace_confidence == pytest.approx(confidence)
    assert len(trace.lags_sec) == len(trace.values)
    assert len(trace.lags_sec) > 1
    # The trace peak should land at (or very near) the estimated delay.
    peak_lag = trace.lags_sec[np.argmax(trace.values)]
    assert peak_lag == pytest.approx(true_delay_sec, abs=1e-3)
    assert np.max(trace.values) == pytest.approx(1.0)


def test_gcc_phat_with_trace_is_capped_to_max_points():
    rng = np.random.default_rng(0)
    sig = rng.standard_normal(int(DURATION * FS))

    _, _, trace = gcc_phat_with_trace(sig, sig, FS, max_tau=2.0, trace_half_window_sec=0.05, trace_max_points=200)

    assert len(trace.lags_sec) <= 201


@pytest.mark.parametrize("true_delay_sec", [0.0, 0.037, -0.12, 0.5])
def test_gcc_phat_robust_recovers_known_delay_on_clean_signal(base_signal, true_delay_sec):
    delayed = generate_delayed_signal(base_signal, FS, delay_sec=true_delay_sec, noise_std=0.0, leakage_ratio=1.0)

    estimated_delay, confidence = gcc_phat_robust(delayed, base_signal, FS, max_tau=2.0, num_segments=4)

    assert estimated_delay == pytest.approx(true_delay_sec, abs=1e-3)
    assert confidence > 0.3


def test_gcc_phat_robust_reports_zero_confidence_when_segments_disagree():
    # Simulates the real-hardware failure mode: two halves of the capture
    # window each have their own strong but mutually inconsistent delay
    # (e.g. one segment locks onto a reverb/periodicity artifact) — a
    # single full-window GCC-PHAT pass would confidently report ONE of
    # these as if it were reliable. The robust estimator must instead
    # recognize the disagreement and report near-zero confidence.
    base = generate_base_signal(2.0, FS, seed=1)
    half_a = generate_delayed_signal(base, FS, delay_sec=0.05, noise_std=0.0, leakage_ratio=1.0, seed=10)
    half_b = generate_delayed_signal(base, FS, delay_sec=0.9, noise_std=0.0, leakage_ratio=1.0, seed=11)
    sig = np.concatenate([half_a, half_b])
    ref = np.concatenate([base, base])

    delay_sec, confidence = gcc_phat_robust(sig, ref, FS, max_tau=2.0, num_segments=2, agreement_tol_sec=0.002)

    assert confidence == pytest.approx(0.0)


def test_gcc_phat_robust_ignores_a_single_outlier_segment(base_signal):
    # 3 of 4 segments agree on the true delay; 1 is a spurious outlier
    # (as seen on real hardware). The robust estimate should follow the
    # majority, not average in the outlier.
    true_delay_sec = 0.08
    n = len(base_signal)
    quarter = n // 4
    sig = generate_delayed_signal(base_signal, FS, delay_sec=true_delay_sec, noise_std=0.0, leakage_ratio=1.0, seed=3)
    outlier_quarter = generate_delayed_signal(
        base_signal[:quarter], FS, delay_sec=1.5, noise_std=0.0, leakage_ratio=1.0, seed=4
    )
    sig = np.concatenate([outlier_quarter, sig[quarter:]])

    delay_sec, confidence = gcc_phat_robust(sig, base_signal, FS, max_tau=2.0, num_segments=4)

    assert delay_sec == pytest.approx(true_delay_sec, abs=1e-3)
    # 3 of 4 (clean, high-confidence) segments agree: expect a confidence
    # around 0.75 * (their average confidence), clearly above zero.
    assert confidence > 0.4


def test_gcc_phat_robust_falls_back_to_plain_gcc_phat_for_short_signals(base_signal):
    true_delay_sec = 0.02
    delayed = generate_delayed_signal(base_signal, FS, delay_sec=true_delay_sec, noise_std=0.0, leakage_ratio=1.0)

    plain_delay, plain_confidence = gcc_phat(delayed, base_signal, FS, max_tau=2.0)
    robust_delay, robust_confidence = gcc_phat_robust(delayed, base_signal, FS, max_tau=2.0, num_segments=100)

    assert robust_delay == pytest.approx(plain_delay)
    assert robust_confidence == pytest.approx(plain_confidence)


def test_gcc_phat_robust_recovers_delay_from_sparse_transients(base_signal):
    # Regression test for a real-hardware bug: content isn't necessarily
    # spread evenly across the window (e.g. a couple of sharp claps in an
    # otherwise near-silent capture). Segments containing no correlated
    # content report a meaningless peak; voting them in anyway used to
    # dilute an otherwise-clear consensus from the segments that actually
    # had signal. Only 2 of 8 segments here carry real correlated content;
    # the rest are near-silent noise.
    true_delay_sec = 0.138
    n = len(base_signal)
    eighth = n // 8
    rng = np.random.default_rng(99)

    quiet = rng.normal(0.0, 1e-4, size=n).astype(np.float64)
    sig = quiet.copy()
    for start in (eighth, 5 * eighth):  # 2 of 8 segments get a real, delayed transient
        burst = generate_delayed_signal(
            base_signal[start : start + eighth], FS, delay_sec=true_delay_sec, noise_std=0.0, leakage_ratio=1.0, seed=5
        )
        sig[start : start + eighth] = burst

    delay_sec, confidence = gcc_phat_robust(sig, base_signal, FS, max_tau=2.0, num_segments=8, min_segment_confidence=0.2)

    assert delay_sec == pytest.approx(true_delay_sec, abs=1e-3)
    assert confidence > 0.0


def test_gcc_phat_robust_picks_the_largest_cluster_not_the_global_median():
    # Regression test for a real-hardware bug: a plain median-of-all-
    # segments approach can land in the gap between two internally-
    # consistent clusters when neither is centered on the median — e.g. 3
    # segments confidently agreeing near the true delay and 4 *other*
    # segments each confidently landing on a *different*, mutually distant
    # value (a periodicity/reverb artifact spread across several distinct
    # far-off lags, as seen on real hardware) can pull the median away from
    # every real cluster. The true delay's cluster is still the largest
    # single group of mutually-agreeing segments and must win.
    true_delay_sec = 0.05
    base = generate_base_signal(7.0, FS, seed=2)
    n = len(base)
    seventh = n // 7

    sig = np.empty(n, dtype=np.float64)
    # 3 segments agree on the true delay.
    for i in (0, 3, 6):
        start = i * seventh
        sig[start : start + seventh] = generate_delayed_signal(
            base[start : start + seventh], FS, delay_sec=true_delay_sec, noise_std=0.0, leakage_ratio=1.0, seed=6 + i
        )
    # 4 other segments each confidently land on their own distinct,
    # mutually-distant wrong delay (never repeating the same value twice).
    wrong_delays = [-0.9, -0.6, 0.6, 0.9]
    for i, wrong_delay in zip((1, 2, 4, 5), wrong_delays):
        start = i * seventh
        sig[start : start + seventh] = generate_delayed_signal(
            base[start : start + seventh], FS, delay_sec=wrong_delay, noise_std=0.0, leakage_ratio=1.0, seed=6 + i
        )

    delay_sec, confidence = gcc_phat_robust(sig, base, FS, max_tau=2.0, num_segments=7, min_segment_confidence=0.2)

    assert delay_sec == pytest.approx(true_delay_sec, abs=1e-3)
    assert confidence > 0.0
