"""Tests for MainWindow wiring: config persistence, validation, and the
preview-then-confirm analyze/apply flow plus auto mode (with OBS and
SyncEngine faked out — no real network or audio hardware)."""

from __future__ import annotations

from obs_audio_sync.config.store import ConfigStore
from obs_audio_sync.core.models import AnalysisResult, AppliedChange, DelayResult, TrackConfig
from obs_audio_sync.gui import main_window as main_window_module
from obs_audio_sync.gui.main_window import MainWindow


def _make_window(qtbot, tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    window = MainWindow(config_store=store)
    qtbot.addWidget(window)
    return window


class FakeSyncEngine:
    """Stand-in for SyncEngine: canned preview result, records apply calls."""

    instances: list["FakeSyncEngine"] = []

    def __init__(self, obs_client, tracks, config):
        self.tracks = tracks
        self.apply_calls: list[dict[str, float]] = []
        FakeSyncEngine.instances.append(self)

    def run_full_cycle(self, progress_cb=None, collect_visual_data=False):
        if progress_cb:
            progress_cb("Capturing audio...")
        return FakeSyncEngine.canned_result

    def apply_offsets(self, target_offsets_ms, progress_cb=None):
        self.apply_calls.append(target_offsets_ms)
        return [
            AppliedChange(track_id=tid, obs_input_name=tid, previous_offset_ms=0.0, new_offset_ms=offset)
            for tid, offset in target_offsets_ms.items()
        ]


def test_config_round_trips_through_save_and_load(qtbot, tmp_path):
    window = _make_window(qtbot, tmp_path)
    window.connection_panel.set_fields("192.168.1.10", 4455, "secret")
    window.tracks_panel.load_tracks(
        [
            TrackConfig(id="pa", display_name="PA", obs_input_name="PA Mic", capture_device_name="Line In", is_reference=True),
            TrackConfig(id="ambient", display_name="Ambient", obs_input_name="Ambient Mic", capture_device_name="RODE"),
        ]
    )

    window._save_config()

    reloaded_window = _make_window(qtbot, tmp_path)
    assert reloaded_window.connection_panel.host_edit.text() == "192.168.1.10"
    assert reloaded_window.connection_panel.port_spin.value() == 4455
    assert reloaded_window.connection_panel.password_edit.text() == "secret"
    loaded_tracks = reloaded_window.tracks_panel.get_tracks()
    assert {t.id for t in loaded_tracks} == {"pa", "ambient"}


def test_validate_requires_obs_connection(qtbot, tmp_path):
    window = _make_window(qtbot, tmp_path)
    window.tracks_panel.add_track()

    assert window._validate_ready_to_analyze() == "Connect to OBS first."


def test_validate_requires_at_least_one_track(qtbot, tmp_path):
    window = _make_window(qtbot, tmp_path)
    window._obs_client = object()  # any non-None stand-in

    assert window._validate_ready_to_analyze() == "Add at least one track."


def test_validate_requires_exactly_one_reference(qtbot, tmp_path):
    window = _make_window(qtbot, tmp_path)
    window._obs_client = object()
    # add_track() auto-selects the first row as reference; removing it
    # leaves the remaining row(s) with no reference selected — the only
    # way to reach a zero-reference state through the real UI (an exclusive
    # QButtonGroup won't let a checked radio be unchecked by clicking itself).
    row1 = window.tracks_panel.add_track()
    window.tracks_panel.add_track()
    window.tracks_panel.remove_track(row1.track_id)

    assert window._validate_ready_to_analyze() == "Select exactly one track as the reference."


def test_validate_requires_obs_input_and_capture_device(qtbot, tmp_path):
    window = _make_window(qtbot, tmp_path)
    window._obs_client = object()
    window.tracks_panel.add_track()

    error = window._validate_ready_to_analyze()

    assert "missing an OBS input or capture device" in error


def test_validate_passes_with_complete_setup(qtbot, tmp_path):
    window = _make_window(qtbot, tmp_path)
    window._obs_client = object()
    row = window.tracks_panel.add_track()
    row.obs_input_combo.setCurrentText("PA Mic")
    row.capture_device_combo.setCurrentText("Line In")

    assert window._validate_ready_to_analyze() == ""


def test_on_connected_updates_panels(qtbot, tmp_path):
    window = _make_window(qtbot, tmp_path)
    fake_client = object()

    window._on_connected(fake_client, ({"obs_version": "31.0.0"}, ["mic", "osmo"]))

    assert window._obs_client is fake_client
    assert window.connection_panel.status_label.text() == "Connected — OBS 31.0.0"
    assert window.tracks_panel._last_obs_input_options == ["mic", "osmo"]


def test_populate_results_table_marks_rejected_and_pending_status(qtbot, tmp_path):
    window = _make_window(qtbot, tmp_path)
    row_ref = window.tracks_panel.add_track()
    row_other = window.tracks_panel.add_track()
    ref_id, other_id = row_ref.track_id, row_other.track_id
    window._display_names = {ref_id: "ref", other_id: "noisy"}

    result = AnalysisResult(
        delays=[
            DelayResult(track_id=ref_id, delay_sec=0.0, confidence=1.0),
            DelayResult(track_id=other_id, delay_sec=0.9, confidence=0.05),
        ],
        target_offsets_ms={ref_id: 0.0},
        rejected_track_ids=[other_id],
    )

    window._populate_results_table(result)

    assert window.results_table.rowCount() == 2
    assert row_other.status_label.text() == "Rejected"
    assert row_ref.status_label.text() == "Ready to apply"


def test_analyze_shows_preview_without_applying(qtbot, tmp_path, monkeypatch):
    FakeSyncEngine.instances = []
    window = _make_window(qtbot, tmp_path)
    window._obs_client = object()
    row = window.tracks_panel.add_track()
    row.obs_input_combo.setCurrentText("PA Mic")
    row.capture_device_combo.setCurrentText("Line In")
    track_id = row.track_id

    FakeSyncEngine.canned_result = AnalysisResult(
        delays=[DelayResult(track_id=track_id, delay_sec=0.0, confidence=1.0)],
        target_offsets_ms={track_id: 12.0},
    )
    monkeypatch.setattr(main_window_module, "SyncEngine", FakeSyncEngine)

    window._on_analyze_clicked()
    qtbot.waitUntil(lambda: window.analysis_panel.analyze_button.isEnabled(), timeout=3000)

    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, 0).text() == "PA Mic"
    assert window._pending_result is not None
    assert window.analysis_panel.apply_button.isEnabled() is True
    # Preview only: no engine instance should have had apply_offsets called.
    assert all(engine.apply_calls == [] for engine in FakeSyncEngine.instances)


def test_apply_writes_pending_result_and_clears_preview(qtbot, tmp_path, monkeypatch):
    FakeSyncEngine.instances = []
    window = _make_window(qtbot, tmp_path)
    window._obs_client = object()
    row = window.tracks_panel.add_track()
    row.obs_input_combo.setCurrentText("PA Mic")
    row.capture_device_combo.setCurrentText("Line In")
    track_id = row.track_id

    FakeSyncEngine.canned_result = AnalysisResult(
        delays=[DelayResult(track_id=track_id, delay_sec=0.0, confidence=1.0)],
        target_offsets_ms={track_id: 12.0},
    )
    monkeypatch.setattr(main_window_module, "SyncEngine", FakeSyncEngine)

    window._on_analyze_clicked()
    qtbot.waitUntil(lambda: window._pending_result is not None, timeout=3000)

    window._on_apply_clicked()
    qtbot.waitUntil(lambda: window._pending_result is None, timeout=3000)

    assert window._pending_result is None
    assert FakeSyncEngine.instances[-1].apply_calls == [{track_id: 12.0}]
    assert row.status_label.text() == "Synced"


def test_auto_mode_rejected_when_not_ready(qtbot, tmp_path, monkeypatch):
    window = _make_window(qtbot, tmp_path)  # no OBS connection
    # _on_auto_mode_toggled(True) pops a modal QMessageBox.warning on
    # validation failure; stub it out so the test doesn't block waiting for
    # a click that can never come in a headless test run.
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", lambda *a, **k: None)

    window._on_auto_mode_toggled(True)

    assert window._auto_controller is None
    assert window._auto_timer.isActive() is False


def test_auto_mode_starts_timer_when_ready(qtbot, tmp_path, monkeypatch):
    window = _make_window(qtbot, tmp_path)
    window._obs_client = object()
    row = window.tracks_panel.add_track()
    row.obs_input_combo.setCurrentText("PA Mic")
    row.capture_device_combo.setCurrentText("Line In")
    monkeypatch.setattr(main_window_module, "SyncEngine", FakeSyncEngine)

    window._on_auto_mode_toggled(True)

    assert window._auto_controller is not None
    assert window._auto_timer.isActive() is True

    window._on_auto_mode_toggled(False)
    assert window._auto_controller is None
    assert window._auto_timer.isActive() is False
