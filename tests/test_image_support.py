import fitz
import pytest

from app.main_window import MainWindow
from app.redactor import apply_redactions, mark_for_redaction, save


class TestImageToPdf:
    def test_converts_image_to_single_page_pdf(self, sample_image):
        doc = MainWindow._image_to_pdf(sample_image)
        assert len(doc) == 1
        page = doc[0]
        assert page.rect.width > 0
        assert page.rect.height > 0
        doc.close()

    def test_converted_pdf_is_renderable(self, sample_image, qapp):
        doc = MainWindow._image_to_pdf(sample_image)
        page = doc[0]
        pix = page.get_pixmap()
        assert pix.width > 0
        assert pix.height > 0
        doc.close()


class TestOcrSearch:
    def test_ocr_finds_text_in_image(self, sample_image):
        doc = MainWindow._image_to_pdf(sample_image)
        page = doc[0]
        tp = page.get_textpage_ocr(language="eng", full=True)

        matches = page.search_for("SECRET_DATA_123", textpage=tp)
        assert len(matches) == 2
        doc.close()

    def test_ocr_extracts_readable_text(self, sample_image):
        doc = MainWindow._image_to_pdf(sample_image)
        page = doc[0]
        tp = page.get_textpage_ocr(language="eng", full=True)

        text = page.get_text("text", textpage=tp)
        assert "SECRET_DATA_123" in text
        doc.close()

    def test_ocr_no_matches_for_absent_text(self, sample_image):
        doc = MainWindow._image_to_pdf(sample_image)
        page = doc[0]
        tp = page.get_textpage_ocr(language="eng", full=True)

        matches = page.search_for("NONEXISTENT_WORD_XYZ", textpage=tp)
        assert len(matches) == 0
        doc.close()


class TestImageRedaction:
    def test_redact_text_in_image_pdf(self, sample_image, tmp_path):
        keyword = "SECRET_DATA_123"
        doc = MainWindow._image_to_pdf(sample_image)
        page = doc[0]
        tp = page.get_textpage_ocr(language="eng", full=True)

        matches = page.search_for(keyword, textpage=tp)
        assert len(matches) > 0

        mark_for_redaction(page, matches)
        apply_redactions(doc)

        # Re-OCR and verify text is gone
        tp2 = page.get_textpage_ocr(language="eng", full=True)
        remaining = page.search_for(keyword, textpage=tp2)
        assert len(remaining) == 0

        doc.close()

    def test_save_redacted_image_pdf(self, sample_image, tmp_path):
        keyword = "SECRET_DATA_123"
        doc = MainWindow._image_to_pdf(sample_image)
        page = doc[0]
        tp = page.get_textpage_ocr(language="eng", full=True)

        mark_for_redaction(page, page.search_for(keyword, textpage=tp))
        apply_redactions(doc)

        out = str(tmp_path / "redacted_image.pdf")
        save(doc, out)
        doc.close()

        # Reopen and verify via OCR on the reopened page
        reopened = fitz.open(out)
        assert len(reopened) == 1
        page2 = reopened[0]
        tp2 = page2.get_textpage_ocr(language="eng", full=True)
        text = page2.get_text("text", textpage=tp2)
        assert keyword not in text
        reopened.close()
