"""E2E tests for the batch dialog workflow."""

import os

import fitz
from PySide6.QtWidgets import QApplication, QMessageBox


class TestBatchSearchAndRedact:
    def test_batch_search_then_redact(self, qapp, batch_tree, tmp_path, monkeypatch):
        from app.batch_dialog import BatchDialog, _BatchWorker, _SearchWorker

        dialog = BatchDialog()
        dialog._input_edit.setText(str(batch_tree))
        output = str(tmp_path / "output")
        dialog._output_edit.setText(output)
        dialog._keyword_edit.setText("SECRET_DATA_123")

        # Make workers run synchronously: call run() then processEvents
        # to ensure queued signal connections are delivered.
        def sync_start_search(self):
            self.run()
            QApplication.processEvents()

        def sync_start_batch(self):
            self.run()
            QApplication.processEvents()

        monkeypatch.setattr(_SearchWorker, "start", sync_start_search)
        monkeypatch.setattr(_BatchWorker, "start", sync_start_batch)
        # Monkeypatch the QMessageBox that pops up at the end of redaction
        monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Ok)

        # Step 1: Search
        dialog._search()
        QApplication.processEvents()
        # Dialog is not shown, so isVisible() inherits parent visibility.
        # Use isHidden() to check the widget's own flag.
        assert not dialog._redact_btn.isHidden()

        # Step 2: Redact
        dialog._redact()
        QApplication.processEvents()

        # Verify output files exist and are redacted
        for name in ["a.pdf", os.path.join("sub", "b.pdf")]:
            path = os.path.join(output, name)
            assert os.path.exists(path), f"Expected output file {path} to exist"
            doc = fitz.open(path)
            assert "SECRET_DATA_123" not in doc[0].get_text()
            doc.close()

        dialog.close()

    def test_search_no_matches(self, qapp, batch_tree, monkeypatch):
        from app.batch_dialog import BatchDialog, _SearchWorker

        dialog = BatchDialog()
        dialog._input_edit.setText(str(batch_tree))
        dialog._output_edit.setText(str(batch_tree) + "_out")
        dialog._keyword_edit.setText("NONEXISTENT_TERM_999")

        def sync_start(self):
            self.run()
            QApplication.processEvents()

        monkeypatch.setattr(_SearchWorker, "start", sync_start)

        dialog._search()
        QApplication.processEvents()
        assert dialog._redact_btn.isHidden()
        dialog.close()

    def test_search_missing_folder_warns(self, qapp, monkeypatch):
        from app.batch_dialog import BatchDialog

        warned = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *args: warned.append(args))

        dialog = BatchDialog()
        dialog._keyword_edit.setText("test")
        dialog._search()
        assert len(warned) == 1
        dialog.close()

    def test_search_missing_keywords_warns(self, qapp, batch_tree, monkeypatch):
        from app.batch_dialog import BatchDialog

        warned = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *args: warned.append(args))

        dialog = BatchDialog()
        dialog._input_edit.setText(str(batch_tree))
        dialog._output_edit.setText(str(batch_tree) + "_out")
        dialog._keyword_edit.setText("")
        dialog._search()
        assert len(warned) == 1
        dialog.close()
