"""Tests for TracksPanel: add/remove rows, reference exclusivity, and
config round-tripping."""

from obs_audio_sync.core.models import TrackConfig
from obs_audio_sync.gui.panels.tracks_panel import TracksPanel


def test_first_added_track_defaults_to_reference(qtbot):
    panel = TracksPanel()
    qtbot.addWidget(panel)

    panel.add_track()

    tracks = panel.get_tracks()
    assert len(tracks) == 1
    assert tracks[0].is_reference is True


def test_reference_selection_is_mutually_exclusive(qtbot):
    panel = TracksPanel()
    qtbot.addWidget(panel)

    row1 = panel.add_track()
    row2 = panel.add_track()

    assert row1.reference_radio.isChecked() is True
    assert row2.reference_radio.isChecked() is False

    row2.reference_radio.setChecked(True)

    assert row1.reference_radio.isChecked() is False
    assert row2.reference_radio.isChecked() is True
    assert panel.has_valid_reference() is True


def test_remove_track_removes_row(qtbot):
    panel = TracksPanel()
    qtbot.addWidget(panel)
    row = panel.add_track()

    panel.remove_track(row.track_id)

    assert panel.get_tracks() == []


def test_load_tracks_replaces_existing_rows(qtbot):
    panel = TracksPanel()
    qtbot.addWidget(panel)
    panel.add_track()

    tracks = [
        TrackConfig(id="pa", display_name="PA", obs_input_name="PA Mic", capture_device_name="Line In", is_reference=True),
        TrackConfig(id="ambient", display_name="Ambient", obs_input_name="Ambient Mic", capture_device_name="RODE"),
    ]
    panel.load_tracks(tracks)

    loaded = panel.get_tracks()
    assert len(loaded) == 2
    assert {t.id for t in loaded} == {"pa", "ambient"}
    pa = next(t for t in loaded if t.id == "pa")
    assert pa.is_reference is True
    assert pa.obs_input_name == "PA Mic"
    assert pa.capture_device_name == "Line In"


def test_has_valid_reference_false_when_no_tracks():
    panel = TracksPanel()

    assert panel.has_valid_reference() is False


def test_set_obs_input_options_broadcasts_to_all_rows(qtbot):
    panel = TracksPanel()
    qtbot.addWidget(panel)
    row1 = panel.add_track()
    row2 = panel.add_track()

    panel.set_obs_input_options(["mic", "osmo"])

    assert [row1.obs_input_combo.itemText(i) for i in range(row1.obs_input_combo.count())] == ["mic", "osmo"]
    assert [row2.obs_input_combo.itemText(i) for i in range(row2.obs_input_combo.count())] == ["mic", "osmo"]


def test_set_obs_input_options_preserves_current_free_text(qtbot):
    panel = TracksPanel()
    qtbot.addWidget(panel)
    row = panel.add_track()
    row.obs_input_combo.setCurrentText("not yet connected input")

    panel.set_obs_input_options(["mic", "osmo"])

    assert row.obs_input_combo.currentText() == "not yet connected input"


def test_set_track_status_updates_matching_row(qtbot):
    panel = TracksPanel()
    qtbot.addWidget(panel)
    row = panel.add_track()

    panel.set_track_status(row.track_id, "ok")

    assert row.status_label.text() == "Synced"
