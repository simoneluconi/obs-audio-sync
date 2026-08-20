"""OBS connection fields and status. Purely a view: connection logic (the
actual websocket work) lives in MainWindow, run on a worker thread."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QWidget


class ConnectionPanel(QWidget):
    connect_requested = Signal(str, int, str)  # host, port, password
    disconnect_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.host_edit = QLineEdit("localhost")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(4455)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self._on_connect_clicked)

        self.status_label = QLabel("Not connected")
        self.status_label.setStyleSheet("color: #8a8f98;")

        form = QFormLayout()
        form.addRow("Host", self.host_edit)
        form.addRow("Port", self.port_spin)
        form.addRow("Password", self.password_edit)

        button_row = QHBoxLayout()
        button_row.addWidget(self.connect_button)
        button_row.addWidget(self.status_label, stretch=1)

        layout = QHBoxLayout(self)
        layout.addLayout(form, stretch=1)
        layout.addLayout(button_row, stretch=1)

    def _on_connect_clicked(self) -> None:
        if self.connect_button.text() == "Connect":
            self.connect_requested.emit(self.host_edit.text().strip(), self.port_spin.value(), self.password_edit.text())
        else:
            self.disconnect_requested.emit()

    def set_connecting(self) -> None:
        self.connect_button.setEnabled(False)
        self.status_label.setText("Connecting…")
        self.status_label.setStyleSheet("color: #d29922;")

    def set_connected(self, version_info: dict[str, str]) -> None:
        self.connect_button.setEnabled(True)
        self.connect_button.setText("Disconnect")
        self.status_label.setText(f"Connected — OBS {version_info.get('obs_version', '?')}")
        self.status_label.setStyleSheet("color: #3fb950;")

    def set_disconnected(self, error: str = "") -> None:
        self.connect_button.setEnabled(True)
        self.connect_button.setText("Connect")
        self.status_label.setText(f"Connection failed: {error}" if error else "Not connected")
        self.status_label.setStyleSheet("color: #f85149;" if error else "color: #8a8f98;")

    def set_fields(self, host: str, port: int, password: str) -> None:
        self.host_edit.setText(host)
        self.port_spin.setValue(port)
        self.password_edit.setText(password)
