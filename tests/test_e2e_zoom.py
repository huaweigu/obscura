"""E2E tests for zoom and fit controls driven through the toolbar.

These exercise the path a user takes: pick "Fit Width" from the zoom combo,
jump to a search result, zoom in to read it.
"""

from app.main_window import MainWindow


def _settle(qapp):
    """Let Qt finish relayout before measuring.

    A single processEvents() is not enough: after a re-render the scroll area
    still reports the previous content height, and set_zoom defers its scroll
    restore to the next event loop turn.
    """
    for _ in range(8):
        qapp.processEvents()


def _open(qapp, path, width=1200, height=800):
    win = MainWindow()
    win.resize(width, height)
    win.show()
    win._open_file_by_path(path)
    _settle(qapp)
    return win


def _close(win):
    for state in win._tab_states:
        if state.doc:
            state.doc.close()
    win.close()


class TestFitFromToolbar:
    def test_fit_width_leaves_no_horizontal_scrollbar(self, qapp, sample_pdf):
        """The bug: fit ignored the viewer's 40px of container margins, so
        'Fit Width' always produced a horizontal scrollbar."""
        win = _open(qapp, sample_pdf)
        try:
            win._zoom_combo.setCurrentText("Fit Width")
            win._on_zoom_combo_activated(win._zoom_combo.currentIndex())
            _settle(qapp)

            viewer = win._viewer
            hbar = viewer.horizontalScrollBar()
            assert hbar.maximum() == 0, "content is wider than the viewport"
        finally:
            _close(win)

    def test_fit_page_leaves_no_scrollbars_for_single_page(self, qapp, tmp_path):
        import fitz

        path = tmp_path / "one.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(str(path))
        doc.close()

        win = _open(qapp, str(path))
        try:
            win._zoom_combo.setCurrentText("Fit Page")
            win._on_zoom_combo_activated(win._zoom_combo.currentIndex())
            _settle(qapp)

            viewer = win._viewer
            assert viewer.horizontalScrollBar().maximum() == 0
            assert viewer.verticalScrollBar().maximum() == 0
        finally:
            _close(win)

    def test_fit_width_adapts_to_panel_being_open(self, qapp, sample_pdf):
        """Opening the panel shrinks the viewport; a fresh Fit Width must
        use the new width, not the old one."""
        win = _open(qapp, sample_pdf)
        try:
            win._fit_width()
            _settle(qapp)
            wide_zoom = win._viewer.zoom

            win._toggle_panel()
            _settle(qapp)
            win._fit_width()
            _settle(qapp)

            assert win._viewer.zoom < wide_zoom
            assert win._viewer.horizontalScrollBar().maximum() == 0
        finally:
            _close(win)


class TestDocumentOpensFitted:
    """Opening at a fixed 100% left the page as a narrow column with dead
    space either side. Viewers fit the page to the window instead."""

    def test_document_fills_the_window_width_on_open(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            viewer = win._viewer
            assert viewer.fit_mode == "width"

            page_px = viewer._page_labels[0].pixmap().width()
            margins = viewer._layout.contentsMargins()
            used = page_px + margins.left() + margins.right()

            # The page should occupy essentially the whole viewport, and never
            # overflow it.
            assert used <= viewer.viewport().width()
            assert used >= viewer.viewport().width() - 40
            assert viewer.horizontalScrollBar().maximum() == 0
        finally:
            _close(win)

    def test_open_starts_at_the_top_of_page_one(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            assert win._viewer.verticalScrollBar().value() == 0
            assert win._viewer.current_page() == 1
        finally:
            _close(win)

    def test_zoom_box_shows_the_fit_mode(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            assert win._zoom_combo.currentText() == "Fit Width"
        finally:
            _close(win)

    def test_explicit_zoom_leaves_fit_mode(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            win._apply_zoom_text("125%")
            _settle(qapp)
            assert win._viewer.fit_mode is None
            assert win._zoom_combo.currentText() == "125%"
        finally:
            _close(win)

    def test_zoom_buttons_leave_fit_mode(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            win._zoom_in()
            _settle(qapp)
            assert win._viewer.fit_mode is None
        finally:
            _close(win)


class TestFitIsSticky:
    def test_opening_the_panel_refits_the_page(self, qapp, sample_pdf):
        """The panel steals ~260px; a sticky fit must give the page the new
        width rather than leaving a stale zoom."""
        win = _open(qapp, sample_pdf)
        try:
            wide_zoom = win._viewer.zoom

            win._toggle_panel()
            _settle(qapp)

            assert win._viewer.zoom < wide_zoom
            assert win._viewer.horizontalScrollBar().maximum() == 0
            assert win._viewer.fit_mode == "width"
        finally:
            _close(win)

    def test_resizing_the_window_refits_the_page(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            before = win._viewer.zoom

            win.resize(800, 800)
            _settle(qapp)
            assert win._viewer.zoom < before

            win.resize(1400, 800)
            _settle(qapp)
            assert win._viewer.zoom > before
            assert win._viewer.horizontalScrollBar().maximum() == 0
        finally:
            _close(win)

    def test_explicit_zoom_is_not_undone_by_a_resize(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            win._apply_zoom_text("150%")
            _settle(qapp)

            win.resize(900, 800)
            _settle(qapp)

            assert win._viewer.fit_mode is None
            assert win._viewer.zoom == 1.5
        finally:
            _close(win)

    def test_refitting_when_already_fitted_does_not_rerender(
        self, qapp, sample_pdf
    ):
        """Guards the feedback loop: a re-render toggles the scrollbar, which
        resizes the viewport, which would schedule another fit forever."""
        win = _open(qapp, sample_pdf)
        try:
            labels_before = list(win._viewer._page_labels)
            assert win._viewer._apply_fit() is False
            assert win._viewer._page_labels == labels_before
            assert win._viewer._fit_pending is False
        finally:
            _close(win)


class TestSearchThenZoomWorkflow:
    def test_zooming_keeps_the_active_result_marked(self, qapp, sample_pdf):
        """Full user path: search, click a result, zoom in to read it."""
        win = _open(qapp, sample_pdf)
        try:
            win._do_search("SECRET_DATA_123")
            result = win._current_state.search_results[2]
            win._on_result_clicked(result.page_index, result.rect)
            _settle(qapp)

            marked = win._viewer._page_labels[result.page_index]
            assert marked._active_highlight is not None

            win._zoom_in()
            _settle(qapp)

            still_marked = win._viewer._page_labels[result.page_index]
            assert still_marked._active_highlight is not None
            # And the yellow match highlights are still there too.
            assert len(still_marked.highlights) > 0
        finally:
            _close(win)

    def test_zoom_keeps_the_reader_on_the_same_page(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            # Leave fit mode first, so the scroll position under test is not
            # being re-derived by a pending re-fit.
            win._apply_zoom_text("100%")
            _settle(qapp)
            win._goto_page(3)
            _settle(qapp)
            before = win._viewer.current_page()
            assert before == 3

            win._apply_zoom_text("200%")
            _settle(qapp)

            assert win._viewer.current_page() == before
            assert win._page_label.text() == f"{before} / 3"
        finally:
            _close(win)
