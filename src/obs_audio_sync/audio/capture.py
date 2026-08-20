"""Simultaneous audio capture from multiple hardware devices.

PortAudio (and therefore sounddevice) does not support opening a single
stream spanning multiple physical devices at once: each device needs its
own `InputStream`. On Windows, however, opening these streams from
different Python threads reliably fails with a low-level WASAPI/WDM-KS
error (PaErrorCode -9999, WdmSyncIoctl) — verified empirically with
multiple real devices connected simultaneously. We therefore open all
streams sequentially from the calling thread: capture still happens
concurrently, because once started, callbacks are executed by PortAudio's
own internal audio threads, not by our Python thread. We correct the
start-up skew between streams by measuring the timestamp of each one's
first callback.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import numpy as np
import sounddevice as sd

from obs_audio_sync.audio.devices import find_device_by_name
from obs_audio_sync.core.exceptions import CaptureError
from obs_audio_sync.core.models import CapturedAudio, TrackConfig

_STREAM_START_TIMEOUT_MARGIN_SEC = 5.0


@dataclass
class _StreamRecorder:
    track_id: str
    device_name: str
    device_index: int
    fs: int
    channels: int
    frames_needed: int
    buffers: list[np.ndarray] = field(default_factory=list)
    first_callback_time: float | None = None
    frames_collected: int = 0
    done_event: threading.Event = field(default_factory=threading.Event)
    error: Exception | None = None

    def callback(self, indata, frames, time_info, status) -> None:
        if self.first_callback_time is None:
            self.first_callback_time = time.perf_counter()
        self.buffers.append(indata.copy())
        self.frames_collected += frames
        if self.frames_collected >= self.frames_needed:
            self.done_event.set()
            raise sd.CallbackStop


class MultiDeviceRecorder:
    """Captures an audio window from each device mapped to a track, in parallel."""

    def __init__(self, tracks: list[TrackConfig]):
        if not tracks:
            raise ValueError("MultiDeviceRecorder requires at least one track")
        self._tracks = tracks

    def capture_window(self, duration_sec: float) -> dict[str, CapturedAudio]:
        """Capture `duration_sec` seconds from each mapped device, in parallel.

        Returns {track_id: CapturedAudio}, with buffers already aligned to
        compensate for start-up skew between the streams.
        """
        recorders = [self._make_recorder(track, duration_sec) for track in self._tracks]

        streams = self._open_and_start_all(recorders)
        try:
            self._wait_for_all(recorders, duration_sec)
        finally:
            self._stop_and_close_all(streams)

        errors = [r for r in recorders if r.error is not None]
        if errors:
            first = errors[0]
            raise CaptureError(f"Capture failed for device '{first.device_name}': {first.error}")

        return self._align_and_trim(recorders)

    def _make_recorder(self, track: TrackConfig, duration_sec: float) -> _StreamRecorder:
        device = find_device_by_name(track.capture_device_name)
        if device is None:
            raise CaptureError(f"Capture device not found: '{track.capture_device_name}'")
        fs = int(device.default_samplerate)
        frames_needed = int(duration_sec * fs)
        return _StreamRecorder(
            track_id=track.id,
            device_name=device.name,
            device_index=device.index,
            fs=fs,
            channels=1,
            frames_needed=frames_needed,
        )

    def _open_and_start_all(self, recorders: list[_StreamRecorder]) -> list[sd.InputStream]:
        # Strictly sequential opening, all in the calling thread: see the
        # module docstring for why we don't use separate threads here.
        streams: list[sd.InputStream] = []
        try:
            for rec in recorders:
                stream = sd.InputStream(
                    device=rec.device_index,
                    channels=rec.channels,
                    samplerate=rec.fs,
                    callback=rec.callback,
                )
                stream.start()
                streams.append(stream)
        except Exception as exc:
            self._stop_and_close_all(streams)
            raise CaptureError(f"Could not start capture: {exc}") from exc
        return streams

    def _wait_for_all(self, recorders: list[_StreamRecorder], duration_sec: float) -> None:
        deadline = time.monotonic() + duration_sec + _STREAM_START_TIMEOUT_MARGIN_SEC
        for rec in recorders:
            remaining = max(0.0, deadline - time.monotonic())
            finished = rec.done_event.wait(timeout=remaining)
            if not finished:
                rec.error = CaptureError(
                    f"Timed out waiting for samples from device '{rec.device_name}'"
                )

    def _stop_and_close_all(self, streams: list[sd.InputStream]) -> None:
        for stream in streams:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass  # best-effort: must not mask the original error

    def _align_and_trim(self, results: list[_StreamRecorder]) -> dict[str, CapturedAudio]:
        # The stream that started first has leading audio the other,
        # later-starting streams don't have: it must be trimmed to align
        # all streams to the same time origin, i.e. the moment the SLOWEST
        # stream to start actually started (max first_callback_time).
        latest_start = max(r.first_callback_time for r in results)
        captured: dict[str, CapturedAudio] = {}
        for r in results:
            data = np.concatenate(r.buffers, axis=0)[:, 0]
            lag_sec = latest_start - r.first_callback_time
            skew_samples = max(0, int(round(lag_sec * r.fs)))
            trimmed = data[skew_samples:] if skew_samples else data
            captured[r.track_id] = CapturedAudio(
                track_id=r.track_id, samples=trimmed.astype(np.float32), fs=r.fs
            )
        return captured
