import os
import subprocess
import sys

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication


def _ensure_tessdata():
    """Set TESSDATA_PREFIX if not already configured."""
    if os.environ.get("TESSDATA_PREFIX"):
        return
    candidates = [
        "/usr/local/share/tessdata",
        "/opt/homebrew/share/tessdata",
        "/usr/share/tesseract-ocr/5/tessdata",
    ]
    for path in candidates:
        if os.path.isdir(path):
            os.environ["TESSDATA_PREFIX"] = path
            return
    try:
        prefix = subprocess.check_output(
            ["brew", "--prefix", "tesseract"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        tessdata = os.path.join(prefix, "share", "tessdata")
        if os.path.isdir(tessdata):
            os.environ["TESSDATA_PREFIX"] = tessdata
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass


from app.main_window import MainWindow
from app.theme import APP_STYLE


class ObscuraApp(QApplication):
    """Custom QApplication that handles macOS file open events."""

    def __init__(self, argv):
        super().__init__(argv)
        self._window = None
        self._pending_files = []

    def set_window(self, window):
        self._window = window
        for path in self._pending_files:
            self._window._open_file_by_path(path)
        self._pending_files.clear()

    def event(self, event):
        if event.type() == QEvent.Type.FileOpen:
            path = event.file()
            if self._window:
                self._window._open_file_by_path(path)
            else:
                self._pending_files.append(path)
            return True
        return super().event(event)


def main():
    _ensure_tessdata()
    app = ObscuraApp(sys.argv)
    app.setApplicationName("Obscura")
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    app.set_window(window)

    # Handle file paths passed as command-line arguments
    for arg in sys.argv[1:]:
        if os.path.isfile(arg):
            window._open_file_by_path(arg)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
