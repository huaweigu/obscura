import fitz
import pytest

from app.thumbnail_panel import ThumbnailPanel


class TestThumbnailPanel:
    def test_load_document_creates_thumbnails(self, qapp, sample_pdf):
        panel = ThumbnailPanel()
        doc = fitz.open(sample_pdf)
        panel.load_document(doc)
        assert len(panel._thumbnails) == 3

    def test_load_empty_document(self, qapp):
        panel = ThumbnailPanel()
        panel.load_document(None)
        assert len(panel._thumbnails) == 0

    def test_set_current_page_updates_selection(self, qapp, sample_pdf):
        panel = ThumbnailPanel()
        doc = fitz.open(sample_pdf)
        panel.load_document(doc)

        # First page starts selected
        assert panel._thumbnails[0]._selected is True
        assert panel._thumbnails[1]._selected is False

        # Switch to page 2
        panel.set_current_page(1)
        assert panel._thumbnails[0]._selected is False
        assert panel._thumbnails[1]._selected is True

    def test_set_current_page_out_of_range(self, qapp, sample_pdf):
        panel = ThumbnailPanel()
        doc = fitz.open(sample_pdf)
        panel.load_document(doc)
        # Should not crash
        panel.set_current_page(99)

    def test_reload_document_clears_old(self, qapp, sample_pdf):
        panel = ThumbnailPanel()
        doc = fitz.open(sample_pdf)
        panel.load_document(doc)
        assert len(panel._thumbnails) == 3

        # Reload with a 1-page doc
        doc2 = fitz.open()
        doc2.new_page()
        panel.load_document(doc2)
        assert len(panel._thumbnails) == 1
