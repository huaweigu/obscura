import fitz
import pytest
from PySide6.QtWidgets import QApplication

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


# ── TestFitModes ────────────────────────────────────────────


def _settle():
    """Let Qt finish relayout before measuring."""
    for _ in range(8):
        QApplication.processEvents()


def _page_fits_horizontally(viewer, label):
    """The rendered page plus the container margins must fit the viewport.

    viewport().width() already excludes a visible scrollbar, so the scrollbar
    must not be subtracted again here.
    """
    margins = viewer._layout.contentsMargins()
    needed = label.pixmap().width() + margins.left() + margins.right()
    return needed <= viewer.viewport().width()


def _shown_viewer(doc, width=900, height=700):
    """A viewer with a real viewport size, so fit maths is meaningful."""
    viewer = PdfViewer()
    viewer.resize(width, height)
    viewer.load_document(doc)
    viewer.show()
    _settle()
    return viewer


class TestFitModes:
    def test_fit_width_does_not_overflow(self, qapp, sample_pdf):
        doc = fitz.open(sample_pdf)
        viewer = _shown_viewer(doc)
        try:
            viewer.fit_width()
            _settle()

            assert _page_fits_horizontally(viewer, viewer._page_labels[0])
            assert viewer.horizontalScrollBar().maximum() == 0
        finally:
            viewer.close()
            doc.close()

    def test_fit_width_uses_widest_page(self, qapp, tmp_path):
        """A landscape page must not be cut off because page 0 is portrait."""
        path = tmp_path / "mixed.pdf"
        doc = fitz.open()
        doc.new_page(width=400, height=800)   # portrait
        doc.new_page(width=1000, height=400)  # much wider
        doc.save(str(path))
        doc.close()

        doc = fitz.open(str(path))
        viewer = _shown_viewer(doc)
        try:
            viewer.fit_width()
            _settle()

            widest = max(p.rect.width for p in doc)
            # _fit_available() is normalised to "both scrollbars showing", so
            # it reads the same before and after the fit.
            expected = viewer._fit_available()[0] / widest
            assert viewer.zoom == pytest.approx(expected, rel=1e-6)

            # Every page fits, not just the portrait one at index 0.
            for lbl in viewer._page_labels:
                assert _page_fits_horizontally(viewer, lbl)
            assert viewer.horizontalScrollBar().maximum() == 0
        finally:
            viewer.close()
            doc.close()

    def test_fit_page_fits_both_axes(self, qapp, sample_pdf):
        doc = fitz.open(sample_pdf)
        viewer = _shown_viewer(doc)
        try:
            viewer.fit_page()
            _settle()

            margins = viewer._layout.contentsMargins()
            pix = viewer._page_labels[0].pixmap()
            assert _page_fits_horizontally(viewer, viewer._page_labels[0])
            assert (
                pix.height() + margins.top() + margins.bottom()
                <= viewer.viewport().height()
            )
        finally:
            viewer.close()
            doc.close()

    def test_fit_on_empty_viewer_is_a_noop(self, qapp):
        viewer = PdfViewer()
        viewer.fit_width()
        viewer.fit_page()
        assert viewer.zoom == 1.0

    def test_apply_fit_always_reports_a_bool(self, qapp, sample_pdf):
        """_run_pending_fit uses the answer to tell a converged fit from one
        still settling, so None would be read as 'converged'."""
        viewer = PdfViewer()
        assert viewer._apply_fit() is False  # no document

        doc = fitz.open(sample_pdf)
        viewer.load_document(doc)
        try:
            assert isinstance(viewer._apply_fit(), bool)
            viewer.show()
            viewer.resize(900, 700)
            _settle()
            assert isinstance(viewer._apply_fit(), bool)
        finally:
            viewer.close()
            doc.close()

    def test_reload_can_keep_the_scroll_position(self, qapp, sample_pdf):
        doc = fitz.open(sample_pdf)
        viewer = _shown_viewer(doc)
        try:
            viewer.scroll_to_page(2)
            _settle()
            before = viewer.verticalScrollBar().value()
            assert before > 0

            viewer.load_document(doc, reset_position=False)
            _settle()
            assert viewer.verticalScrollBar().value() > 0

            viewer.load_document(doc)  # default: opening a file starts at top
            _settle()
            assert viewer.verticalScrollBar().value() == 0
        finally:
            viewer.close()
            doc.close()


# ── TestZoomStability ───────────────────────────────────────


class TestZoomStability:
    def test_active_highlight_survives_zoom(self, qapp, sample_pdf):
        """Jump to a match, zoom in to read it — the marker must stay."""
        doc = fitz.open(sample_pdf)
        viewer = _shown_viewer(doc)
        try:
            rect = doc[1].search_for("SECRET_DATA_123")[0]
            viewer.set_active_highlight(1, rect)
            assert viewer._page_labels[1]._active_highlight is not None

            viewer.set_zoom(2.0)
            _settle()

            assert viewer._page_labels[1]._active_highlight is not None
            assert viewer._page_labels[0]._active_highlight is None
        finally:
            viewer.close()
            doc.close()

    def test_search_highlights_survive_zoom(self, qapp, sample_pdf):
        doc = fitz.open(sample_pdf)
        viewer = _shown_viewer(doc)
        try:
            rects = doc[0].search_for("SECRET_DATA_123")
            viewer.set_highlights({0: rects})
            viewer.set_zoom(1.75)
            _settle()
            assert len(viewer._page_labels[0].highlights) == len(rects)
        finally:
            viewer.close()
            doc.close()

    def test_clear_active_highlight_is_not_resurrected_by_zoom(self, qapp, sample_pdf):
        doc = fitz.open(sample_pdf)
        viewer = _shown_viewer(doc)
        try:
            rect = doc[0].search_for("SECRET_DATA_123")[0]
            viewer.set_active_highlight(0, rect)
            viewer.clear_active_highlight()
            viewer.set_zoom(1.5)
            _settle()
            assert viewer._page_labels[0]._active_highlight is None
        finally:
            viewer.close()
            doc.close()

    def test_scroll_position_preserved_across_zoom(self, qapp, sample_pdf):
        """Zooming should keep you on the page you were reading."""
        doc = fitz.open(sample_pdf)
        viewer = _shown_viewer(doc)
        try:
            viewer.scroll_to_page(2)
            _settle()
            before = viewer.current_page()

            viewer.set_zoom(2.0)
            _settle()

            assert viewer.current_page() == before
        finally:
            viewer.close()
            doc.close()

    def test_zoom_cancels_open_inline_editor(self, qapp, sample_pdf):
        """A re-render must not orphan the QLineEdit overlay."""
        doc = fitz.open(sample_pdf)
        viewer = _shown_viewer(doc)
        try:
            viewer.set_editor_mode_enabled(True)
            lbl = viewer._page_labels[0]
            lbl._start_inline_edit(80, 80)
            assert lbl._inline_editor is not None

            viewer.set_zoom(1.5)
            _settle()

            for new_lbl in viewer._page_labels:
                assert new_lbl._inline_editor is None
        finally:
            viewer.close()
            doc.close()
