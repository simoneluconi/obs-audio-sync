"""OBS operations specific to synchronization: listing inputs, reading and
writing the audio Sync Offset."""

from __future__ import annotations

from obs_audio_sync.core.exceptions import ObsConnectionError
from obs_audio_sync.obs.client import ObsClient


def list_input_names(client: ObsClient) -> list[str]:
    """Return the names of all inputs configured in OBS (audio and otherwise).

    Filtering for audio-type inputs is left to the UI: OBS does not
    cleanly distinguish "audio inputs" from other kinds via GetInputList,
    and the user maps each track to its input manually anyway.
    """
    try:
        resp = client.raw.get_input_list()
    except Exception as exc:
        raise ObsConnectionError(f"Error reading the input list from OBS: {exc}") from exc
    return [item["inputName"] for item in resp.inputs]


def get_sync_offset_ms(client: ObsClient, input_name: str) -> float:
    try:
        resp = client.raw.get_input_audio_sync_offset(input_name)
    except Exception as exc:
        raise ObsConnectionError(
            f"Error reading the sync offset of '{input_name}': {exc}"
        ) from exc
    return float(resp.input_audio_sync_offset)


def set_sync_offset_ms(client: ObsClient, input_name: str, offset_ms: float) -> None:
    try:
        client.raw.set_input_audio_sync_offset(input_name, int(round(offset_ms)))
    except Exception as exc:
        raise ObsConnectionError(
            f"Error writing the sync offset of '{input_name}': {exc}"
        ) from exc
