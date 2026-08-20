import numpy as np
import pytest

from obs_audio_sync.dsp.onset_align import onset_align_delay
from obs_audio_sync.testing.synthetic import generate_base_signal, generate_delayed_signal

FS = 48000
DURATION = 6.0


@pytest.fixture
def base_signal():
    return generate_base_signal(DURATION, FS, seed=0)


@pytest.mark.parametrize("true_delay_sec", [0.0, 0.05, 0.2, -0.3])
def test_onset_align_recovers_known_delay(base_signal, true_delay_sec):
    delayed = generate_delayed_signal(base_signal, FS, delay_sec=true_delay_sec, noise_std=0.0, leakage_ratio=1.0)

    delay_sec, confidence = onset_align_delay(delayed, base_signal, FS, max_tau=2.0)

    # Onset envelope frames are ~10ms apart at the default hop_length; allow
    # a bit more slack than the sample-accurate gcc_phat tests.
    assert delay_sec == pytest.approx(true_delay_sec, abs=0.02)
    assert confidence > 0.05


def test_onset_align_survives_a_dominant_sustained_tone(base_signal):
    # Reproduces the real-hardware failure mode for raw-waveform GCC-PHAT:
    # a loud, sustained, near-periodic tone (a bassline/chord held for the
    # whole window) has no unique time-delay solution under phase
    # correlation and can lock onto a wrong-but-confident peak. The onset
    # envelope should still pick up the transient content's real timing
    # since a pure sustained tone contributes almost nothing to onset
    # strength once it's already sounding.
    true_delay_sec = 0.15
    n = len(base_signal)
    t = np.arange(n) / FS
    dominant_tone = 0.9 * np.sin(2 * np.pi * 110.0 * t)  # loud sustained low A

    ref = base_signal + dominant_tone
    delayed_transients = generate_delayed_signal(base_signal, FS, delay_sec=true_delay_sec, noise_std=0.0, leakage_ratio=1.0)
    sig = delayed_transients + generate_delayed_signal(dominant_tone, FS, delay_sec=true_delay_sec, noise_std=0.0, leakage_ratio=1.0)

    delay_sec, confidence = onset_align_delay(sig, ref, FS, max_tau=2.0)

    assert delay_sec == pytest.approx(true_delay_sec, abs=0.02)
    assert confidence > 0.0


def test_onset_align_low_confidence_for_uncorrelated_signals():
    rng = np.random.default_rng(42)
    sig = rng.standard_normal(int(DURATION * FS))
    ref = rng.standard_normal(int(DURATION * FS))

    _, confidence = onset_align_delay(sig, ref, FS, max_tau=2.0)

    assert confidence < 0.5


def test_onset_align_respects_max_tau(base_signal):
    delayed = generate_delayed_signal(base_signal, FS, delay_sec=1.8, noise_std=0.0, leakage_ratio=1.0)

    delay_sec, _ = onset_align_delay(delayed, base_signal, FS, max_tau=0.5)

    assert abs(delay_sec) <= 0.5 + 0.02
