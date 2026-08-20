"""Tests for AutoSyncController's drift-based apply decision."""

from unittest.mock import MagicMock

from obs_audio_sync.core.models import AnalysisResult, AppliedChange
from obs_audio_sync.sync_engine.auto_mode import AutoSyncController


def _make_engine(applied_changes: list[AppliedChange]) -> MagicMock:
    engine = MagicMock()
    engine.apply_offsets.return_value = applied_changes
    return engine


def test_first_tick_applies_everything():
    changes = [AppliedChange(track_id="a", obs_input_name="A", previous_offset_ms=0.0, new_offset_ms=100.0)]
    engine = _make_engine(changes)
    controller = AutoSyncController(engine, drift_threshold_ms=20.0)
    result = AnalysisResult(target_offsets_ms={"a": 100.0})

    applied = controller.evaluate_and_apply(result)

    engine.apply_offsets.assert_called_once_with({"a": 100.0}, progress_cb=None)
    assert applied == changes


def test_small_drift_is_not_reapplied():
    engine = _make_engine([])
    controller = AutoSyncController(engine, drift_threshold_ms=20.0)
    controller.record_applied([AppliedChange(track_id="a", obs_input_name="A", previous_offset_ms=0.0, new_offset_ms=100.0)])

    applied = controller.evaluate_and_apply(AnalysisResult(target_offsets_ms={"a": 105.0}))

    engine.apply_offsets.assert_not_called()
    assert applied == []


def test_drift_beyond_threshold_is_reapplied():
    changes = [AppliedChange(track_id="a", obs_input_name="A", previous_offset_ms=100.0, new_offset_ms=140.0)]
    engine = _make_engine(changes)
    controller = AutoSyncController(engine, drift_threshold_ms=20.0)
    controller.record_applied([AppliedChange(track_id="a", obs_input_name="A", previous_offset_ms=0.0, new_offset_ms=100.0)])

    applied = controller.evaluate_and_apply(AnalysisResult(target_offsets_ms={"a": 140.0}))

    engine.apply_offsets.assert_called_once_with({"a": 140.0}, progress_cb=None)
    assert applied == changes


def test_only_drifted_tracks_are_included_in_apply_call():
    changes = [AppliedChange(track_id="b", obs_input_name="B", previous_offset_ms=50.0, new_offset_ms=90.0)]
    engine = _make_engine(changes)
    controller = AutoSyncController(engine, drift_threshold_ms=20.0)
    controller.record_applied(
        [
            AppliedChange(track_id="a", obs_input_name="A", previous_offset_ms=0.0, new_offset_ms=100.0),
            AppliedChange(track_id="b", obs_input_name="B", previous_offset_ms=0.0, new_offset_ms=50.0),
        ]
    )

    controller.evaluate_and_apply(AnalysisResult(target_offsets_ms={"a": 102.0, "b": 90.0}))

    engine.apply_offsets.assert_called_once_with({"b": 90.0}, progress_cb=None)


def test_record_applied_seeds_baseline_without_calling_engine():
    engine = _make_engine([])
    controller = AutoSyncController(engine, drift_threshold_ms=20.0)

    controller.record_applied([AppliedChange(track_id="a", obs_input_name="A", previous_offset_ms=0.0, new_offset_ms=100.0)])

    engine.apply_offsets.assert_not_called()
    applied = controller.evaluate_and_apply(AnalysisResult(target_offsets_ms={"a": 101.0}))
    assert applied == []
