"""E2E tests for document lifecycle and unsaved-change protection.

Redaction is destructive and irreversible — the preview dialog says so — but
until now closing a tab or quitting discarded applied redactions with no
prompt at all.
"""

import os

import fitz
import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from app.main_window import MainWindow
from app.preview_dialog import PreviewDialog


@pytest.fixture()
def accept_preview(monkeypatch):
    """Confirm the redaction preview and swallow the 'applied' notice."""
    monkeypatch.setattr(
        PreviewDialog, "exec", lambda self: PreviewDialog.DialogCode.Accepted
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
    )


@pytest.fixture()
def answer_discard_prompt(monkeypatch):
    """Drive the Save/Discard/Cancel prompt; returns a setter for the answer."""
    answers = {"button": QMessageBox.StandardButton.Discard}
    calls = []

    def _fake_warning(*args, **kwargs):
        calls.append(args)
        return answers["button"]

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(_fake_warning))

    def _set(button):
        answers["button"] = button

    _set.calls = calls
    return _set


def _open(qapp, path):
    win = MainWindow()
    win.show()
    win._open_file_by_path(path)
    qapp.processEvents()
    return win


def _force_close(win):
    for state in win._tab_states:
        if state.doc and not state.doc.is_closed:
            state.doc.close()
        state.is_dirty = False
    win._tab_states.clear()
    win.close()


class TestDirtyTracking:
    def test_new_document_is_clean(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            assert win._current_state.is_dirty is False
        finally:
            _force_close(win)

    def test_redaction_marks_document_dirty(self, qapp, sample_pdf, accept_preview):
        win = _open(qapp, sample_pdf)
        try:
            win._do_search("SECRET_DATA_123")
            win._redact_all()
            qapp.processEvents()
            assert win._current_state.is_dirty is True
        finally:
            _force_close(win)

    def test_cancelled_redaction_leaves_document_clean(
        self, qapp, sample_pdf, monkeypatch
    ):
        monkeypatch.setattr(
            PreviewDialog, "exec", lambda self: PreviewDialog.DialogCode.Rejected
        )
        win = _open(qapp, sample_pdf)
        try:
            win._do_search("SECRET_DATA_123")
            win._redact_all()
            qapp.processEvents()
            assert win._current_state.is_dirty is False
        finally:
            _force_close(win)

    def test_dirty_document_is_marked_in_the_tab_title(
        self, qapp, sample_pdf, accept_preview
    ):
        win = _open(qapp, sample_pdf)
        try:
            assert "•" not in win._tab_widget.tabText(0)
            win._do_search("SECRET_DATA_123")
            win._redact_all()
            qapp.processEvents()
            assert "•" in win._tab_widget.tabText(0)
        finally:
            _force_close(win)

    def test_saving_clears_dirty(self, qapp, sample_pdf, accept_preview):
        win = _open(qapp, sample_pdf)
        try:
            win._do_search("SECRET_DATA_123")
            win._redact_all()
            assert win._current_state.is_dirty is True

            win._quick_save()
            qapp.processEvents()
            assert win._current_state.is_dirty is False
            assert "•" not in win._tab_widget.tabText(0)
        finally:
            _force_close(win)


class TestSavingKeepsTheReadersPlace:
    def test_save_does_not_jump_back_to_page_one(
        self, qapp, tmp_path, monkeypatch
    ):
        """The save fallback reloads the document. Reloading must not be
        confused with opening one, which starts at the top."""
        path = tmp_path / "long.pdf"
        doc = fitz.open()
        for i in range(20):
            doc.new_page().insert_text((72, 72), f"Page {i + 1}")
        doc.save(str(path))
        doc.close()

        win = MainWindow()
        win.resize(1200, 800)
        win.show()
        win._open_file_by_path(str(path))
        for _ in range(15):
            qapp.processEvents()
        try:
            win._goto_page(12)
            for _ in range(15):
                qapp.processEvents()
            before = win._viewer.current_page()
            assert before == 12

            # Force the fallback path that reloads the document.
            monkeypatch.setattr(
                fitz.Document,
                "saveIncr",
                lambda self: (_ for _ in ()).throw(RuntimeError("no incr")),
            )
            win._quick_save()
            for _ in range(15):
                qapp.processEvents()

            assert win._viewer.current_page() == before
        finally:
            _force_close(win)


class TestDirtyMarkerTargetsTheRightTab:
    def test_marking_uses_identity_not_equality(
        self, qapp, sample_pdf, second_sample_pdf, accept_preview
    ):
        """DocumentState is a dataclass, so == compares fields. Looking a tab
        up by equality can resolve to the wrong index."""
        win = MainWindow()
        win.show()
        win._open_file_by_path(sample_pdf)
        win._open_file_by_path(second_sample_pdf)
        qapp.processEvents()
        try:
            win._tab_widget.setCurrentIndex(1)
            win._do_search("UNIQUE_TERM_456")
            win._redact_all()
            qapp.processEvents()

            assert "•" in win._tab_widget.tabText(1)
            assert "•" not in win._tab_widget.tabText(0)
            assert win._tab_states[0].is_dirty is False
            assert win._tab_states[1].is_dirty is True
        finally:
            _force_close(win)

    def test_tab_index_of_returns_the_identical_state(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            state = win._tab_states[0]
            assert win._tab_index_of(state) == 0
            # A structurally-equal state that is not in the list must not match.
            import copy

            assert win._tab_index_of(copy.copy(state)) == -1
        finally:
            _force_close(win)


class TestCloseProtection:
    def test_closing_clean_tab_does_not_prompt(
        self, qapp, sample_pdf, answer_discard_prompt
    ):
        win = _open(qapp, sample_pdf)
        try:
            win._on_tab_close_requested(0)
            assert win._tab_widget.count() == 0
            assert answer_discard_prompt.calls == []
        finally:
            _force_close(win)

    def test_cancelling_the_prompt_keeps_the_tab(
        self, qapp, sample_pdf, accept_preview, answer_discard_prompt
    ):
        win = _open(qapp, sample_pdf)
        try:
            win._do_search("SECRET_DATA_123")
            win._redact_all()

            answer_discard_prompt(QMessageBox.StandardButton.Cancel)
            win._on_tab_close_requested(0)

            assert win._tab_widget.count() == 1
            assert len(win._tab_states) == 1
            assert win._current_state.doc.is_closed is False
        finally:
            _force_close(win)

    def test_discarding_closes_the_tab(
        self, qapp, sample_pdf, accept_preview, answer_discard_prompt
    ):
        win = _open(qapp, sample_pdf)
        try:
            win._do_search("SECRET_DATA_123")
            win._redact_all()

            answer_discard_prompt(QMessageBox.StandardButton.Discard)
            win._on_tab_close_requested(0)

            assert win._tab_widget.count() == 0
            assert len(win._tab_states) == 0
        finally:
            _force_close(win)

    def test_save_from_the_prompt_writes_the_file(
        self, qapp, tmp_path, accept_preview, answer_discard_prompt
    ):
        path = tmp_path / "save_me.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "REMOVE_ME stays until saved")
        doc.save(str(path))
        doc.close()

        win = _open(qapp, str(path))
        try:
            win._do_search("REMOVE_ME")
            win._redact_all()

            answer_discard_prompt(QMessageBox.StandardButton.Save)
            win._on_tab_close_requested(0)
            qapp.processEvents()

            assert win._tab_widget.count() == 0
            reopened = fitz.open(str(path))
            assert "REMOVE_ME" not in reopened[0].get_text("text")
            reopened.close()
        finally:
            _force_close(win)

    def test_quitting_with_unsaved_work_prompts_and_can_be_cancelled(
        self, qapp, sample_pdf, accept_preview, answer_discard_prompt
    ):
        win = _open(qapp, sample_pdf)
        try:
            win._do_search("SECRET_DATA_123")
            win._redact_all()

            answer_discard_prompt(QMessageBox.StandardButton.Cancel)
            event = QCloseEvent()
            win.closeEvent(event)

            assert event.isAccepted() is False
            assert len(win._tab_states) == 1
        finally:
            _force_close(win)

    def test_quitting_clean_is_not_interrupted(
        self, qapp, sample_pdf, answer_discard_prompt
    ):
        win = _open(qapp, sample_pdf)
        try:
            event = QCloseEvent()
            win.closeEvent(event)
            assert event.isAccepted() is True
            assert answer_discard_prompt.calls == []
        finally:
            _force_close(win)


class TestViewerLifetime:
    def test_closed_tab_viewer_is_deleted(self, qapp, sample_pdf, second_sample_pdf):
        """QTabWidget.removeTab only unparents the widget; without an explicit
        delete the viewer stays alive holding a QPixmap for every page."""
        win = MainWindow()
        win.show()
        win._open_file_by_path(sample_pdf)
        win._open_file_by_path(second_sample_pdf)
        qapp.processEvents()

        viewer = win._tab_states[0].viewer
        win._on_tab_close_requested(0)
        # deleteLater posts a DeferredDelete event; processEvents alone does
        # not drain those, so ask for them explicitly.
        qapp.processEvents()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)

        try:
            with pytest.raises(RuntimeError):
                viewer.objectName()
        finally:
            _force_close(win)

    def test_closing_a_tab_closes_its_document(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        doc = win._current_state.doc
        win._on_tab_close_requested(0)
        assert doc.is_closed is True
        win.close()


@pytest.fixture()
def failing_save(monkeypatch):
    """Force the incremental save AND the atomic replace to fail."""
    errors = []
    monkeypatch.setattr(
        fitz.Document,
        "saveIncr",
        lambda self: (_ for _ in ()).throw(RuntimeError("cannot save incrementally")),
    )
    monkeypatch.setattr(
        os, "replace", lambda *a: (_ for _ in ()).throw(OSError("Permission denied"))
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(
            lambda parent, title, text, *a, **k: errors.append(text)
            or QMessageBox.StandardButton.Ok
        ),
    )
    return errors


class TestQuickSaveRecovery:
    def test_failed_replace_leaves_a_usable_document(
        self, qapp, tmp_path, accept_preview, failing_save
    ):
        """The fallback path closed the doc before os.replace. If replace
        raised, the tab was left pointing at a closed document."""
        path = tmp_path / "locked.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "SECRET here")
        doc.save(str(path))
        doc.close()

        win = _open(qapp, str(path))
        try:
            win._do_search("SECRET")
            win._redact_all()

            win._quick_save()
            qapp.processEvents()

            state = win._current_state
            assert state.doc.is_closed is False
            # The tab must still be usable.
            assert len(state.doc) == 1
            win._do_search("here")
        finally:
            _force_close(win)

    def test_failed_save_keeps_the_redactions_in_memory(
        self, qapp, tmp_path, accept_preview, failing_save
    ):
        """A failed save must not silently revert applied redactions.

        Reopening the document from the untouched original threw the user's
        work away while still advertising it as unsaved.
        """
        path = tmp_path / "keepwork.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "TOPSECRET payload")
        doc.save(str(path))
        doc.close()

        win = _open(qapp, str(path))
        try:
            win._do_search("TOPSECRET")
            win._redact_all()
            assert "TOPSECRET" not in win._doc[0].get_text("text")

            win._quick_save()
            qapp.processEvents()

            state = win._current_state
            assert state.is_dirty is True, "failed save must stay dirty"
            assert "TOPSECRET" not in state.doc[0].get_text("text"), (
                "the redaction was reverted by a failed save"
            )
        finally:
            _force_close(win)

    def test_retrying_after_a_failed_save_writes_the_redacted_file(
        self, qapp, tmp_path, accept_preview, monkeypatch
    ):
        """The dangerous sequence: redact, save fails, save again succeeds.

        If the failure reverted the in-memory document, the retry would
        cheerfully write the *unredacted* file over the original.
        """
        path = tmp_path / "retry.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "TOPSECRET payload")
        doc.save(str(path))
        doc.close()

        win = _open(qapp, str(path))
        try:
            win._do_search("TOPSECRET")
            win._redact_all()

            monkeypatch.setattr(
                fitz.Document,
                "saveIncr",
                lambda self: (_ for _ in ()).throw(RuntimeError("no incr")),
            )
            monkeypatch.setattr(
                QMessageBox,
                "critical",
                staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
            )
            real_replace = os.replace
            monkeypatch.setattr(
                os, "replace", lambda *a: (_ for _ in ()).throw(OSError("locked"))
            )

            win._quick_save()  # fails
            qapp.processEvents()

            monkeypatch.setattr(os, "replace", real_replace)
            win._quick_save()  # retry, now succeeds
            qapp.processEvents()

            assert win._current_state.is_dirty is False
            reopened = fitz.open(str(path))
            text = reopened[0].get_text("text")
            reopened.close()
            assert "TOPSECRET" not in text, "retry wrote the unredacted document"
        finally:
            _force_close(win)

    def test_failed_save_tells_the_user_what_to_do(
        self, qapp, tmp_path, accept_preview, failing_save
    ):
        path = tmp_path / "advice.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "SECRET here")
        doc.save(str(path))
        doc.close()

        win = _open(qapp, str(path))
        try:
            win._do_search("SECRET")
            win._redact_all()
            win._quick_save()
            qapp.processEvents()

            assert failing_save, "no error was reported to the user"
            assert "Save As" in failing_save[-1]
        finally:
            _force_close(win)

    def test_failed_replace_leaves_no_temp_file(
        self, qapp, tmp_path, accept_preview, failing_save
    ):
        path = tmp_path / "tmpcheck.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "SECRET here")
        doc.save(str(path))
        doc.close()

        win = _open(qapp, str(path))
        try:
            win._do_search("SECRET")
            win._redact_all()

            win._quick_save()
            qapp.processEvents()

            leftovers = [p.name for p in tmp_path.iterdir() if p.suffix == ".pdf"]
            assert leftovers == ["tmpcheck.pdf"], f"temp file left behind: {leftovers}"
        finally:
            _force_close(win)
