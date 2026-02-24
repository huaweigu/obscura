import os
import subprocess
import sys

from PySide6.QtWidgets import QApplication


def _ensure_tessdata():
    """Set TESSDATA_PREFIX if not already configured."""
    if os.environ.get("TESSDATA_PREFIX"):
        return
    # Common locations
    candidates = [
        "/usr/local/share/tessdata",        # Homebrew Intel
        "/opt/homebrew/share/tessdata",      # Homebrew Apple Silicon
        "/usr/share/tesseract-ocr/5/tessdata",  # Linux
    ]
    for path in candidates:
        if os.path.isdir(path):
            os.environ["TESSDATA_PREFIX"] = path
            return
    # Try brew --prefix as fallback
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


def main():
    _ensure_tessdata()
    app = QApplication(sys.argv)
    app.setApplicationName("Text Redactor")
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
