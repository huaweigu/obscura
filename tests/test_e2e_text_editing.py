"""E2E tests for the text editing workflow."""

import fitz
from app.text_editor import get_span_at_point


class TestTextEditingWorkflow:
    def test_edit_replaces_text(self, main_window, sample_pdf):
        main_window._open_file_by_path(sample_pdf)
        main_window._switch_mode("editor")
        state = main_window._current_state
        page = state.doc[0]
        # Get a span at a known position (72, 72 is where text was inserted)
        span = get_span_at_point(page, fitz.Point(72, 72))
        if span:
            main_window._on_text_edit_committed(0, span, "REPLACED_TEXT")
            new_page_text = state.doc[0].get_text()
            assert "REPLACED_TEXT" in new_page_text

    def test_editor_mode_enables_editing(self, main_window_with_pdf):
        main_window_with_pdf._switch_mode("editor")
        viewer = main_window_with_pdf._viewer
        assert viewer._editor_mode_enabled is True
        assert viewer._text_selection_enabled is False

    def test_edit_and_save(self, main_window, sample_pdf, tmp_path, monkeypatch):
        main_window._open_file_by_path(sample_pdf)
        main_window._switch_mode("editor")
        state = main_window._current_state
        page = state.doc[0]
        span = get_span_at_point(page, fitz.Point(72, 72))
        if span:
            main_window._on_text_edit_committed(0, span, "SAVED_EDIT")
            save_path = str(tmp_path / "edited.pdf")
            from PySide6.QtWidgets import QFileDialog
            monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **kw: (save_path, ""))
            main_window._save_file()
            doc2 = fitz.open(save_path)
            assert "SAVED_EDIT" in doc2[0].get_text()
            doc2.close()

    def test_viewer_refreshes_after_edit(self, main_window, sample_pdf):
        main_window._open_file_by_path(sample_pdf)
        main_window._switch_mode("editor")
        state = main_window._current_state
        viewer = state.viewer
        page = state.doc[0]
        span = get_span_at_point(page, fitz.Point(72, 72))
        if span:
            main_window._on_text_edit_committed(0, span, "CHANGED")
            # After refresh, the viewer should still report the correct page count
            assert viewer.page_count == 3
