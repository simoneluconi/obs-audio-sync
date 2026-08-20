"""A single row in the tracks panel: one audio track's configuration and
live status."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QWidget,
)

from obs_audio_sync.core.models import TrackConfig

_STATUS_STYLES = {
    "idle": ("Not analyzed", "#8a8f98"),
    "pending": ("Ready to apply", "#5b8cff"),
    "ok": ("Synced", "#3fb950"),
    "warning": ("Low confidence", "#d29922"),
    "error": ("Rejected", "#f85149"),
}


class TrackRowWidget(QWidget):
    remove_requested = Signal(str)  # emits track_id

    def __init__(self, track_id: str, display_name: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.track_id = track_id

        self.name_edit = QLineEdit(display_name or track_id)
        self.name_edit.setPlaceholderText("Track name")
        self.name_edit.setMinimumWidth(110)

        self.obs_input_combo = QComboBox()
        self.obs_input_combo.setEditable(True)
        self.obs_input_combo.setPlaceholderText("OBS audio input")
        self.obs_input_combo.setMinimumWidth(150)

        self.capture_device_combo = QComboBox()
        self.capture_device_combo.setEditable(True)
        self.capture_device_combo.setPlaceholderText("Capture device")
        self.capture_device_combo.setMinimumWidth(180)

        self.reference_radio = QRadioButton("Reference")

        self.status_label = QLabel()
        self.status_label.setMinimumWidth(110)
        self.set_status("idle")

        self.remove_button = QPushButton("✕")
        self.remove_button.setFixedWidth(28)
        self.remove_button.setToolTip("Remove track")
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self.track_id))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self.name_edit)
        layout.addWidget(self.obs_input_combo, stretch=1)
        layout.addWidget(self.capture_device_combo, stretch=1)
        layout.addWidget(self.reference_radio)
        layout.addWidget(self.status_label)
        layout.addWidget(self.remove_button)

    def to_track_config(self) -> TrackConfig:
        return TrackConfig(
            id=self.track_id,
            display_name=self.name_edit.text().strip() or self.track_id,
            obs_input_name=self.obs_input_combo.currentText().strip(),
            capture_device_name=self.capture_device_combo.currentText().strip(),
            is_reference=self.reference_radio.isChecked(),
        )

    def load_track_config(self, track: TrackConfig) -> None:
        self.name_edit.setText(track.display_name)
        self.obs_input_combo.setCurrentText(track.obs_input_name)
        self.capture_device_combo.setCurrentText(track.capture_device_name)
        self.reference_radio.setChecked(track.is_reference)

    def set_obs_input_options(self, names: list[str]) -> None:
        _repopulate_combo_preserving_text(self.obs_input_combo, names)

    def set_capture_device_options(self, names: list[str]) -> None:
        _repopulate_combo_preserving_text(self.capture_device_combo, names)

    def set_status(self, status: str, detail: str = "") -> None:
        label, color = _STATUS_STYLES.get(status, _STATUS_STYLES["idle"])
        text = detail or label
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: 600;")


def _repopulate_combo_preserving_text(combo: QComboBox, items: list[str]) -> None:
    current_text = combo.currentText()
    combo.blockSignals(True)
    combo.clear()
    combo.addItems(items)
    combo.setCurrentText(current_text)
    combo.blockSignals(False)
