"""Tests for the generic Worker/WorkerSignals QRunnable wrapper."""

from PySide6.QtCore import QThreadPool

from obs_audio_sync.gui.workers import Worker


def test_worker_emits_finished_with_result(qtbot):
    worker = Worker(lambda a, b: a + b, 2, 3)

    with qtbot.waitSignal(worker.signals.finished, timeout=2000) as blocker:
        QThreadPool.globalInstance().start(worker)

    assert blocker.args == [5]


def test_worker_emits_error_on_exception(qtbot):
    def boom():
        raise ValueError("something went wrong")

    worker = Worker(boom)

    with qtbot.waitSignal(worker.signals.error, timeout=2000) as blocker:
        QThreadPool.globalInstance().start(worker)

    assert "something went wrong" in blocker.args[0]


def test_worker_injects_progress_callback_when_supported(qtbot):
    def fn(progress_cb):
        progress_cb("step 1")
        progress_cb("step 2")
        return "done"

    worker = Worker(fn, supports_progress=True)
    progress_messages = []
    worker.signals.progress.connect(progress_messages.append)

    with qtbot.waitSignal(worker.signals.finished, timeout=2000):
        QThreadPool.globalInstance().start(worker)

    assert progress_messages == ["step 1", "step 2"]


def test_worker_does_not_inject_progress_callback_by_default(qtbot):
    calls = []
    worker = Worker(lambda: calls.append("ran") or "ok")

    with qtbot.waitSignal(worker.signals.finished, timeout=2000):
        QThreadPool.globalInstance().start(worker)

    assert calls == ["ran"]
