"""Orchestration of a full synchronization cycle: parallel audio capture
from the mapped devices, delay estimation via onset-envelope correlation
(parallel across tracks), and OBS offset resolution.

`run_full_cycle` only computes — it never writes to OBS. Writing is a
separate, explicit step via `apply_offsets`, so callers can show the user a
preview and ask for confirmation before anything changes in OBS (manual
mode), or apply only a drift-filtered subset automatically (auto mode, via
`AutoSyncController`).

No Qt dependency: usable both from the CLI and from a GUI worker. Capture
specifically goes through `capture_window_in_subprocess` rather than
`MultiDeviceRecorder` directly: opening a WASAPI stream only works from a
process's actual main thread on this platform (verified empirically), and
`run_full_cycle` is designed to be called from a background thread (e.g. a
Qt `QThreadPool` worker) so the GUI stays responsive.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np

from obs_audio_sync.audio.capture_process import capture_window_in_subprocess
from obs_audio_sync.core.models import (
    AnalysisResult,
    AppliedChange,
    CapturedAudio,
    CorrelationTrace,
    DelayResult,
    TrackConfig,
    TrackPreview,
)
from obs_audio_sync.dsp.gcc_phat import gcc_phat_with_trace
from obs_audio_sync.dsp.offsets import clamp_offset_ms, resolve_target_offsets
from obs_audio_sync.dsp.onset_align import onset_align_delay
from obs_audio_sync.dsp.preprocessing import prepare_for_correlation
from obs_audio_sync.obs.client import ObsClient
from obs_audio_sync.obs.sync_ops import get_sync_offset_ms, set_sync_offset_ms

ProgressCallback = Callable[[str], None]

_PREVIEW_MAX_POINTS = 3000


@dataclass
class SyncEngineConfig:
    # Longer than the original 4s default: a longer window gives the
    # segment-consensus estimator (see dsp.gcc_phat.gcc_phat_robust) more
    # independent chances to confirm a delay, which matters a lot for real
    # venue audio (crowd noise, PA announcements, applause) where useful
    # correlated content isn't spread evenly through time.
    capture_window_sec: float = 8.0
    max_tau_sec: float = 2.0
    confidence_threshold: float = 0.2
    target_fs: int = 48000


class SyncEngine:
    """Computes (and, on request, applies) one synchronization cycle for a
    set of tracks.

    Requires exactly one `TrackConfig` with `is_reference = True`: the
    others are compared against it via GCC-PHAT.
    """

    def __init__(
        self,
        obs_client: ObsClient,
        tracks: list[TrackConfig],
        config: SyncEngineConfig | None = None,
    ):
        if not tracks:
            raise ValueError("SyncEngine requires at least one track")
        reference_count = sum(1 for t in tracks if t.is_reference)
        if reference_count != 1:
            raise ValueError(
                f"SyncEngine requires exactly one reference track, found {reference_count}"
            )
        self._obs = obs_client
        self._tracks = tracks
        self._config = config or SyncEngineConfig()

    def run_full_cycle(
        self, progress_cb: ProgressCallback | None = None, collect_visual_data: bool = False
    ) -> AnalysisResult:
        """Capture, analyze and resolve target offsets. Never writes to OBS.

        `collect_visual_data` additionally builds downsampled waveform
        previews and correlation traces for the GUI's visual feedback
        panel — skipped by default since it costs extra CPU/memory that
        the CLI and auto-mode drift checks don't need.
        """

        def report(message: str) -> None:
            if progress_cb is not None:
                progress_cb(message)

        report("Capturing audio...")
        captured = capture_window_in_subprocess(self._tracks, self._config.capture_window_sec)

        report("Running GCC-PHAT analysis...")
        delays, track_previews = self._estimate_delays(captured, collect_visual_data)

        target_offsets_ms, rejected_track_ids = resolve_target_offsets(
            delays, self._config.confidence_threshold
        )

        return AnalysisResult(
            delays=delays,
            target_offsets_ms=target_offsets_ms,
            rejected_track_ids=rejected_track_ids,
            track_previews=track_previews,
        )

    def apply_offsets(
        self, target_offsets_ms: dict[str, float], progress_cb: ProgressCallback | None = None
    ) -> list[AppliedChange]:
        """Write the given track_id -> offset_ms values to OBS.

        Callers pass either a full `AnalysisResult.target_offsets_ms` (after
        the user confirms a preview) or a drift-filtered subset (auto mode).
        """
        if progress_cb is not None:
            progress_cb("Applying offsets to OBS...")

        track_by_id = {t.id: t for t in self._tracks}
        applied: list[AppliedChange] = []
        for track_id, new_offset_ms in target_offsets_ms.items():
            track = track_by_id[track_id]
            clamped_offset_ms, _was_clamped = clamp_offset_ms(new_offset_ms)
            previous_offset_ms = get_sync_offset_ms(self._obs, track.obs_input_name)
            set_sync_offset_ms(self._obs, track.obs_input_name, clamped_offset_ms)
            applied.append(
                AppliedChange(
                    track_id=track_id,
                    obs_input_name=track.obs_input_name,
                    previous_offset_ms=previous_offset_ms,
                    new_offset_ms=clamped_offset_ms,
                )
            )
        return applied

    def _reference_track_id(self) -> str:
        return next(t.id for t in self._tracks if t.is_reference)

    def _estimate_delays(
        self, captured: dict[str, CapturedAudio], collect_visual_data: bool
    ) -> tuple[list[DelayResult], dict[str, TrackPreview]]:
        reference_id = self._reference_track_id()
        target_fs = self._config.target_fs
        prepared = {
            track_id: prepare_for_correlation(audio.samples, audio.fs, target_fs)
            for track_id, audio in captured.items()
        }
        ref_signal = prepared[reference_id]
        other_ids = [tid for tid in prepared if tid != reference_id]

        def estimate(track_id: str) -> tuple[DelayResult, TrackPreview | None]:
            # onset_align_delay (onset-strength envelope correlation) is
            # what we actually trust for the reported delay/confidence, not
            # raw-waveform GCC-PHAT: a sustained tone or chord has no
            # unique time-delay solution under phase correlation (it
            # repeats every cycle), so GCC-PHAT — even hardened with
            # segment-consensus and spectral-flatness weighting — kept
            # confidently locking onto the wrong peak on real continuous
            # music. Onset timing doesn't have that ambiguity: this is
            # close to what professional multicam audio-sync tools (e.g.
            # PluralEyes) actually correlate. Verified on real hardware:
            # repeated captures converged to within ~1ms of each other and
            # within ~5ms of an independent transient-timing ground-truth
            # measurement, where GCC-PHAT-based approaches kept swinging
            # across hundreds of milliseconds.
            delay_sec, confidence = onset_align_delay(
                prepared[track_id], ref_signal, target_fs, max_tau=self._config.max_tau_sec
            )
            preview = None
            if collect_visual_data:
                # The full-window trace is still what we show in the UI:
                # seeing multiple comparable peaks is useful, visible
                # evidence for *why* a given estimate has low confidence.
                _full_delay, _full_confidence, trace = gcc_phat_with_trace(
                    prepared[track_id], ref_signal, target_fs, max_tau=self._config.max_tau_sec
                )
                preview = _make_preview(track_id, prepared[track_id], target_fs, trace)
            return DelayResult(track_id=track_id, delay_sec=delay_sec, confidence=confidence), preview

        delays = [DelayResult(track_id=reference_id, delay_sec=0.0, confidence=1.0)]
        track_previews: dict[str, TrackPreview] = {}
        if collect_visual_data:
            track_previews[reference_id] = _make_preview(reference_id, ref_signal, target_fs, None)

        if other_ids:
            with ThreadPoolExecutor(max_workers=len(other_ids)) as pool:
                for delay_result, preview in pool.map(estimate, other_ids):
                    delays.append(delay_result)
                    if preview is not None:
                        track_previews[delay_result.track_id] = preview

        return delays, track_previews


def _make_preview(
    track_id: str, signal: np.ndarray, fs: int, trace: CorrelationTrace | None
) -> TrackPreview:
    waveform, fs_display = _downsample_for_preview(signal, fs)
    return TrackPreview(track_id=track_id, waveform=waveform, fs_display=fs_display, correlation=trace)


def _downsample_for_preview(
    signal: np.ndarray, fs: int, max_points: int = _PREVIEW_MAX_POINTS
) -> tuple[np.ndarray, float]:
    if len(signal) <= max_points:
        return signal, float(fs)
    stride = len(signal) // max_points
    return signal[::stride], fs / stride
