"""Dialog for tuning analysis thresholds, persisted in AppConfig."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QSpinBox, QVBoxLayout

from obs_audio_sync.config.schema import AppConfig


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")

        self.capture_window_spin = QDoubleSpinBox()
        self.capture_window_spin.setRange(1.0, 60.0)
        self.capture_window_spin.setSingleStep(1.0)
        self.capture_window_spin.setSuffix(" s")

        self.max_tau_spin = QDoubleSpinBox()
        self.max_tau_spin.setRange(0.1, 10.0)
        self.max_tau_spin.setSingleStep(0.1)
        self.max_tau_spin.setSuffix(" s")

        self.confidence_threshold_spin = QDoubleSpinBox()
        self.confidence_threshold_spin.setRange(0.0, 1.0)
        self.confidence_threshold_spin.setSingleStep(0.05)

        self.drift_threshold_spin = QDoubleSpinBox()
        self.drift_threshold_spin.setRange(1.0, 1000.0)
        self.drift_threshold_spin.setSuffix(" ms")

        self.target_fs_spin = QSpinBox()
        self.target_fs_spin.setRange(8000, 192000)
        self.target_fs_spin.setSingleStep(1000)
        self.target_fs_spin.setSuffix(" Hz")

        form = QFormLayout()
        form.addRow("Capture window", self.capture_window_spin)
        form.addRow("Max expected delay", self.max_tau_spin)
        form.addRow("Confidence threshold", self.confidence_threshold_spin)
        form.addRow("Drift threshold (auto mode)", self.drift_threshold_spin)
        form.addRow("Target sample rate", self.target_fs_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self._load_from_config(config)

    def _load_from_config(self, config: AppConfig) -> None:
        self.capture_window_spin.setValue(config.capture_window_sec)
        self.max_tau_spin.setValue(config.max_expected_delay_sec)
        self.confidence_threshold_spin.setValue(config.confidence_threshold)
        self.drift_threshold_spin.setValue(config.drift_threshold_ms)
        self.target_fs_spin.setValue(config.target_sample_rate)

    def apply_to_config(self, config: AppConfig) -> AppConfig:
        return config.model_copy(
            update={
                "capture_window_sec": self.capture_window_spin.value(),
                "max_expected_delay_sec": self.max_tau_spin.value(),
                "confidence_threshold": self.confidence_threshold_spin.value(),
                "drift_threshold_ms": self.drift_threshold_spin.value(),
                "target_sample_rate": self.target_fs_spin.value(),
            }
        )
