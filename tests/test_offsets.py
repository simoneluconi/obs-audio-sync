import pytest

from obs_audio_sync.core.models import DelayResult
from obs_audio_sync.dsp.offsets import clamp_offset_ms, resolve_target_offsets


def test_resolve_target_offsets_slowest_track_gets_zero():
    delays = [
        DelayResult(track_id="reference", delay_sec=0.0, confidence=1.0),
        DelayResult(track_id="ambient", delay_sec=0.02, confidence=0.8),
        DelayResult(track_id="camera", delay_sec=0.35, confidence=0.9),
    ]

    offsets, rejected = resolve_target_offsets(delays)

    assert rejected == []
    # The track with the largest delay (camera, 0.35s) is the "slowest": offset 0.
    assert offsets["camera"] == 0.0
    # The others get delayed until they align with the slowest one.
    assert offsets["reference"] == pytest.approx(350.0)
    assert offsets["ambient"] == pytest.approx(330.0)
    assert all(v >= 0 for v in offsets.values())


def test_resolve_target_offsets_filters_low_confidence():
    delays = [
        DelayResult(track_id="reference", delay_sec=0.0, confidence=1.0),
        DelayResult(track_id="noisy", delay_sec=0.9, confidence=0.05),
    ]

    offsets, rejected = resolve_target_offsets(delays, confidence_threshold=0.2)

    assert rejected == ["noisy"]
    assert "noisy" not in offsets
    assert offsets["reference"] == 0.0


def test_resolve_target_offsets_all_rejected_returns_empty():
    delays = [DelayResult(track_id="a", delay_sec=0.1, confidence=0.01)]

    offsets, rejected = resolve_target_offsets(delays, confidence_threshold=0.2)

    assert offsets == {}
    assert rejected == ["a"]


def test_clamp_offset_ms_within_range():
    assert clamp_offset_ms(500.0) == (500.0, False)


def test_clamp_offset_ms_negative_clamped_to_zero():
    assert clamp_offset_ms(-10.0) == (0.0, True)


def test_clamp_offset_ms_above_max_clamped():
    value, clamped = clamp_offset_ms(25000.0)
    assert clamped is True
    assert value == 20000.0
