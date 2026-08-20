"""Pydantic schema for the persisted application configuration.

Kept separate from `core.models.TrackConfig` (the plain dataclass used by
the capture/DSP/OBS pipeline): this schema is only concerned with
validating and (de)serializing what's stored on disk, and converts to/from
the runtime dataclass via `to_track_config()` / `from_track_config()`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from obs_audio_sync.core.models import TrackConfig


class TrackConfigSchema(BaseModel):
    id: str
    display_name: str
    obs_input_name: str = ""
    capture_device_name: str = ""
    is_reference: bool = False

    def to_track_config(self) -> TrackConfig:
        return TrackConfig(
            id=self.id,
            display_name=self.display_name,
            obs_input_name=self.obs_input_name,
            capture_device_name=self.capture_device_name,
            is_reference=self.is_reference,
        )

    @classmethod
    def from_track_config(cls, track: TrackConfig) -> "TrackConfigSchema":
        return cls(
            id=track.id,
            display_name=track.display_name,
            obs_input_name=track.obs_input_name,
            capture_device_name=track.capture_device_name,
            is_reference=track.is_reference,
        )


class ObsConnectionConfig(BaseModel):
    host: str = "localhost"
    port: int = 4455
    password: str = ""


class AppConfig(BaseModel):
    schema_version: int = 1
    obs: ObsConnectionConfig = Field(default_factory=ObsConnectionConfig)
    tracks: list[TrackConfigSchema] = Field(default_factory=list)
    capture_window_sec: float = 8.0
    max_expected_delay_sec: float = 2.0
    confidence_threshold: float = 0.2
    drift_threshold_ms: float = 20.0
    auto_mode_enabled: bool = False
    auto_mode_interval_sec: int = 30
    target_sample_rate: int = 48000
