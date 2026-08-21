"""Main application window.

Manual flow is preview-then-confirm: "Analyze now" only computes and shows
results (never writes to OBS); a separate "Apply changes" button, enabled
once a preview exists, is what actually writes to OBS. Auto mode is the
opposite by design — it is meant to run hands-off, so each tick computes
and applies (only the tracks that drifted beyond the configured threshold)
without asking for confirmation.

All blocking work (OBS websocket, audio capture, GCC-PHAT) runs off the UI
thread via `gui.workers.Worker`.
"""

from __future__ import annotations

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    QMainWindow,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from obs_audio_sync.audio.devices import list_input_devices
from obs_audio_sync.config.schema import AppConfig, ObsConnectionConfig, TrackConfigSchema
from obs_audio_sync.config.store import ConfigStore
from obs_audio_sync.core.models import AnalysisResult, AppliedChange, TrackConfig
from obs_audio_sync.gui.panels.analysis_panel import AnalysisPanel
from obs_audio_sync.gui.panels.connection_panel import ConnectionPanel
from obs_audio_sync.gui.panels.settings_dialog import SettingsDialog
from obs_audio_sync.gui.panels.tracks_panel import TracksPanel
from obs_audio_sync.gui.panels.visual_feedback_panel import VisualFeedbackPanel
from obs_audio_sync.gui.workers import Worker
from obs_audio_sync.obs.client import ObsClient
from obs_audio_sync.obs.sync_ops import list_input_names
from obs_audio_sync.sync_engine.auto_mode import AutoSyncController
from obs_audio_sync.sync_engine.engine import SyncEngine, SyncEngineConfig

_RESULT_COLUMNS = ["Track", "Delay (ms)", "Confidence", "Proposed offset (ms)", "Status"]


def _connect_and_fetch_obs_info(client: ObsClient) -> tuple[dict[str, str], list[str]]:
    client.connect()
    version_info = client.get_version_info()
    input_names = list_input_names(client)
    return version_info, input_names


class MainWindow(QMainWindow):
    def __init__(self, config_store: ConfigStore | None = None):
        super().__init__()
        self.setWindowTitle("OBS Audio Sync")
        self.resize(1200, 900)
        self.setMinimumSize(900, 700)

        self._thread_pool = QThreadPool.globalInstance()
        self._config_store = config_store or ConfigStore()
        self._app_config = AppConfig()
        self._obs_client: ObsClient | None = None

        self._pending_result: AnalysisResult | None = None
        self._reference_track_id: str | None = None
        self._display_names: dict[str, str] = {}
        self._last_manual_applied_changes: list[AppliedChange] = []

        self._auto_engine: SyncEngine | None = None
        self._auto_controller: AutoSyncController | None = None
        self._analysis_in_flight = False
        self._auto_seconds_remaining = 0

        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._on_auto_timer_tick)
        self._auto_countdown_timer = QTimer(self)
        self._auto_countdown_timer.timeout.connect(self._on_auto_countdown_tick)

        settings_action = self.menuBar().addAction("Settings")
        settings_action.triggered.connect(self._open_settings_dialog)

        self.connection_panel = ConnectionPanel()
        self.connection_panel.connect_requested.connect(self._on_connect_requested)
        self.connection_panel.disconnect_requested.connect(self._on_disconnect_requested)

        self.tracks_panel = TracksPanel()

        self.analysis_panel = AnalysisPanel()
        self.analysis_panel.analyze_requested.connect(self._on_analyze_clicked)
        self.analysis_panel.apply_requested.connect(self._on_apply_clicked)
        self.analysis_panel.auto_mode_toggled.connect(self._on_auto_mode_toggled)
        self.analysis_panel.auto_interval_changed.connect(self._on_auto_interval_changed)

        self.results_table = QTableWidget(0, len(_RESULT_COLUMNS))
        self.results_table.setHorizontalHeaderLabels(_RESULT_COLUMNS)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setMaximumHeight(160)

        self.visual_feedback_panel = VisualFeedbackPanel()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.connection_panel)
        layout.addWidget(self.tracks_panel, stretch=0)
        layout.addWidget(self.analysis_panel)
        layout.addWidget(self.results_table)
        layout.addWidget(self.visual_feedback_panel, stretch=1)
        self.setCentralWidget(central)

        self._refresh_capture_devices()
        self._load_config()

    # -- Config persistence -------------------------------------------------

    def _load_config(self) -> None:
        self._app_config = self._config_store.load()
        self.connection_panel.set_fields(
            self._app_config.obs.host, self._app_config.obs.port, self._app_config.obs.password
        )
        self.tracks_panel.load_tracks([t.to_track_config() for t in self._app_config.tracks])
        self.analysis_panel.set_interval_seconds(self._app_config.auto_mode_interval_sec)
        # Auto mode is never auto-resumed at startup, even if it was left
        # on last session: OBS isn't connected yet at this point, and
        # silently starting to write offsets before the user has reviewed
        # anything would be surprising.

    def _save_config(self) -> None:
        self._app_config.obs = ObsConnectionConfig(
            host=self.connection_panel.host_edit.text().strip(),
            port=self.connection_panel.port_spin.value(),
            password=self.connection_panel.password_edit.text(),
        )
        self._app_config.tracks = [TrackConfigSchema.from_track_config(t) for t in self.tracks_panel.get_tracks()]
        self._app_config.auto_mode_interval_sec = self.analysis_panel.interval_spin.value()
        self._config_store.save(self._app_config)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._auto_timer.stop()
        self._auto_countdown_timer.stop()
        self._save_config()
        super().closeEvent(event)

    # -- Settings -------------------------------------------------

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self._app_config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._app_config = dialog.apply_to_config(self._app_config)

    # -- OBS connection -------------------------------------------------

    def _on_connect_requested(self, host: str, port: int, password: str) -> None:
        self.connection_panel.set_connecting()
        client = ObsClient(host=host, port=port, password=password)
        worker = Worker(_connect_and_fetch_obs_info, client)
        worker.signals.finished.connect(lambda result: self._on_connected(client, result))
        worker.signals.error.connect(self.connection_panel.set_disconnected)
        self._thread_pool.start(worker)

    def _on_connected(self, client: ObsClient, result: tuple[dict[str, str], list[str]]) -> None:
        version_info, input_names = result
        self._obs_client = client
        self.connection_panel.set_connected(version_info)
        self.tracks_panel.set_obs_input_options(input_names)

    def _on_disconnect_requested(self) -> None:
        self._disable_auto_mode()
        if self._obs_client is not None:
            self._obs_client.disconnect()
            self._obs_client = None
        self.connection_panel.set_disconnected()

    # -- Capture devices -------------------------------------------------

    def _refresh_capture_devices(self) -> None:
        device_names = [d.name for d in list_input_devices()]
        self.tracks_panel.set_capture_device_options(device_names)

    # -- Shared helpers -------------------------------------------------

    def _validate_ready_to_analyze(self) -> str:
        if self._obs_client is None:
            return "Connect to OBS first."
        tracks = self.tracks_panel.get_tracks()
        if not tracks:
            return "Add at least one track."
        if not self.tracks_panel.has_valid_reference():
            return "Select exactly one track as the reference."
        for track in tracks:
            if not track.obs_input_name or not track.capture_device_name:
                return f"Track '{track.display_name}' is missing an OBS input or capture device."
        return ""

    def _build_sync_engine_config(self) -> SyncEngineConfig:
        return SyncEngineConfig(
            capture_window_sec=self._app_config.capture_window_sec,
            max_tau_sec=self._app_config.max_expected_delay_sec,
            confidence_threshold=self._app_config.confidence_threshold,
            target_fs=self._app_config.target_sample_rate,
        )

    def _snapshot_track_metadata(self, tracks: list[TrackConfig]) -> None:
        self._reference_track_id = next(t.id for t in tracks if t.is_reference)
        self._display_names = {t.id: t.display_name for t in tracks}

    def _populate_results_table(self, result: AnalysisResult) -> None:
        self.results_table.setRowCount(len(result.delays))
        for row, delay in enumerate(sorted(result.delays, key=lambda d: d.track_id)):
            offset_ms = result.target_offsets_ms.get(delay.track_id)
            rejected = delay.track_id in result.rejected_track_ids
            status = "Rejected (low confidence)" if rejected else "Ready to apply"

            values = [
                self._display_names.get(delay.track_id, delay.track_id),
                f"{delay.delay_sec * 1000:+.2f}",
                f"{delay.confidence:.2f}",
                f"{offset_ms:.1f}" if offset_ms is not None else "—",
                status,
            ]
            for col, value in enumerate(values):
                self.results_table.setItem(row, col, QTableWidgetItem(value))

            self.tracks_panel.set_track_status(delay.track_id, "error" if rejected else "pending")

    # -- Manual analyze / apply -------------------------------------------------

    def _on_analyze_clicked(self) -> None:
        error = self._validate_ready_to_analyze()
        if error:
            QMessageBox.warning(self, "Cannot analyze", error)
            return

        tracks = self.tracks_panel.get_tracks()
        self._snapshot_track_metadata(tracks)
        engine = SyncEngine(self._obs_client, tracks, self._build_sync_engine_config())

        self.analysis_panel.set_analyzing(True)
        self.analysis_panel.set_preview_available(False)
        self.analysis_panel.set_status("Starting analysis…")
        self._pending_result = None

        worker = Worker(engine.run_full_cycle, supports_progress=True, collect_visual_data=True)
        worker.signals.progress.connect(self.analysis_panel.set_status)
        worker.signals.finished.connect(self._on_preview_ready)
        worker.signals.error.connect(self._on_analyze_error)
        self._thread_pool.start(worker)

    def _on_preview_ready(self, result: AnalysisResult) -> None:
        self.analysis_panel.set_analyzing(False)
        self._pending_result = result
        self._populate_results_table(result)
        self.visual_feedback_panel.set_result(result, self._reference_track_id, self._display_names)

        if result.target_offsets_ms:
            self.analysis_panel.set_status("Preview ready — review below, then click \"Apply changes\" to write to OBS.")
            self.analysis_panel.set_preview_available(True)
        else:
            self.analysis_panel.set_status("No track passed the confidence threshold — nothing to apply.")
            self.analysis_panel.set_preview_available(False)

    def _on_analyze_error(self, message: str) -> None:
        self.analysis_panel.set_analyzing(False)
        self.analysis_panel.set_status("Analysis failed.")
        QMessageBox.critical(self, "Analysis failed", message)

    def _on_apply_clicked(self) -> None:
        if self._pending_result is None or self._obs_client is None:
            return

        tracks = self.tracks_panel.get_tracks()
        engine = SyncEngine(self._obs_client, tracks, self._build_sync_engine_config())

        self.analysis_panel.set_applying(True)
        self.analysis_panel.set_status("Applying changes to OBS…")

        worker = Worker(engine.apply_offsets, self._pending_result.target_offsets_ms)
        worker.signals.finished.connect(self._on_apply_finished)
        worker.signals.error.connect(self._on_apply_error)
        self._thread_pool.start(worker)

    def _on_apply_finished(self, applied_changes: list[AppliedChange]) -> None:
        self.analysis_panel.set_applying(False)
        self.analysis_panel.set_preview_available(False)
        self.analysis_panel.set_status(f"Applied {len(applied_changes)} change(s) to OBS.")
        self._last_manual_applied_changes = applied_changes
        if self._auto_controller is not None:
            self._auto_controller.record_applied(applied_changes)
        for change in applied_changes:
            self.tracks_panel.set_track_status(change.track_id, "ok")
        self._pending_result = None

    def _on_apply_error(self, message: str) -> None:
        self.analysis_panel.set_applying(False)
        self.analysis_panel.set_status("Apply failed.")
        QMessageBox.critical(self, "Apply failed", message)

    # -- Auto mode -------------------------------------------------

    def _on_auto_mode_toggled(self, enabled: bool) -> None:
        if enabled:
            error = self._validate_ready_to_analyze()
            if error:
                QMessageBox.warning(self, "Cannot enable auto mode", error)
                self.analysis_panel.set_auto_mode_active(False)
                return

            tracks = self.tracks_panel.get_tracks()
            self._snapshot_track_metadata(tracks)
            self._auto_engine = SyncEngine(self._obs_client, tracks, self._build_sync_engine_config())
            self._auto_controller = AutoSyncController(
                self._auto_engine, drift_threshold_ms=self._app_config.drift_threshold_ms
            )
            self._auto_controller.record_applied(self._last_manual_applied_changes)

            self.analysis_panel.set_auto_mode_active(True)
            self._start_auto_timer()
        else:
            self._disable_auto_mode()

    def _disable_auto_mode(self) -> None:
        self._auto_timer.stop()
        self._auto_countdown_timer.stop()
        self._auto_engine = None
        self._auto_controller = None
        self.analysis_panel.set_auto_mode_active(False)

    def _start_auto_timer(self) -> None:
        interval_sec = self.analysis_panel.interval_spin.value()
        self._auto_timer.start(interval_sec * 1000)
        self._auto_seconds_remaining = interval_sec
        self.analysis_panel.set_countdown(self._auto_seconds_remaining)
        self._auto_countdown_timer.start(1000)

    def _on_auto_interval_changed(self, seconds: int) -> None:
        if self._auto_timer.isActive():
            self._auto_timer.setInterval(seconds * 1000)
            self._auto_seconds_remaining = seconds
            self.analysis_panel.set_countdown(seconds)

    def _on_auto_countdown_tick(self) -> None:
        self._auto_seconds_remaining = max(0, self._auto_seconds_remaining - 1)
        self.analysis_panel.set_countdown(self._auto_seconds_remaining)

    def _on_auto_timer_tick(self) -> None:
        self._auto_seconds_remaining = self.analysis_panel.interval_spin.value()
        self.analysis_panel.set_countdown(self._auto_seconds_remaining)

        if self._analysis_in_flight or self._auto_controller is None or self._auto_engine is None:
            return  # previous cycle still running: skip this tick rather than overlap

        self._analysis_in_flight = True
        worker = Worker(self._run_auto_cycle, supports_progress=True)
        worker.signals.progress.connect(self.analysis_panel.set_status)
        worker.signals.finished.connect(self._on_auto_cycle_finished)
        worker.signals.error.connect(self._on_auto_cycle_error)
        self._thread_pool.start(worker)

    def _run_auto_cycle(self, progress_cb=None) -> tuple[AnalysisResult, list[AppliedChange]]:
        result = self._auto_engine.run_full_cycle(progress_cb=progress_cb, collect_visual_data=True)
        applied = self._auto_controller.evaluate_and_apply(result, progress_cb=progress_cb)
        return result, applied

    def _on_auto_cycle_finished(self, payload: tuple[AnalysisResult, list[AppliedChange]]) -> None:
        self._analysis_in_flight = False
        result, applied = payload
        self._populate_results_table(result)
        self.visual_feedback_panel.set_result(result, self._reference_track_id, self._display_names)
        for change in applied:
            self.tracks_panel.set_track_status(change.track_id, "ok")
        self.analysis_panel.set_status(
            f"Auto: applied {len(applied)} change(s)." if applied else "Auto: no drift detected."
        )

    def _on_auto_cycle_error(self, message: str) -> None:
        self._analysis_in_flight = False
        # Non-modal on purpose: a dialog popping up unattended every failed
        # tick would be a poor experience for a background mode.
        self.analysis_panel.set_status(f"Auto cycle failed: {message}")
