import sys
import os

import fitz
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single QApplication exists for the entire test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture()
def sample_pdf(tmp_path):
    """Create a multi-page PDF with known text content."""
    path = tmp_path / "sample.pdf"
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page()
        lines = [
            f"Page {i + 1}: Introduction paragraph.",
            "The quick brown fox jumps over the lazy dog.",
            "Confidential: SECRET_DATA_123 must be removed.",
            "Another line with SECRET_DATA_123 repeated here.",
            "End of page content.",
        ]
        page.insert_text((72, 72), "\n".join(lines), fontsize=12)
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture()
def sample_image(tmp_path, qapp):
    """Create a JPEG image with known text content for OCR testing."""
    from PySide6.QtGui import QImage, QPainter, QFont, QColor

    path = tmp_path / "sample.jpg"
    img = QImage(600, 300, QImage.Format.Format_RGB888)
    img.fill(QColor("white"))
    painter = QPainter(img)
    painter.setFont(QFont("Helvetica", 20))
    painter.drawText(50, 80, "This contains SECRET_DATA_123")
    painter.drawText(50, 160, "And SECRET_DATA_123 again here")
    painter.end()
    img.save(str(path), "JPEG")
    return str(path)
