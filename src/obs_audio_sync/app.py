"""Application bootstrap: creates the QApplication and shows the main window."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from obs_audio_sync.gui.main_window import MainWindow
from obs_audio_sync.gui.theme import DARK_STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("OBS Audio Sync")
    app.setStyleSheet(DARK_STYLESHEET)

    window = MainWindow()
    window.showMaximized()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
