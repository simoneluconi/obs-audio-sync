"""Visual confirmation that tracks are actually synchronized: waveform
before/after alignment overlay, the cross-correlation curve behind each
delay estimate, and an overall status summary."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from obs_audio_sync.core.models import AnalysisResult
from obs_audio_sync.dsp.preprocessing import apply_delay

# Applied once, at import time, before any PlotWidget in this module is
# constructed — pyqtgraph reads these at widget-creation time, not live.
pg.setConfigOption("background", "#1e2126")
pg.setConfigOption("foreground", "#e6e6e6")
pg.setConfigOptions(antialias=True)

_COLOR_REFERENCE = "#5b8cff"
_COLOR_BEFORE = "#f85149"
_COLOR_AFTER = "#3fb950"


class VisualFeedbackPanel(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._result: AnalysisResult | None = None
        self._reference_track_id: str | None = None
        self._display_names: dict[str, str] = {}

        self.summary_label = QLabel("No analysis yet.")
        self.summary_label.setStyleSheet("font-size: 15px; font-weight: 600;")

        self.track_selector = QComboBox()
        self.track_selector.currentTextChanged.connect(self._on_track_selected)

        self.detail_label = QLabel()

        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("Preview track:"))
        selector_row.addWidget(self.track_selector, stretch=1)
        selector_row.addWidget(self.detail_label, stretch=2)

        self.waveform_plot = pg.PlotWidget(title="Waveform alignment (reference vs. before/after shift)")
        self.waveform_plot.addLegend()
        self.waveform_plot.setLabel("bottom", "Time", units="s")
        self.waveform_plot.setLabel("left", "Amplitude")
        self.waveform_plot.showGrid(x=True, y=True, alpha=0.2)

        self.correlation_plot = pg.PlotWidget(title="Cross-correlation (peak = estimated delay)")
        self.correlation_plot.setLabel("bottom", "Lag", units="ms")
        self.correlation_plot.setLabel("left", "Normalized correlation")
        self.correlation_plot.showGrid(x=True, y=True, alpha=0.2)

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary_label)
        layout.addLayout(selector_row)
        layout.addWidget(self.waveform_plot, stretch=1)
        layout.addWidget(self.correlation_plot, stretch=1)

    def set_result(self, result: AnalysisResult, reference_track_id: str, display_names: dict[str, str] | None = None) -> None:
        self._result = result
        self._reference_track_id = reference_track_id
        self._display_names = display_names or {}

        self._update_summary()

        non_reference_ids = [tid for tid in result.track_previews if tid != reference_track_id]
        self.track_selector.blockSignals(True)
        self.track_selector.clear()
        for track_id in non_reference_ids:
            self.track_selector.addItem(self._label_for(track_id), track_id)
        self.track_selector.blockSignals(False)

        if non_reference_ids:
            self._render_track(non_reference_ids[0])
        else:
            self._clear_plots()

    def clear(self) -> None:
        self._result = None
        self._reference_track_id = None
        self.track_selector.clear()
        self.summary_label.setText("No analysis yet.")
        self.summary_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #8a8f98;")
        self._clear_plots()

    def _label_for(self, track_id: str) -> str:
        return self._display_names.get(track_id, track_id)

    def _on_track_selected(self, _text: str) -> None:
        track_id = self.track_selector.currentData()
        if track_id:
            self._render_track(track_id)

    def _update_summary(self) -> None:
        assert self._result is not None
        total = len(self._result.delays)
        rejected = len(self._result.rejected_track_ids)
        synced = total - rejected

        if total == 0:
            self.summary_label.setText("No tracks analyzed.")
            self.summary_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #8a8f98;")
        elif rejected == 0:
            self.summary_label.setText(f"✓ All {total} tracks synchronized")
            self.summary_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #3fb950;")
        else:
            self.summary_label.setText(
                f"⚠ {synced}/{total} tracks synchronized — {rejected} rejected (low confidence)"
            )
            self.summary_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #d29922;")

    def _render_track(self, track_id: str) -> None:
        if self._result is None or self._reference_track_id is None:
            return
        ref_preview = self._result.track_previews.get(self._reference_track_id)
        track_preview = self._result.track_previews.get(track_id)
        delay_result = next((d for d in self._result.delays if d.track_id == track_id), None)
        if ref_preview is None or track_preview is None or delay_result is None:
            self._clear_plots()
            return

        self.waveform_plot.clear()
        t_ref = np.arange(len(ref_preview.waveform)) / ref_preview.fs_display
        self.waveform_plot.plot(t_ref, ref_preview.waveform, pen=pg.mkPen(_COLOR_REFERENCE, width=2), name="Reference")

        t_track = np.arange(len(track_preview.waveform)) / track_preview.fs_display
        self.waveform_plot.plot(
            t_track,
            track_preview.waveform,
            pen=pg.mkPen(_COLOR_BEFORE, width=1, style=Qt.PenStyle.DashLine),
            name="Before alignment",
        )

        shifted = apply_delay(track_preview.waveform, delay_result.delay_sec, track_preview.fs_display)
        self.waveform_plot.plot(t_track, shifted, pen=pg.mkPen(_COLOR_AFTER, width=2), name="After alignment")

        self.correlation_plot.clear()
        trace = track_preview.correlation
        if trace is not None and len(trace.lags_sec):
            lags_ms = trace.lags_sec * 1000.0
            self.correlation_plot.plot(lags_ms, trace.values, pen=pg.mkPen(_COLOR_REFERENCE, width=2))
            peak_idx = int(np.argmax(trace.values))
            self.correlation_plot.plot(
                [lags_ms[peak_idx]],
                [trace.values[peak_idx]],
                pen=None,
                symbol="o",
                symbolBrush=_COLOR_BEFORE,
                symbolSize=10,
            )

        confidence_pct = delay_result.confidence * 100.0
        status = "rejected" if track_id in self._result.rejected_track_ids else "accepted"
        self.detail_label.setText(
            f"{self._label_for(track_id)}: delay {delay_result.delay_sec * 1000:+.1f} ms, "
            f"confidence {confidence_pct:.0f}% ({status})"
        )

    def _clear_plots(self) -> None:
        self.waveform_plot.clear()
        self.correlation_plot.clear()
        self.detail_label.setText("")
