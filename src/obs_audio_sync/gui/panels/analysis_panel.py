"""Analyze/Apply controls and auto-mode toggle. Purely a view: the actual
analysis/apply logic and the QTimer driving auto mode live in MainWindow."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget


class AnalysisPanel(QWidget):
    analyze_requested = Signal()
    apply_requested = Signal()
    auto_mode_toggled = Signal(bool)
    auto_interval_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.analyze_button = QPushButton("Analyze now")
        self.analyze_button.clicked.connect(self.analyze_requested)

        self.apply_button = QPushButton("Apply changes")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply_requested)

        self.auto_mode_checkbox = QCheckBox("Auto mode")
        self.auto_mode_checkbox.toggled.connect(self.auto_mode_toggled)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(5, 300)
        self.interval_spin.setValue(30)
        self.interval_spin.setSuffix(" s")
        self.interval_spin.valueChanged.connect(self.auto_interval_changed)

        self.countdown_label = QLabel("")
        self.countdown_label.setStyleSheet("color: #8a8f98;")

        self.status_label = QLabel("Ready.")

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.analyze_button)
        buttons_row.addWidget(self.apply_button)
        buttons_row.addStretch(1)
        buttons_row.addWidget(self.auto_mode_checkbox)
        buttons_row.addWidget(QLabel("every"))
        buttons_row.addWidget(self.interval_spin)
        buttons_row.addWidget(self.countdown_label)

        layout = QVBoxLayout(self)
        layout.addLayout(buttons_row)
        layout.addWidget(self.status_label)

    def set_analyzing(self, analyzing: bool) -> None:
        self.analyze_button.setEnabled(not analyzing)

    def set_preview_available(self, available: bool) -> None:
        self.apply_button.setEnabled(available)

    def set_applying(self, applying: bool) -> None:
        self.apply_button.setEnabled(not applying)
        self.analyze_button.setEnabled(not applying)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_countdown(self, seconds_remaining: int | None) -> None:
        self.countdown_label.setText(f"next check in {seconds_remaining}s" if seconds_remaining is not None else "")

    def set_auto_mode_active(self, active: bool) -> None:
        self.auto_mode_checkbox.blockSignals(True)
        self.auto_mode_checkbox.setChecked(active)
        self.auto_mode_checkbox.blockSignals(False)
        if not active:
            self.set_countdown(None)

    def set_interval_seconds(self, seconds: int) -> None:
        self.interval_spin.blockSignals(True)
        self.interval_spin.setValue(seconds)
        self.interval_spin.blockSignals(False)
