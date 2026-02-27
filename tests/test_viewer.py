import fitz
import pytest

from app.pdf_viewer import PdfViewer


class TestPdfViewer:
    def test_initial_state(self, qapp):
        viewer = PdfViewer()
        assert viewer.doc is None
        assert viewer.page_count == 0
        assert viewer.current_page() == 0

    def test_load_document(self, qapp, sample_pdf):
        viewer = PdfViewer()
        doc = fitz.open(sample_pdf)
        viewer.load_document(doc)
        assert viewer.doc is doc
        assert viewer.page_count == 3
        assert len(viewer._page_labels) == 3

    def test_zoom_bounds(self, qapp, sample_pdf):
        viewer = PdfViewer()
        doc = fitz.open(sample_pdf)
        viewer.load_document(doc)

        viewer.set_zoom(0.01)
        assert viewer.zoom == 0.05  # clamped to min

        viewer.set_zoom(10.0)
        assert viewer.zoom == 5.0  # clamped to max

    def test_zoom_in_out(self, qapp, sample_pdf):
        viewer = PdfViewer()
        doc = fitz.open(sample_pdf)
        viewer.load_document(doc)
        initial = viewer.zoom

        viewer.zoom_in()
        assert viewer.zoom == initial + 0.25

        viewer.zoom_out()
        assert viewer.zoom == initial

    def test_set_and_clear_highlights(self, qapp, sample_pdf):
        viewer = PdfViewer()
        doc = fitz.open(sample_pdf)
        viewer.load_document(doc)

        rects = doc[0].search_for("SECRET_DATA_123")
        viewer.set_highlights({0: rects})
        assert len(viewer._page_labels[0].highlights) == len(rects)
        assert len(viewer._page_labels[1].highlights) == 0

        viewer.clear_highlights()
        assert len(viewer._page_labels[0].highlights) == 0

    def test_refresh_rerenders(self, qapp, sample_pdf):
        viewer = PdfViewer()
        doc = fitz.open(sample_pdf)
        viewer.load_document(doc)
        old_labels = list(viewer._page_labels)

        viewer.refresh()
        # Labels should be new objects after refresh
        assert len(viewer._page_labels) == 3
        for old_lbl in old_labels:
            assert old_lbl not in viewer._page_labels
