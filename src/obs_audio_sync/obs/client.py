"""Synchronous wrapper around the obs-websocket v5 client (obsws-python)."""

from __future__ import annotations

import obsws_python as obsws

from obs_audio_sync.core.exceptions import ObsConnectionError


class ObsClient:
    """Manages the connection to OBS and exposes the raw `obsws_python` client.

    Isolates the rest of the code from connection/authentication details
    and normalizes library errors into `ObsConnectionError`.
    """

    def __init__(self, host: str, port: int, password: str = "", timeout: float = 5.0):
        self._host = host
        self._port = port
        self._password = password
        self._timeout = timeout
        self._client: obsws.ReqClient | None = None

    def connect(self) -> None:
        try:
            self._client = obsws.ReqClient(
                host=self._host, port=self._port, password=self._password, timeout=self._timeout
            )
        except Exception as exc:
            raise ObsConnectionError(
                f"Could not connect to OBS ({self._host}:{self._port}): {exc}"
            ) from exc

    def disconnect(self) -> None:
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass  # best-effort on shutdown
            self._client = None

    def __enter__(self) -> "ObsClient":
        self.connect()
        return self

    def __exit__(self, *exc_info) -> bool:
        self.disconnect()
        return False

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    @property
    def raw(self) -> obsws.ReqClient:
        """The raw `obsws_python` client, for callers needing the full API."""
        if self._client is None:
            raise ObsConnectionError("Not connected to OBS: call connect() first")
        return self._client

    def get_version_info(self) -> dict[str, str]:
        try:
            resp = self.raw.get_version()
        except Exception as exc:
            raise ObsConnectionError(f"Error communicating with OBS: {exc}") from exc
        return {
            "obs_version": resp.obs_version,
            "websocket_version": resp.obs_web_socket_version,
        }
