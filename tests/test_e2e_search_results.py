"""E2E tests for the search results list as a redaction-selection tool.

The list is how a user picks *which* occurrence to redact, so rows have to be
distinguishable from one another.
"""

import fitz
import pytest

from app.main_window import MainWindow


@pytest.fixture()
def mixed_context_pdf(tmp_path):
    """Two pages, each with the same keyword in clearly different sentences."""
    path = tmp_path / "mixed_context.pdf"
    doc = fitz.open()

    page = doc.new_page()
    page.insert_text((72, 100), "Invoice for ACME sent in January", fontsize=11)
    page.insert_text((72, 160), "Refund to ACME issued in March", fontsize=11)

    page = doc.new_page()
    page.insert_text((72, 100), "Contract with ACME signed in June", fontsize=11)

    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture()
def auto_confirm_redaction(monkeypatch):
    """Accept the preview dialog and swallow the 'applied' confirmation.

    Both are modal: left alone, QMessageBox.information blocks the test run.
    """
    from PySide6.QtWidgets import QMessageBox

    from app.preview_dialog import PreviewDialog

    monkeypatch.setattr(
        PreviewDialog, "exec", lambda self: PreviewDialog.DialogCode.Accepted
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok),
    )


def _open(qapp, path):
    win = MainWindow()
    win.show()
    win._open_file_by_path(path)
    qapp.processEvents()
    return win


def _close(win):
    for state in win._tab_states:
        if state.doc:
            state.doc.close()
    win.close()


class TestResultsListIsUsable:
    def test_list_rows_are_distinguishable(self, qapp, mixed_context_pdf):
        """The bug: every row on a page showed the page's first match, so the
        list could not be used to choose an occurrence."""
        win = _open(qapp, mixed_context_pdf)
        try:
            win._do_search("ACME")
            qapp.processEvents()

            rows = [
                win._search_panel._results_list.item(i).text()
                for i in range(win._search_panel._results_list.count())
            ]
            assert len(rows) == 3
            assert len(set(rows)) == 3, f"duplicate rows: {rows}"

            assert "Invoice" in rows[0]
            assert "Refund" in rows[1]
            assert "Contract" in rows[2]
        finally:
            _close(win)

    def test_rows_are_labelled_with_their_page(self, qapp, mixed_context_pdf):
        win = _open(qapp, mixed_context_pdf)
        try:
            win._do_search("ACME")
            qapp.processEvents()
            panel = win._search_panel
            assert panel._results_list.item(0).text().startswith("Page 1:")
            assert panel._results_list.item(1).text().startswith("Page 1:")
            assert panel._results_list.item(2).text().startswith("Page 2:")
        finally:
            _close(win)


class TestRedactSelectedUsesTheRightMatch:
    def test_redacting_one_row_removes_only_that_occurrence(
        self, qapp, mixed_context_pdf, auto_confirm_redaction
    ):
        """Pick the second row and confirm the first occurrence survives."""
        win = _open(qapp, mixed_context_pdf)
        try:
            win._do_search("ACME")
            results = win._current_state.search_results
            second = results[1]  # the "Refund" occurrence on page 1
            assert "Refund" in second.snippet

            win._redact_selected([second])
            qapp.processEvents()

            text = win._doc[0].get_text("text")
            assert "Refund to ACME" not in text
            assert "Invoice for ACME" in text
        finally:
            _close(win)

    def test_search_after_redaction_finds_the_remainder(
        self, qapp, mixed_context_pdf, auto_confirm_redaction
    ):
        win = _open(qapp, mixed_context_pdf)
        try:
            win._do_search("ACME")
            win._redact_selected([win._current_state.search_results[1]])
            qapp.processEvents()

            win._do_search("ACME")
            remaining = [r.snippet for r in win._current_state.search_results]
            assert len(remaining) == 2
            assert len(set(remaining)) == 2
        finally:
            _close(win)
