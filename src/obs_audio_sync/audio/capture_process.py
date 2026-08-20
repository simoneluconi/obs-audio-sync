"""Runs audio capture in an isolated child process.

Empirically verified on this Windows/WASAPI setup: opening a
`sounddevice.InputStream` only succeeds when done from a process's actual
main thread. It reliably fails with a low-level WASAPI/WDM-KS error
(PaErrorCode -9999, WdmSyncIoctl) when attempted from ANY background
thread — a plain `threading.Thread` and a Qt `QThreadPool` worker both
reproduce it. Since the GUI's main thread must stay free to keep the
window responsive, capture runs in a short-lived child process instead:
its own main thread satisfies the constraint, and normal inter-process
communication (via `concurrent.futures.ProcessPoolExecutor`) carries the
resulting audio arrays back to the caller.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

from obs_audio_sync.core.models import CapturedAudio, TrackConfig


def _run_capture(tracks: list[TrackConfig], duration_sec: float) -> dict[str, CapturedAudio]:
    # Imported inside the child process, so the parent process never needs
    # to import sounddevice unless it also captures directly.
    from obs_audio_sync.audio.capture import MultiDeviceRecorder

    return MultiDeviceRecorder(tracks).capture_window(duration_sec)


def capture_window_in_subprocess(
    tracks: list[TrackConfig], duration_sec: float
) -> dict[str, CapturedAudio]:
    """Blocking: capture `duration_sec` seconds from each track's device in
    a fresh child process, and return the result.

    Safe to call from any thread in the calling process (including a Qt
    `QThreadPool` worker), unlike `MultiDeviceRecorder.capture_window`
    directly.
    """
    with ProcessPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run_capture, tracks, duration_sec)
        return future.result()
