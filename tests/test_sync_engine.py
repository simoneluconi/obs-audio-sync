"""End-to-end tests for SyncEngine (simulated capture + real GCC-PHAT + simulated
OBS writes), with no real audio hardware or OBS connection."""

from types import SimpleNamespace

import numpy as np
import pytest

from obs_audio_sync.core.models import CapturedAudio, TrackConfig
from obs_audio_sync.obs.client import ObsClient
from obs_audio_sync.sync_engine import engine as engine_module
from obs_audio_sync.sync_engine.engine import SyncEngine, SyncEngineConfig
from obs_audio_sync.testing.synthetic import generate_base_signal, generate_delayed_signal

FS = 48000
KNOWN_DELAY_SEC = 0.05


class _FakeRawObsClient:
    def __init__(self, initial_offsets: dict[str, int]):
        self.set_calls: list[tuple[str, int]] = []
        self._offsets = dict(initial_offsets)

    def get_input_audio_sync_offset(self, name):
        return SimpleNamespace(input_audio_sync_offset=self._offsets[name])

    def set_input_audio_sync_offset(self, name, offset):
        self.set_calls.append((name, offset))
        self._offsets[name] = offset


def _make_obs_client(fake_raw: _FakeRawObsClient) -> ObsClient:
    client = ObsClient(host="localhost", port=4455)
    client._client = fake_raw  # bypasses connect(): no real websocket in tests
    return client


def _fake_capture_window_in_subprocess(tracks: list[TrackConfig], duration_sec: float) -> dict[str, CapturedAudio]:
    """Replaces capture_window_in_subprocess: no real devices, no child process."""
    base = generate_base_signal(duration_sec, FS, seed=0)
    captured: dict[str, CapturedAudio] = {}
    for track in tracks:
        if track.is_reference:
            samples = base
        else:
            samples = generate_delayed_signal(
                base, FS, delay_sec=KNOWN_DELAY_SEC, noise_std=0.0, leakage_ratio=1.0, seed=1
            )
        captured[track.id] = CapturedAudio(track_id=track.id, samples=samples.astype(np.float32), fs=FS)
    return captured


def _make_tracks() -> list[TrackConfig]:
    return [
        TrackConfig(id="ref", display_name="ref", obs_input_name="Mic PA", capture_device_name="dev_ref", is_reference=True),
        TrackConfig(id="ambient", display_name="ambient", obs_input_name="Mic Ambient", capture_device_name="dev_ambient"),
    ]


def test_run_full_cycle_never_touches_obs(monkeypatch):
    monkeypatch.setattr(engine_module, "capture_window_in_subprocess", _fake_capture_window_in_subprocess)
    fake_raw = _FakeRawObsClient({"Mic PA": 0, "Mic Ambient": 0})
    obs_client = _make_obs_client(fake_raw)
    eng = SyncEngine(obs_client, _make_tracks(), SyncEngineConfig(capture_window_sec=2.0))

    result = eng.run_full_cycle()

    assert result.applied_changes == []
    assert result.rejected_track_ids == []
    assert fake_raw.set_calls == []

    ambient_delay = next(d for d in result.delays if d.track_id == "ambient")
    # onset-envelope correlation has coarser native resolution (~10ms at
    # the default hop_length) than sample-accurate GCC-PHAT.
    assert ambient_delay.delay_sec == pytest.approx(KNOWN_DELAY_SEC, abs=0.02)
    # "ambient" is the slowest track (50ms delay): offset 0. "ref" gets
    # delayed by 50ms to align with it.
    assert result.target_offsets_ms["ambient"] == pytest.approx(0.0, abs=5.0)
    assert result.target_offsets_ms["ref"] == pytest.approx(50.0, abs=5.0)
    assert result.track_previews == {}  # not collected unless requested


def test_run_full_cycle_collects_visual_data_when_requested(monkeypatch):
    monkeypatch.setattr(engine_module, "capture_window_in_subprocess", _fake_capture_window_in_subprocess)
    obs_client = _make_obs_client(_FakeRawObsClient({"Mic PA": 0, "Mic Ambient": 0}))
    eng = SyncEngine(obs_client, _make_tracks(), SyncEngineConfig(capture_window_sec=2.0))

    result = eng.run_full_cycle(collect_visual_data=True)

    assert set(result.track_previews) == {"ref", "ambient"}
    ref_preview = result.track_previews["ref"]
    assert ref_preview.correlation is None  # the reference has nothing to compare itself against
    assert len(ref_preview.waveform) > 0
    assert ref_preview.fs_display > 0

    ambient_preview = result.track_previews["ambient"]
    assert ambient_preview.correlation is not None
    assert len(ambient_preview.correlation.lags_sec) == len(ambient_preview.correlation.values)


def test_apply_offsets_writes_to_obs(monkeypatch):
    monkeypatch.setattr(engine_module, "capture_window_in_subprocess", _fake_capture_window_in_subprocess)
    fake_raw = _FakeRawObsClient({"Mic PA": 0, "Mic Ambient": 0})
    obs_client = _make_obs_client(fake_raw)
    eng = SyncEngine(obs_client, _make_tracks(), SyncEngineConfig(capture_window_sec=2.0))
    result = eng.run_full_cycle()

    applied = eng.apply_offsets(result.target_offsets_ms)

    assert len(applied) == 2
    applied_by_input = {c.obs_input_name: c.new_offset_ms for c in applied}
    assert applied_by_input["Mic PA"] == pytest.approx(50.0, abs=5.0)
    assert applied_by_input["Mic Ambient"] == pytest.approx(0.0, abs=5.0)
    assert fake_raw._offsets["Mic PA"] == pytest.approx(50, abs=5)
    assert fake_raw._offsets["Mic Ambient"] == pytest.approx(0, abs=5)


def test_apply_offsets_only_writes_the_given_subset(monkeypatch):
    monkeypatch.setattr(engine_module, "capture_window_in_subprocess", _fake_capture_window_in_subprocess)
    fake_raw = _FakeRawObsClient({"Mic PA": 0, "Mic Ambient": 0})
    obs_client = _make_obs_client(fake_raw)
    eng = SyncEngine(obs_client, _make_tracks(), SyncEngineConfig(capture_window_sec=2.0))

    applied = eng.apply_offsets({"ambient": 12.0})

    assert len(applied) == 1
    assert applied[0].obs_input_name == "Mic Ambient"
    assert fake_raw._offsets["Mic Ambient"] == pytest.approx(12.0)
    assert fake_raw._offsets["Mic PA"] == 0  # untouched


def test_requires_exactly_one_reference_track():
    tracks = [TrackConfig(id="a", display_name="a", obs_input_name="A", capture_device_name="d")]
    obs_client = _make_obs_client(_FakeRawObsClient({}))

    with pytest.raises(ValueError):
        SyncEngine(obs_client, tracks)


def test_requires_at_least_one_track():
    obs_client = _make_obs_client(_FakeRawObsClient({}))

    with pytest.raises(ValueError):
        SyncEngine(obs_client, [])
