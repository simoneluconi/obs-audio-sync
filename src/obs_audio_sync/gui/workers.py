"""Generic QRunnable wrapper so blocking calls (OBS websocket, audio
capture, GCC-PHAT) never run on the UI thread.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    progress = Signal(str)
    finished = Signal(object)
    error = Signal(str)


class Worker(QRunnable):
    """Runs `fn(*args, **kwargs)` on a QThreadPool worker thread.

    If `supports_progress` is True, a `progress_cb` keyword argument is
    injected automatically, wired to `signals.progress`, so `fn` can report
    incremental status (e.g. "Capturing audio...") back to the UI thread.
    """

    def __init__(self, fn: Callable[..., Any], *args: Any, supports_progress: bool = False, **kwargs: Any):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._supports_progress = supports_progress
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            kwargs = dict(self._kwargs)
            if self._supports_progress:
                kwargs["progress_cb"] = self.signals.progress.emit
            result = self._fn(*self._args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - reported to the UI via signal, not swallowed
            self.signals.error.emit(str(exc))
        else:
            self.signals.finished.emit(result)
