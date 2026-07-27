"""E2E tests for multi-tab and mode-switching interactions."""


class TestMultiTabWorkflow:
    def test_open_two_files(self, main_window, sample_pdf, second_sample_pdf):
        main_window._open_file_by_path(sample_pdf)
        main_window._open_file_by_path(second_sample_pdf)
        assert main_window._tab_widget.count() == 2

    def test_switch_tabs_shows_correct_doc(self, main_window, sample_pdf, second_sample_pdf):
        main_window._open_file_by_path(sample_pdf)
        main_window._open_file_by_path(second_sample_pdf)
        main_window._tab_widget.setCurrentIndex(0)
        assert len(main_window._doc) == 3  # sample_pdf has 3 pages
        main_window._tab_widget.setCurrentIndex(1)
        assert len(main_window._doc) == 1  # second_sample_pdf has 1 page

    def test_search_results_isolated_per_tab(self, main_window, sample_pdf, second_sample_pdf):
        main_window._open_file_by_path(sample_pdf)
        main_window._open_file_by_path(second_sample_pdf)
        main_window._tab_widget.setCurrentIndex(0)
        main_window._do_search("SECRET_DATA_123")
        assert len(main_window._current_state.search_results) == 6
        main_window._tab_widget.setCurrentIndex(1)
        assert len(main_window._current_state.search_results) == 0

    def test_close_tab_cleans_doc(self, main_window, sample_pdf, second_sample_pdf):
        main_window._open_file_by_path(sample_pdf)
        main_window._open_file_by_path(second_sample_pdf)
        main_window._on_tab_close_requested(0)
        assert main_window._tab_widget.count() == 1
        assert len(main_window._doc) == 1  # only second PDF remains


class TestModeWithPanels:
    # Note: isVisible() returns False when the parent QMainWindow is not shown.
    # Use "not isHidden()" to check the widget's own visibility flag instead.
    #
    # Modes no longer own panel visibility — they only raise the relevant dock.
    # Redact is the exception: it force-opens the panel because there is no
    # other way to enter a search keyword.

    def test_reader_raises_pages_and_leaves_panel_alone(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._switch_mode("reader")
        assert win._raised_dock is win._thumb_dock
        assert win._is_panel_open() is False

    def test_reader_with_open_panel_shows_thumbnails(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._toggle_panel()
        win._switch_mode("reader")
        assert not win._thumb_dock.isHidden()

    def test_redactor_shows_search(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._switch_mode("redactor")
        assert not win._search_dock.isHidden()
        assert win._raised_dock is win._search_dock

    def test_editor_does_not_force_panel_open(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._switch_mode("editor")
        assert win._thumb_dock.isHidden()
        assert win._toc_dock.isHidden()
        assert win._search_dock.isHidden()

    def test_page_label_updates(self, main_window_with_pdf):
        # The initial page label should show page info for the 3-page PDF
        text = main_window_with_pdf._page_label.text()
        assert "/ 3" in text
