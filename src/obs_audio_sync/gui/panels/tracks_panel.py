"""Dynamic list of audio tracks: add/remove rows, enforce a single
reference track, and broadcast OBS input / capture device options."""

from __future__ import annotations

import itertools

from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from obs_audio_sync.core.models import TrackConfig
from obs_audio_sync.gui.panels.track_row_widget import TrackRowWidget

_id_counter = itertools.count(1)


class TracksPanel(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._rows: dict[str, TrackRowWidget] = {}
        self._reference_group = QButtonGroup(self)
        self._reference_group.setExclusive(True)
        self._last_obs_input_options: list[str] = []
        self._last_capture_device_options: list[str] = []

        header = QHBoxLayout()
        for text, stretch in (("Name", 0), ("OBS input", 1), ("Capture device", 1), ("", 0), ("Status", 0), ("", 0)):
            label = QLabel(f"<b>{text}</b>")
            header.addWidget(label, stretch=stretch)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(2)

        add_button = QPushButton("+ Add track")
        add_button.clicked.connect(lambda: self.add_track())

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addLayout(self._rows_layout)
        layout.addWidget(add_button)
        layout.addStretch(1)

    def add_track(self, track: TrackConfig | None = None) -> TrackRowWidget:
        track_id = track.id if track is not None else f"track-{next(_id_counter)}"
        row = TrackRowWidget(track_id, track.display_name if track is not None else "")
        row.remove_requested.connect(self.remove_track)
        self._reference_group.addButton(row.reference_radio)
        row.set_obs_input_options(self._last_obs_input_options)
        row.set_capture_device_options(self._last_capture_device_options)

        if track is not None:
            row.load_track_config(track)
        elif not self._rows:
            row.reference_radio.setChecked(True)  # first track defaults to reference

        self._rows[track_id] = row
        self._rows_layout.addWidget(row)
        return row

    def remove_track(self, track_id: str) -> None:
        row = self._rows.pop(track_id, None)
        if row is None:
            return
        self._reference_group.removeButton(row.reference_radio)
        self._rows_layout.removeWidget(row)
        row.deleteLater()

    def clear(self) -> None:
        for track_id in list(self._rows):
            self.remove_track(track_id)

    def load_tracks(self, tracks: list[TrackConfig]) -> None:
        self.clear()
        for track in tracks:
            self.add_track(track)

    def get_tracks(self) -> list[TrackConfig]:
        return [row.to_track_config() for row in self._rows.values()]

    def has_valid_reference(self) -> bool:
        tracks = self.get_tracks()
        return sum(1 for t in tracks if t.is_reference) == 1

    def set_obs_input_options(self, names: list[str]) -> None:
        self._last_obs_input_options = names
        for row in self._rows.values():
            row.set_obs_input_options(names)

    def set_capture_device_options(self, names: list[str]) -> None:
        self._last_capture_device_options = names
        for row in self._rows.values():
            row.set_capture_device_options(names)

    def set_track_status(self, track_id: str, status: str, detail: str = "") -> None:
        row = self._rows.get(track_id)
        if row is not None:
            row.set_status(status, detail)
