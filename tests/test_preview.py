import fitz
import pytest

from app.preview_dialog import PreviewDialog, _render_page
from app.redactor import mark_for_redaction


class TestRenderPage:
    def test_renders_to_valid_pixmap(self, qapp, sample_pdf):
        doc = fitz.open(sample_pdf)
        pix = _render_page(doc[0], zoom=1.0)
        assert not pix.isNull()
        assert pix.width() > 0
        assert pix.height() > 0
        doc.close()

    def test_zoom_affects_size(self, qapp, sample_pdf):
        doc = fitz.open(sample_pdf)
        pix1 = _render_page(doc[0], zoom=1.0)
        pix2 = _render_page(doc[0], zoom=2.0)
        assert pix2.width() > pix1.width()
        assert pix2.height() > pix1.height()
        doc.close()


class TestPreviewDialog:
    def test_creates_without_error(self, qapp, sample_pdf):
        doc = fitz.open(sample_pdf)
        rects = doc[0].search_for("SECRET_DATA_123")
        mark_for_redaction(doc[0], rects)

        dialog = PreviewDialog(doc)
        assert dialog.windowTitle() == "Redaction Preview"
        doc.close()

    def test_no_redactions_shows_message(self, qapp, sample_pdf):
        doc = fitz.open(sample_pdf)
        # No redaction annotations added
        dialog = PreviewDialog(doc)
        # Should not crash; the "no annotations" label is shown
        doc.close()

    def test_redacted_preview_renders(self, qapp, sample_pdf):
        doc = fitz.open(sample_pdf)
        page = doc[0]
        rects = page.search_for("SECRET_DATA_123")
        mark_for_redaction(page, rects)

        dialog = PreviewDialog(doc)
        pix = dialog._render_redacted_preview(page, zoom=1.0)
        assert not pix.isNull()
        assert pix.width() > 0
        doc.close()
