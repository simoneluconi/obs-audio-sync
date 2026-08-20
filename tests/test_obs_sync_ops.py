"""Tests for obs/sync_ops.py using a fake obsws_python client (no real OBS
connection required)."""

from types import SimpleNamespace

import pytest

from obs_audio_sync.core.exceptions import ObsConnectionError
from obs_audio_sync.obs.client import ObsClient
from obs_audio_sync.obs.sync_ops import get_sync_offset_ms, list_input_names, set_sync_offset_ms


class FakeRawClient:
    def __init__(self):
        self.set_calls: list[tuple[str, int]] = []
        self._offsets = {"Mic PA": 0, "Mic Ambient": 42}

    def get_input_list(self):
        return SimpleNamespace(inputs=[{"inputName": name} for name in self._offsets])

    def get_input_audio_sync_offset(self, name):
        if name not in self._offsets:
            raise RuntimeError(f"input '{name}' not found")
        return SimpleNamespace(input_audio_sync_offset=self._offsets[name])

    def set_input_audio_sync_offset(self, name, offset):
        self.set_calls.append((name, offset))
        self._offsets[name] = offset


def make_client(fake_raw: FakeRawClient) -> ObsClient:
    client = ObsClient(host="localhost", port=4455)
    client._client = fake_raw  # bypasses connect(): no real websocket in tests
    return client


def test_list_input_names():
    client = make_client(FakeRawClient())

    names = list_input_names(client)

    assert names == ["Mic PA", "Mic Ambient"]


def test_get_sync_offset_ms():
    client = make_client(FakeRawClient())

    assert get_sync_offset_ms(client, "Mic Ambient") == 42.0


def test_set_sync_offset_ms_rounds_to_int():
    fake_raw = FakeRawClient()
    client = make_client(fake_raw)

    set_sync_offset_ms(client, "Mic PA", 125.6)

    assert fake_raw.set_calls == [("Mic PA", 126)]


def test_get_sync_offset_wraps_errors():
    client = make_client(FakeRawClient())

    with pytest.raises(ObsConnectionError):
        get_sync_offset_ms(client, "Nonexistent")


def test_raw_property_requires_connect():
    client = ObsClient(host="localhost", port=4455)

    with pytest.raises(ObsConnectionError):
        _ = client.raw
