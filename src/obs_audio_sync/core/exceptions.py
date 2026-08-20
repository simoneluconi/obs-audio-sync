class ObsAudioSyncError(Exception):
    """Base error for the application."""


class CaptureError(ObsAudioSyncError):
    """Error while capturing audio from a device."""


class ObsConnectionError(ObsAudioSyncError):
    """Error connecting to or communicating with OBS over the websocket."""
