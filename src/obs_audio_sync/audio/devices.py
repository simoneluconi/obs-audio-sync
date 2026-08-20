"""Enumeration of audio input devices via sounddevice (PortAudio/WASAPI)."""

from __future__ import annotations

import sounddevice as sd

from obs_audio_sync.core.models import DeviceInfo


def list_input_devices(wasapi_only: bool = True) -> list[DeviceInfo]:
    """Return the available input devices (with at least one input channel).

    On Windows we filter to the WASAPI host API by default: it has the
    lowest, most reliable latency for capturing in parallel with OBS, which
    typically also uses WASAPI for its own audio inputs.
    """
    host_apis = sd.query_hostapis()
    devices = sd.query_devices()

    result: list[DeviceInfo] = []
    for index, dev in enumerate(devices):
        if dev["max_input_channels"] <= 0:
            continue
        host_api_name = host_apis[dev["hostapi"]]["name"]
        if wasapi_only and "WASAPI" not in host_api_name:
            continue
        result.append(
            DeviceInfo(
                index=index,
                name=dev["name"],
                host_api=host_api_name,
                max_input_channels=dev["max_input_channels"],
                default_samplerate=dev["default_samplerate"],
            )
        )
    return result


def find_device_by_name(name: str, wasapi_only: bool = True) -> DeviceInfo | None:
    for dev in list_input_devices(wasapi_only=wasapi_only):
        if dev.name == name:
            return dev
    return None
