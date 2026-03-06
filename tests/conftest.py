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


@pytest.fixture()
def main_window(qapp):
    """Create a MainWindow instance for testing."""
    from app.main_window import MainWindow

    window = MainWindow()
    yield window
    for state in window._tab_states:
        if state.doc:
            state.doc.close()
    window.close()


@pytest.fixture()
def main_window_with_pdf(main_window, sample_pdf):
    """MainWindow with a PDF already loaded in a tab."""
    main_window._open_file_by_path(sample_pdf)
    return main_window


@pytest.fixture()
def second_sample_pdf(tmp_path):
    """A second distinct PDF for multi-tab testing."""
    path = tmp_path / "second.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Different document with UNIQUE_TERM_456.", fontsize=12)
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture()
def sample_pdf_with_toc(tmp_path):
    """Create a PDF with table of contents for navigation tests."""
    path = tmp_path / "toc_sample.pdf"
    doc = fitz.open()
    for i in range(5):
        page = doc.new_page()
        page.insert_text((72, 72), f"Chapter {i + 1} content.", fontsize=12)
        page.insert_text((72, 120), "SECRET_DATA_123 is here.", fontsize=12)
    doc.set_toc([
        [1, "Chapter 1", 1],
        [1, "Chapter 2", 2],
        [1, "Chapter 3", 3],
        [1, "Chapter 4", 4],
        [1, "Chapter 5", 5],
    ])
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture()
def batch_tree(tmp_path):
    """Folder tree with multiple PDFs for batch dialog E2E tests."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "File with SECRET_DATA_123.", fontsize=12)
    doc.save(str(tmp_path / "a.pdf"))
    doc.close()

    sub = tmp_path / "sub"
    sub.mkdir()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Another SECRET_DATA_123 here.", fontsize=12)
    doc.save(str(sub / "b.pdf"))
    doc.close()

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Clean document.", fontsize=12)
    doc.save(str(tmp_path / "clean.pdf"))
    doc.close()

    return tmp_path
