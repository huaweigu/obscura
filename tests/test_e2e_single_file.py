"""E2E tests for core single-file redaction workflow."""

import fitz
from app.preview_dialog import PreviewDialog
from PySide6.QtWidgets import QMessageBox, QFileDialog


class TestSearchRedactSave:
    def test_full_redact_all_workflow(self, main_window, sample_pdf, tmp_path, monkeypatch):
        # 1. Open PDF
        main_window._open_file_by_path(sample_pdf)
        # 2. Switch to redactor
        main_window._switch_mode("redactor")
        # 3. Search
        main_window._do_search("SECRET_DATA_123")
        state = main_window._current_state
        assert len(state.search_results) == 6
        # 4. Mock preview dialog -> Accepted
        monkeypatch.setattr(PreviewDialog, "exec", lambda self: PreviewDialog.DialogCode.Accepted)
        # 5. Mock QMessageBox.information (called at end of _do_redaction)
        monkeypatch.setattr(QMessageBox, "information", lambda *args: QMessageBox.StandardButton.Ok)
        # 6. Redact all
        main_window._redact_all()
        # 7. Verify text removed from every page
        for i in range(3):
            text = state.doc[i].get_text()
            assert "SECRET_DATA_123" not in text
        # 8. Save and verify the saved file
        save_path = str(tmp_path / "redacted.pdf")
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kw: (save_path, ""))
        main_window._save_file()
        doc2 = fitz.open(save_path)
        for i in range(len(doc2)):
            assert "SECRET_DATA_123" not in doc2[i].get_text()
        doc2.close()

    def test_redact_selected_only(self, main_window, sample_pdf, monkeypatch):
        main_window._open_file_by_path(sample_pdf)
        main_window._switch_mode("redactor")
        main_window._do_search("SECRET_DATA_123")
        state = main_window._current_state
        page0_results = [r for r in state.search_results if r.page_index == 0]
        monkeypatch.setattr(PreviewDialog, "exec", lambda self: PreviewDialog.DialogCode.Accepted)
        monkeypatch.setattr(QMessageBox, "information", lambda *args: QMessageBox.StandardButton.Ok)
        main_window._redact_selected(page0_results)
        # Page 0 should be redacted
        assert "SECRET_DATA_123" not in state.doc[0].get_text()
        # Page 1 should still have the text
        assert "SECRET_DATA_123" in state.doc[1].get_text()

    def test_redact_cancel_preserves_text(self, main_window, sample_pdf, monkeypatch):
        main_window._open_file_by_path(sample_pdf)
        main_window._do_search("SECRET_DATA_123")
        state = main_window._current_state
        monkeypatch.setattr(PreviewDialog, "exec", lambda self: PreviewDialog.DialogCode.Rejected)
        main_window._redact_all()
        # Text should be preserved when user cancels
        assert "SECRET_DATA_123" in state.doc[0].get_text()

    def test_search_redact_search_again(self, main_window, sample_pdf, monkeypatch):
        main_window._open_file_by_path(sample_pdf)
        main_window._do_search("SECRET_DATA_123")
        monkeypatch.setattr(PreviewDialog, "exec", lambda self: PreviewDialog.DialogCode.Accepted)
        monkeypatch.setattr(QMessageBox, "information", lambda *args: QMessageBox.StandardButton.Ok)
        main_window._redact_all()
        # Search again for the same term after redaction
        main_window._do_search("SECRET_DATA_123")
        assert len(main_window._current_state.search_results) == 0


class TestSearchHighlights:
    def test_search_sets_highlights(self, main_window_with_pdf):
        main_window_with_pdf._do_search("SECRET_DATA_123")
        viewer = main_window_with_pdf._viewer
        # Check that at least one page label has highlights
        has_highlights = False
        for pl in viewer._page_labels:
            if pl.highlights:
                has_highlights = True
                break
        assert has_highlights

    def test_result_click_scrolls(self, main_window_with_pdf):
        main_window_with_pdf._do_search("SECRET_DATA_123")
        state = main_window_with_pdf._current_state
        result = state.search_results[0]
        # Should not crash; exercises set_active_highlight + scroll_to_page
        main_window_with_pdf._on_result_clicked(result.page_index, result.rect)

    def test_new_search_replaces_old(self, main_window_with_pdf):
        main_window_with_pdf._do_search("SECRET_DATA_123")
        state = main_window_with_pdf._current_state
        assert len(state.search_results) == 6
        main_window_with_pdf._do_search("NONEXISTENT_TERM")
        assert len(state.search_results) == 0
