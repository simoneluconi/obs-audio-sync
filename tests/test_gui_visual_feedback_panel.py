"""Tests for VisualFeedbackPanel: summary status, track selector, and
waveform/correlation plot population."""

import numpy as np

from obs_audio_sync.core.models import AnalysisResult, CorrelationTrace, DelayResult, TrackPreview
from obs_audio_sync.gui.panels.visual_feedback_panel import VisualFeedbackPanel


def _make_result(rejected: list[str] | None = None) -> AnalysisResult:
    ref_preview = TrackPreview(track_id="ref", waveform=np.sin(np.linspace(0, 10, 500)), fs_display=100.0)
    other_preview = TrackPreview(
        track_id="ambient",
        waveform=np.sin(np.linspace(0, 10, 500)),
        fs_display=100.0,
        correlation=CorrelationTrace(lags_sec=np.linspace(-0.05, 0.05, 50), values=np.abs(np.sin(np.linspace(-3, 3, 50)))),
    )
    return AnalysisResult(
        delays=[
            DelayResult(track_id="ref", delay_sec=0.0, confidence=1.0),
            DelayResult(track_id="ambient", delay_sec=0.02, confidence=0.8),
        ],
        target_offsets_ms={"ref": 20.0, "ambient": 0.0},
        rejected_track_ids=rejected or [],
        track_previews={"ref": ref_preview, "ambient": other_preview},
    )


def test_set_result_shows_all_synced_summary(qtbot):
    panel = VisualFeedbackPanel()
    qtbot.addWidget(panel)

    panel.set_result(_make_result(), reference_track_id="ref")

    assert "All 2 tracks synchronized" in panel.summary_label.text()


def test_set_result_shows_rejected_summary(qtbot):
    panel = VisualFeedbackPanel()
    qtbot.addWidget(panel)

    panel.set_result(_make_result(rejected=["ambient"]), reference_track_id="ref")

    assert "1/2 tracks synchronized" in panel.summary_label.text()
    assert "1 rejected" in panel.summary_label.text()


def test_set_result_populates_track_selector_excluding_reference(qtbot):
    panel = VisualFeedbackPanel()
    qtbot.addWidget(panel)

    panel.set_result(_make_result(), reference_track_id="ref")

    items = [panel.track_selector.itemData(i) for i in range(panel.track_selector.count())]
    assert items == ["ambient"]


def test_set_result_uses_display_names_in_selector(qtbot):
    panel = VisualFeedbackPanel()
    qtbot.addWidget(panel)

    panel.set_result(_make_result(), reference_track_id="ref", display_names={"ambient": "Ambient Mic"})

    assert panel.track_selector.itemText(0) == "Ambient Mic"


def test_set_result_renders_detail_label_for_selected_track(qtbot):
    panel = VisualFeedbackPanel()
    qtbot.addWidget(panel)

    panel.set_result(_make_result(), reference_track_id="ref")

    assert "delay" in panel.detail_label.text()
    assert "confidence" in panel.detail_label.text()


def test_clear_resets_summary_and_selector(qtbot):
    panel = VisualFeedbackPanel()
    qtbot.addWidget(panel)
    panel.set_result(_make_result(), reference_track_id="ref")

    panel.clear()

    assert panel.summary_label.text() == "No analysis yet."
    assert panel.track_selector.count() == 0


def test_set_result_with_no_other_tracks_clears_plots(qtbot):
    panel = VisualFeedbackPanel()
    qtbot.addWidget(panel)
    result = AnalysisResult(
        delays=[DelayResult(track_id="ref", delay_sec=0.0, confidence=1.0)],
        track_previews={"ref": TrackPreview(track_id="ref", waveform=np.zeros(10), fs_display=10.0)},
    )

    panel.set_result(result, reference_track_id="ref")

    assert panel.track_selector.count() == 0
