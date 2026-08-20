"""Conversion of estimated delays (GCC-PHAT) into absolute OBS Sync Offsets."""

from __future__ import annotations

from obs_audio_sync.core.models import DelayResult

# OBS accepts an asymmetric range for the Sync Offset (~-950ms / +20000ms).
# We always normalize to offset >= 0 to stay away from the much tighter
# negative limit: it makes no physical sense to "shift a track back in
# time" once it's already been captured late, so the only valid correction
# is to delay the faster tracks until they align with the slowest one.
OBS_MAX_OFFSET_MS = 20000.0


def resolve_target_offsets(
    delays: list[DelayResult],
    confidence_threshold: float = 0.2,
) -> tuple[dict[str, float], list[str]]:
    """Compute the absolute OBS offsets (ms, >= 0) to apply to each track.

    `delays` contains, for every non-reference track, the delay estimated
    relative to the reference track (delay_sec > 0 => the track is delayed
    relative to the reference). The reference track itself must be included
    with delay_sec = 0.0 and confidence = 1.0.

    Returns (target_offsets_ms, rejected_track_ids): tracks whose confidence
    is below threshold are excluded from the offset dict (and reported in
    rejected_track_ids), to avoid applying corrections based on an
    unreliable estimate.
    """
    accepted = [d for d in delays if d.confidence >= confidence_threshold]
    rejected_track_ids = [d.track_id for d in delays if d.confidence < confidence_threshold]

    if not accepted:
        return {}, rejected_track_ids

    max_delay = max(d.delay_sec for d in accepted)

    target_offsets_ms = {
        d.track_id: round((max_delay - d.delay_sec) * 1000.0, 3) for d in accepted
    }

    return target_offsets_ms, rejected_track_ids


def clamp_offset_ms(offset_ms: float) -> tuple[float, bool]:
    """Apply a defensive clamp to OBS's real limits.

    Returns (clamped_offset, was_clamped) so the UI can warn the user when
    a measured delay exceeds what OBS can correct for.
    """
    if offset_ms < 0:
        return 0.0, True
    if offset_ms > OBS_MAX_OFFSET_MS:
        return OBS_MAX_OFFSET_MS, True
    return offset_ms, False
