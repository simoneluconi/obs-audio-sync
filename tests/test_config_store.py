import json

from obs_audio_sync.config.schema import AppConfig, ObsConnectionConfig, TrackConfigSchema
from obs_audio_sync.config.store import ConfigStore
from obs_audio_sync.core.models import TrackConfig


def test_load_returns_defaults_when_file_missing(tmp_path):
    store = ConfigStore(tmp_path / "does_not_exist.json")

    config = store.load()

    assert config == AppConfig()


def test_save_then_load_round_trips(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    config = AppConfig(
        obs=ObsConnectionConfig(host="192.168.1.10", port=4455, password="secret"),
        tracks=[
            TrackConfigSchema(id="pa", display_name="PA", obs_input_name="PA Mic", capture_device_name="Line In", is_reference=True),
            TrackConfigSchema(id="ambient", display_name="Ambient", obs_input_name="Ambient Mic", capture_device_name="RODE Wireless"),
        ],
        confidence_threshold=0.3,
        auto_mode_enabled=True,
        auto_mode_interval_sec=45,
    )

    store.save(config)
    loaded = store.load()

    assert loaded == config


def test_load_backs_up_and_falls_back_to_defaults_on_corrupt_file(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{not valid json", encoding="utf-8")
    store = ConfigStore(config_path)

    config = store.load()

    assert config == AppConfig()
    backup_path = config_path.with_suffix(".json.corrupt")
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == "{not valid json"


def test_save_is_atomic_and_leaves_no_tmp_file(tmp_path):
    config_path = tmp_path / "config.json"
    store = ConfigStore(config_path)

    store.save(AppConfig())

    assert config_path.exists()
    assert not config_path.with_suffix(".json.tmp").exists()
    json.loads(config_path.read_text(encoding="utf-8"))  # valid JSON


def test_track_config_schema_round_trips_to_core_track_config():
    track = TrackConfig(
        id="cam", display_name="Camera", obs_input_name="Camera Audio", capture_device_name="Cam Link 4K", is_reference=False
    )

    schema = TrackConfigSchema.from_track_config(track)
    restored = schema.to_track_config()

    assert restored == track
