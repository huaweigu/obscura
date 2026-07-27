"""E2E tests for the collapsible left panel.

These drive the window the way a user does — real keyboard shortcuts, the real
toolbar action, real file opening — and assert on document width, which is the
thing the user actually cares about.

Note: isVisible() is False while the QMainWindow is not shown on screen, so
these tests use isHidden() (the widget's own flag) and explicit geometry from
a shown window where width matters.
"""

from app.main_window import MainWindow


def _document_width(win):
    """Horizontal space available to the document area."""
    return win.centralWidget().width()


class TestPanelGivesDocumentSpace:
    def test_opening_pdf_leaves_document_full_width(self, qapp, sample_pdf):
        """The reported bug: opening a PDF used to cost ~266px to a panel
        the user never asked for, in a mode that isn't redaction."""
        win = MainWindow()
        try:
            win.resize(1200, 800)
            win.show()
            qapp.processEvents()

            win._open_file_by_path(sample_pdf)
            qapp.processEvents()

            assert win._mode == "reader"
            assert win._is_panel_open() is False
            # Full width minus window frame only — no panel taking a slice.
            assert _document_width(win) >= win.width() - 20
        finally:
            win.close()

    def test_toggling_panel_reclaims_and_returns_space(self, qapp, sample_pdf):
        win = MainWindow()
        try:
            win.resize(1200, 800)
            win.show()
            win._open_file_by_path(sample_pdf)
            qapp.processEvents()

            full = _document_width(win)

            win._toggle_panel()
            qapp.processEvents()
            with_panel = _document_width(win)
            assert with_panel < full

            win._toggle_panel()
            qapp.processEvents()
            assert _document_width(win) == full
        finally:
            win.close()

    def test_switching_read_redact_read_returns_the_space(self, qapp, sample_pdf):
        """Redact borrows the space; coming back to Read must not keep it."""
        win = MainWindow()
        try:
            win.resize(1200, 800)
            win.show()
            win._open_file_by_path(sample_pdf)
            qapp.processEvents()
            full = _document_width(win)

            win._switch_mode("redactor")
            qapp.processEvents()
            assert _document_width(win) < full

            # The user collapses it again and goes back to reading.
            win._toggle_panel()
            win._switch_mode("reader")
            qapp.processEvents()
            assert _document_width(win) == full
        finally:
            win.close()


class TestPanelKeyboardWorkflow:
    def test_ctrl_f_opens_panel_and_focuses_search_input(self, qapp, sample_pdf):
        win = MainWindow()
        try:
            win.show()
            win._open_file_by_path(sample_pdf)
            qapp.processEvents()

            win._focus_search()
            qapp.processEvents()

            assert win._is_panel_open() is True
            assert win._raised_dock is win._search_dock
            assert win._search_panel._search_input.hasFocus()
        finally:
            win.close()

    def test_search_workflow_from_collapsed_panel(self, qapp, sample_pdf):
        """Full path: collapsed panel -> Ctrl+F -> type -> results appear."""
        win = MainWindow()
        try:
            win.show()
            win._open_file_by_path(sample_pdf)
            qapp.processEvents()
            assert win._is_panel_open() is False

            win._focus_search()
            win._search_panel._search_input.setText("SECRET_DATA_123")
            win._search_panel._on_search()
            qapp.processEvents()

            assert len(win._current_state.search_results) == 6
            assert win._search_panel._results_list.count() == 6
            assert win._is_panel_open() is True
        finally:
            win.close()

    def test_toolbar_toggle_action_drives_the_panel(self, qapp, sample_pdf):
        win = MainWindow()
        try:
            win.show()
            win._open_file_by_path(sample_pdf)
            qapp.processEvents()

            win._panel_act.trigger()
            qapp.processEvents()
            assert win._is_panel_open() is True

            win._panel_act.trigger()
            qapp.processEvents()
            assert win._is_panel_open() is False
        finally:
            win.close()


class TestPanelPersistenceAcrossSessions:
    def test_preference_survives_restart(self, qapp, sample_pdf):
        """Open the panel, 'quit', 'relaunch' — panel is still open."""
        first = MainWindow()
        first.show()
        first._open_file_by_path(sample_pdf)
        first._toggle_panel()
        assert first._is_panel_open() is True
        first.close()

        second = MainWindow()
        try:
            second.show()
            qapp.processEvents()
            assert second._is_panel_open() is True
        finally:
            second.close()

    def test_default_for_a_brand_new_user_is_collapsed(self, qapp):
        # isolated_settings gives each test a clean store, so this window has
        # no stored preference at all — it must fall back to collapsed.
        win = MainWindow()
        try:
            assert win._settings.value("panel/open", None) is None
            assert win._is_panel_open() is False
            assert win._panel_width == 260
        finally:
            win.close()


class TestPanelWithMultipleTabs:
    def test_toc_dock_follows_the_active_tab(
        self, qapp, sample_pdf, sample_pdf_with_toc
    ):
        win = MainWindow()
        try:
            win.show()
            win._open_file_by_path(sample_pdf)          # no TOC
            win._open_file_by_path(sample_pdf_with_toc)  # has TOC
            win._set_panel_open(True)
            qapp.processEvents()

            assert win._has_toc is True
            assert not win._toc_dock.isHidden()

            win._tab_widget.setCurrentIndex(0)
            qapp.processEvents()
            assert win._has_toc is False
            assert win._toc_dock.isHidden()

            win._tab_widget.setCurrentIndex(1)
            qapp.processEvents()
            assert win._has_toc is True
            assert not win._toc_dock.isHidden()
        finally:
            for state in win._tab_states:
                if state.doc:
                    state.doc.close()
            win.close()

    def test_panel_stays_closed_across_tab_switches(
        self, qapp, sample_pdf, second_sample_pdf
    ):
        win = MainWindow()
        try:
            win.show()
            win._open_file_by_path(sample_pdf)
            win._open_file_by_path(second_sample_pdf)
            qapp.processEvents()

            assert win._is_panel_open() is False
            win._tab_widget.setCurrentIndex(0)
            qapp.processEvents()
            assert win._is_panel_open() is False
        finally:
            for state in win._tab_states:
                if state.doc:
                    state.doc.close()
            win.close()
