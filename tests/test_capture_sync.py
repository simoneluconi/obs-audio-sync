"""Verify the start-up skew correction between streams in MultiDeviceRecorder.

We test `_align_and_trim` directly (rather than mocking the whole
sounddevice.InputStream/thread-pool stack, which would be fragile and
non-deterministic to test via real timing): it's the pure function that
implements the alignment logic, isolated from actual audio capture.
"""

import numpy as np

from obs_audio_sync.audio.capture import MultiDeviceRecorder, _StreamRecorder
from obs_audio_sync.core.models import TrackConfig

FS = 48000


def _make_recorder_instance() -> MultiDeviceRecorder:
    dummy_track = TrackConfig(id="a", display_name="a", obs_input_name="", capture_device_name="dev_a")
    return MultiDeviceRecorder([dummy_track])


def test_align_and_trim_corrects_start_skew():
    n = FS * 2
    data_a = np.arange(n, dtype=np.float32).reshape(-1, 1)
    data_b = np.arange(n, dtype=np.float32).reshape(-1, 1)

    rec_a = _StreamRecorder(track_id="a", device_name="dev_a", device_index=0, fs=FS, channels=1, frames_needed=n)
    rec_a.buffers = [data_a]
    rec_a.first_callback_time = 100.000  # started first

    rec_b = _StreamRecorder(track_id="b", device_name="dev_b", device_index=0, fs=FS, channels=1, frames_needed=n)
    rec_b.buffers = [data_b]
    rec_b.first_callback_time = 100.010  # 10ms later

    captured = _make_recorder_instance()._align_and_trim([rec_a, rec_b])

    expected_skew_samples = round(0.010 * FS)
    assert len(captured["a"].samples) == n - expected_skew_samples
    assert len(captured["b"].samples) == n
    np.testing.assert_array_equal(captured["a"].samples, data_a[expected_skew_samples:, 0])
    np.testing.assert_array_equal(captured["b"].samples, data_b[:, 0])


def test_align_and_trim_no_skew_when_started_together():
    n = FS
    data_a = np.ones((n, 1), dtype=np.float32)
    data_b = np.ones((n, 1), dtype=np.float32) * 2

    rec_a = _StreamRecorder(track_id="a", device_name="dev_a", device_index=0, fs=FS, channels=1, frames_needed=n)
    rec_a.buffers = [data_a]
    rec_a.first_callback_time = 50.0

    rec_b = _StreamRecorder(track_id="b", device_name="dev_b", device_index=0, fs=FS, channels=1, frames_needed=n)
    rec_b.buffers = [data_b]
    rec_b.first_callback_time = 50.0

    captured = _make_recorder_instance()._align_and_trim([rec_a, rec_b])

    assert len(captured["a"].samples) == n
    assert len(captured["b"].samples) == n


def test_align_and_trim_handles_multiple_buffer_chunks():
    chunk = np.ones((480, 1), dtype=np.float32)
    rec = _StreamRecorder(track_id="a", device_name="dev_a", device_index=0, fs=FS, channels=1, frames_needed=1440)
    rec.buffers = [chunk, chunk, chunk]
    rec.first_callback_time = 0.0

    captured = _make_recorder_instance()._align_and_trim([rec])

    assert len(captured["a"].samples) == 1440
