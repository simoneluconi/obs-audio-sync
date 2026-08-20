"""Shared types, free of any Qt dependency."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class CapturedAudio:
    """Mono audio buffer captured from a device, at its native sample rate."""

    track_id: str
    samples: np.ndarray
    fs: int


@dataclass(frozen=True)
class DeviceInfo:
    """An audio input device enumerated via sounddevice.

    `index` is the PortAudio index unique to this device+host-API
    combination for this session: the same device name can appear multiple
    times (MME, DirectSound, WASAPI, WDM-KS), so the index must always be
    used to open the stream, never the name alone (ambiguous for
    sounddevice itself).
    """

    index: int
    name: str
    host_api: str
    max_input_channels: int
    default_samplerate: float


@dataclass
class TrackConfig:
    """Configuration of an audio track to synchronize."""

    id: str
    display_name: str
    obs_input_name: str
    capture_device_name: str
    is_reference: bool = False


@dataclass(frozen=True)
class DelayResult:
    """GCC-PHAT delay estimate of a track relative to the reference."""

    track_id: str
    delay_sec: float
    confidence: float


@dataclass(frozen=True)
class AppliedChange:
    """A sync offset change actually written to OBS."""

    track_id: str
    obs_input_name: str
    previous_offset_ms: float
    new_offset_ms: float


@dataclass(frozen=True)
class CorrelationTrace:
    """A small, plot-friendly excerpt of a PHAT cross-correlation curve
    around its peak — normalized to [0, 1], not the full (potentially
    multi-million-sample) upsampled array."""

    lags_sec: np.ndarray
    values: np.ndarray


@dataclass(frozen=True)
class TrackPreview:
    """Downsampled, plot-friendly data for one track's visual feedback:
    a waveform preview (for the pre/post alignment overlay) and, for
    non-reference tracks, the correlation trace behind its delay estimate.
    """

    track_id: str
    waveform: np.ndarray
    fs_display: float
    correlation: CorrelationTrace | None = None


@dataclass
class AnalysisResult:
    """Full outcome of an analysis cycle (capture + estimation + offset resolution)."""

    delays: list[DelayResult] = field(default_factory=list)
    target_offsets_ms: dict[str, float] = field(default_factory=dict)
    rejected_track_ids: list[str] = field(default_factory=list)
    applied_changes: list[AppliedChange] = field(default_factory=list)
    track_previews: dict[str, TrackPreview] = field(default_factory=dict)
