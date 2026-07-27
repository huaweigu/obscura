import sys

import fitz
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single QApplication exists for the entire test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Back MainWindow's QSettings with a per-test INI file.

    MainWindow persists panel state via QSettings. Without this, tests would
    read and write the developer's real preferences (on macOS, the
    com.obscura.Obscura plist domain) and leak state into each other.

    Note: QSettings.setDefaultFormat/setPath are NOT sufficient here — on
    macOS a QSettings built from org/app names still resolves to the native
    plist domain. Substituting the constructor is the reliable isolation.
    """
    ini_path = str(tmp_path / "obscura.ini")

    def _isolated_settings(*_args, **_kwargs):
        return QSettings(ini_path, QSettings.Format.IniFormat)

    monkeypatch.setattr("app.main_window.QSettings", _isolated_settings)
    yield


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
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

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


@pytest.fixture()
def tax_tree(tmp_path):
    """Mimic a tax folder with PDFs and images across subfolders."""
    # w2/ - PDF with employer name and employee name
    w2 = tmp_path / "w2"
    w2.mkdir()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), (
        "W-2 Wage and Tax Statement\n"
        "Employer: Acme Corp\n"
        "Employee: John Smith\n"
        "SSN: 123-45-6789\n"
        "Wages: $150,000"
    ), fontsize=12)
    doc.save(str(w2 / "w2_john.pdf"))
    doc.close()

    # brokerage/ - PDF with account holder
    brokerage = tmp_path / "brokerage"
    brokerage.mkdir()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), (
        "1099-B Consolidated Statement\n"
        "Account Holder: John Smith\n"
        "Acme Corp RSU Sale\n"
        "Proceeds: $50,000"
    ), fontsize=12)
    doc.save(str(brokerage / "1099b.pdf"))
    doc.close()

    # donation/ - PDF without target keywords
    donation = tmp_path / "donation"
    donation.mkdir()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), (
        "Charitable Donation Receipt\n"
        "Organization: Local Food Bank\n"
        "Amount: $500"
    ), fontsize=12)
    doc.save(str(donation / "receipt.pdf"))
    doc.close()

    # hsa/ - another PDF with employee name
    hsa = tmp_path / "hsa"
    hsa.mkdir()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), (
        "HSA 1099-SA\n"
        "Account Holder: John Smith\n"
        "Distributions: $2,000"
    ), fontsize=12)
    doc.save(str(hsa / "1099sa.pdf"))
    doc.close()

    return tmp_path
