"""Auto-mode decision logic: apply only the offsets that actually drifted.

Pure Python, no Qt — the GUI drives this from a `QTimer` tick, but the
comparison/apply logic itself is independently testable and reusable.
"""

from __future__ import annotations

from obs_audio_sync.core.models import AnalysisResult, AppliedChange
from obs_audio_sync.sync_engine.engine import ProgressCallback, SyncEngine


class AutoSyncController:
    """Wraps a `SyncEngine` and only re-applies an offset when it has
    drifted from what was last applied by more than `drift_threshold_ms`.

    This avoids re-writing OBS on every tick from measurement noise alone
    (GCC-PHAT estimates on fresh audio windows jitter by a millisecond or
    two even when nothing actually changed).
    """

    def __init__(self, engine: SyncEngine, drift_threshold_ms: float = 20.0):
        self._engine = engine
        self.drift_threshold_ms = drift_threshold_ms
        self._last_applied_offsets_ms: dict[str, float] = {}

    def record_applied(self, changes: list[AppliedChange]) -> None:
        """Seed/update the drift baseline from offsets applied elsewhere
        (e.g. a manual "Analyze now" + confirm), so auto mode's first tick
        doesn't treat everything as drifted."""
        for change in changes:
            self._last_applied_offsets_ms[change.track_id] = change.new_offset_ms

    def evaluate_and_apply(
        self, result: AnalysisResult, progress_cb: ProgressCallback | None = None
    ) -> list[AppliedChange]:
        """Apply only the tracks whose newly computed offset differs from
        the last applied value by more than `drift_threshold_ms` (or that
        have never been applied yet). Returns the changes actually written."""
        drifted = {
            track_id: offset_ms
            for track_id, offset_ms in result.target_offsets_ms.items()
            if self._has_drifted(track_id, offset_ms)
        }
        if not drifted:
            return []

        applied = self._engine.apply_offsets(drifted, progress_cb=progress_cb)
        self.record_applied(applied)
        return applied

    def _has_drifted(self, track_id: str, offset_ms: float) -> bool:
        previous = self._last_applied_offsets_ms.get(track_id)
        return previous is None or abs(offset_ms - previous) > self.drift_threshold_ms
