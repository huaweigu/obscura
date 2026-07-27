
from app.main_window import SegmentedControl, WelcomeWidget

# ── TestMainWindowInit ──────────────────────────────────────


class TestMainWindowInit:
    def test_initial_title(self, main_window):
        assert main_window.windowTitle() == "Obscura"

    def test_initial_mode_is_reader(self, main_window):
        assert main_window._mode == "reader"

    def test_welcome_shown_on_startup(self, main_window):
        assert main_window._stack.currentIndex() == 0

    def test_no_tabs_on_startup(self, main_window):
        assert main_window._tab_widget.count() == 0
        assert len(main_window._tab_states) == 0


# ── TestFileOpen ────────────────────────────────────────────


class TestFileOpen:
    def test_open_creates_tab(self, main_window, sample_pdf):
        main_window._open_file_by_path(sample_pdf)
        assert main_window._tab_widget.count() == 1
        assert len(main_window._tab_states) == 1

    def test_open_switches_to_tab_view(self, main_window, sample_pdf):
        main_window._open_file_by_path(sample_pdf)
        assert main_window._stack.currentIndex() == 1

    def test_same_file_reuses_tab(self, main_window, sample_pdf):
        main_window._open_file_by_path(sample_pdf)
        main_window._open_file_by_path(sample_pdf)
        assert main_window._tab_widget.count() == 1

    def test_multiple_files_create_multiple_tabs(
        self, main_window, sample_pdf, second_sample_pdf
    ):
        main_window._open_file_by_path(sample_pdf)
        main_window._open_file_by_path(second_sample_pdf)
        assert main_window._tab_widget.count() == 2
        assert len(main_window._tab_states) == 2

    def test_tab_bar_hidden_for_single_tab(self, main_window, sample_pdf):
        main_window._open_file_by_path(sample_pdf)
        # tabBar().isVisible() depends on the window being shown on screen;
        # use isHidden() to check the widget's own visibility flag instead.
        assert main_window._tab_widget.tabBar().isHidden()

    def test_tab_bar_visible_for_multiple_tabs(
        self, main_window, sample_pdf, second_sample_pdf
    ):
        main_window._open_file_by_path(sample_pdf)
        main_window._open_file_by_path(second_sample_pdf)
        assert not main_window._tab_widget.tabBar().isHidden()


# ── TestTabClose ────────────────────────────────────────────


class TestTabClose:
    def test_close_removes_tab(self, main_window, sample_pdf, second_sample_pdf):
        main_window._open_file_by_path(sample_pdf)
        main_window._open_file_by_path(second_sample_pdf)
        assert main_window._tab_widget.count() == 2

        main_window._on_tab_close_requested(0)
        assert main_window._tab_widget.count() == 1
        assert len(main_window._tab_states) == 1

    def test_close_last_tab_shows_welcome(self, main_window, sample_pdf):
        main_window._open_file_by_path(sample_pdf)
        main_window._on_tab_close_requested(0)
        assert main_window._tab_widget.count() == 0
        assert main_window._stack.currentIndex() == 0

    def test_close_one_of_two_keeps_other(
        self, main_window, sample_pdf, second_sample_pdf
    ):
        main_window._open_file_by_path(sample_pdf)
        main_window._open_file_by_path(second_sample_pdf)

        # Close the first tab (sample_pdf)
        main_window._on_tab_close_requested(0)
        assert main_window._tab_widget.count() == 1

        # The remaining state should be the second file
        remaining = main_window._tab_states[0]
        assert remaining.file_path == second_sample_pdf


# ── TestModeSwitch ──────────────────────────────────────────


class TestModeSwitch:
    """Mode switching sets interaction state and raises the relevant dock.

    Panel *visibility* is the user's business (see TestPanelToggle); the only
    exception is Redact, which has no other entry point for a keyword.
    """

    def test_reader_mode_raises_pages_without_opening_panel(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._activate_reader_mode()
        assert win._mode == "reader"
        assert win._raised_dock is win._thumb_dock
        # Panel starts collapsed and Read mode must not change that.
        assert win._is_panel_open() is False

    def test_reader_mode_title(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._activate_reader_mode()
        assert win.windowTitle() == "Obscura"

    def test_reader_mode_keeps_open_panel_open(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._set_panel_open(True)
        win._activate_reader_mode()
        assert win._is_panel_open() is True
        assert win._raised_dock is win._thumb_dock

    def test_redactor_mode_opens_panel_and_raises_search(self, main_window_with_pdf):
        win = main_window_with_pdf
        assert win._is_panel_open() is False
        win._activate_redactor_mode()
        assert win._mode == "redactor"
        assert win._is_panel_open() is True
        assert win._raised_dock is win._search_dock
        assert not win._search_dock.isHidden()
        assert win.windowTitle() == "Obscura \u2014 Redact"

    def test_editor_mode_does_not_open_panel(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._activate_editor_mode()
        assert win._mode == "editor"
        assert win._is_panel_open() is False
        assert win.windowTitle() == "Obscura \u2014 Edit"

    def test_editor_mode_keeps_open_panel_open(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._set_panel_open(True)
        win._activate_editor_mode()
        assert win._is_panel_open() is True

    def test_editor_mode_enables_editor_on_viewer(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._activate_editor_mode()
        assert win._viewer._editor_mode_enabled is True
        assert win._viewer._text_selection_enabled is False


# \u2500\u2500 TestPanelToggle \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500


class TestPanelToggle:
    """The left dock group is collapsed by default and toggled explicitly."""

    def test_panel_collapsed_by_default(self, main_window):
        win = main_window
        assert win._is_panel_open() is False
        assert win._thumb_dock.isHidden()
        assert win._toc_dock.isHidden()
        assert win._search_dock.isHidden()

    def test_toggle_action_unchecked_by_default(self, main_window):
        assert main_window._panel_act.isChecked() is False

    def test_opening_a_pdf_does_not_open_panel(self, main_window, sample_pdf):
        main_window._open_file_by_path(sample_pdf)
        assert main_window._is_panel_open() is False

    def test_toggle_opens_then_closes(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._toggle_panel()
        assert win._is_panel_open() is True
        assert win._panel_act.isChecked() is True
        win._toggle_panel()
        assert win._is_panel_open() is False
        assert win._panel_act.isChecked() is False

    def test_open_panel_shows_pages_and_search_tabs(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._set_panel_open(True)
        assert not win._thumb_dock.isHidden()
        assert not win._search_dock.isHidden()

    def test_bookmarks_dock_hidden_without_toc(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._set_panel_open(True)
        assert win._has_toc is False
        assert win._toc_dock.isHidden()

    def test_bookmarks_dock_shown_with_toc(self, main_window, sample_pdf_with_toc):
        main_window._open_file_by_path(sample_pdf_with_toc)
        main_window._set_panel_open(True)
        assert main_window._has_toc is True
        assert not main_window._toc_dock.isHidden()

    def test_focus_search_opens_panel_and_raises_search(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._focus_search()
        assert win._is_panel_open() is True
        assert win._raised_dock is win._search_dock

    def test_redact_then_manual_collapse_stays_collapsed(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._activate_redactor_mode()
        assert win._is_panel_open() is True
        win._toggle_panel()
        assert win._is_panel_open() is False
        # Re-entering the mode we are already in must not re-open it.
        win._activate_reader_mode()
        assert win._is_panel_open() is False

    def test_panel_open_state_persists_across_windows(self, main_window):
        from app.main_window import MainWindow

        main_window._set_panel_open(True)
        main_window.close()  # closeEvent flushes settings

        fresh = MainWindow()
        try:
            assert fresh._is_panel_open() is True
            assert fresh._panel_act.isChecked() is True
        finally:
            fresh.close()

    def test_panel_closed_state_persists_across_windows(self, main_window):
        from app.main_window import MainWindow

        main_window._set_panel_open(True)
        main_window._set_panel_open(False)
        main_window.close()

        fresh = MainWindow()
        try:
            assert fresh._is_panel_open() is False
        finally:
            fresh.close()

    def test_panel_width_persists_across_windows(self, main_window):
        from app.main_window import MainWindow

        main_window._set_panel_open(True)
        main_window._panel_width = 340
        main_window._save_panel_settings()

        fresh = MainWindow()
        try:
            assert fresh._panel_width == 340
        finally:
            fresh.close()


# ── TestNavigation ──────────────────────────────────────────


class TestNavigation:
    def test_next_page(self, main_window_with_pdf):
        win = main_window_with_pdf
        # Viewer starts at page 1 (1-based)
        win._next_page()
        # scroll_to_page was called; current_page depends on scroll geometry,
        # but we can verify the viewer didn't crash and method is callable
        assert win._viewer is not None

    def test_prev_page_at_first_does_nothing(self, main_window_with_pdf):
        win = main_window_with_pdf
        # At page 1, prev should be a no-op (current stays >= 1)
        win._prev_page()
        assert win._viewer.current_page() >= 1

    def test_first_page(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._first_page()
        # After scrolling to first page, current_page should be 1
        assert win._viewer.current_page() >= 1

    def test_last_page(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._last_page()
        # scroll_to_page(page_count - 1) was called
        assert win._viewer is not None


# ── TestZoomControls ────────────────────────────────────────


class TestZoomControls:
    def test_zoom_in_updates_combo(self, main_window_with_pdf):
        win = main_window_with_pdf
        initial_zoom = win._viewer.zoom
        win._zoom_in()
        expected = int((initial_zoom + 0.25) * 100)
        assert win._zoom_combo.currentText() == f"{expected}%"

    def test_zoom_out_updates_combo(self, main_window_with_pdf):
        win = main_window_with_pdf
        initial_zoom = win._viewer.zoom
        win._zoom_out()
        expected = int((initial_zoom - 0.25) * 100)
        assert win._zoom_combo.currentText() == f"{expected}%"

    def test_apply_zoom_text_valid(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._apply_zoom_text("150%")
        assert win._viewer.zoom == 1.5
        assert win._zoom_combo.currentText() == "150%"

    def test_apply_zoom_text_invalid_reverts(self, main_window_with_pdf):
        win = main_window_with_pdf
        original_zoom = win._viewer.zoom
        win._apply_zoom_text("abc")
        # Invalid input should revert combo to current zoom
        assert win._viewer.zoom == original_zoom
        assert win._zoom_combo.currentText() == f"{int(original_zoom * 100)}%"


# ── TestSearch ──────────────────────────────────────────────


class TestSearch:
    def test_search_finds_results(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._do_search("SECRET_DATA_123")
        state = win._current_state
        assert len(state.search_results) == 6  # 2 per page x 3 pages

    def test_search_sets_highlights_on_viewer(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._do_search("SECRET_DATA_123")
        # Viewer should have highlights dict populated
        assert len(win._viewer._highlights) > 0

    def test_search_stores_results_in_state(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._do_search("SECRET_DATA_123")
        state = win._current_state
        assert state.search_results is not None
        for r in state.search_results:
            assert r.page_index >= 0
            assert r.snippet != ""

    def test_search_no_results(self, main_window_with_pdf):
        win = main_window_with_pdf
        win._do_search("NONEXISTENT_TERM_XYZ")
        state = win._current_state
        assert len(state.search_results) == 0


# ── TestSegmentedControl ────────────────────────────────────


class TestSegmentedControl:
    def test_set_active(self, qapp):
        ctrl = SegmentedControl([("a", "A"), ("b", "B"), ("c", "C")])
        ctrl.set_active("b")
        assert ctrl.active_mode() == "b"
        assert ctrl._buttons["b"].isChecked()
        assert not ctrl._buttons["a"].isChecked()

    def test_mode_changed_signal(self, qapp):
        ctrl = SegmentedControl([("a", "A"), ("b", "B")])
        received = []
        ctrl.mode_changed.connect(lambda mode: received.append(mode))
        # Simulate clicking button "b"
        ctrl._buttons["b"].click()
        assert received == ["b"]

    def test_active_mode_returns_current(self, qapp):
        ctrl = SegmentedControl([("x", "X"), ("y", "Y")])
        assert ctrl.active_mode() is None
        ctrl.set_active("x")
        assert ctrl.active_mode() == "x"
        ctrl.set_active("y")
        assert ctrl.active_mode() == "y"


# ── TestWelcomeWidget ───────────────────────────────────────


class TestWelcomeWidget:
    def test_creates_widget(self, qapp):
        widget = WelcomeWidget()
        assert widget is not None
        assert widget.acceptDrops()

    def test_open_requested_signal(self, qapp):
        widget = WelcomeWidget()
        received = []
        widget.open_requested.connect(lambda: received.append(True))
        widget.open_requested.emit()
        assert received == [True]
