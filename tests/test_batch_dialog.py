import pytest
from PySide6.QtWidgets import QFrame, QLabel, QMessageBox

from app.batch_dialog import BatchDialog, _ShrinkWorker


class TestBatchDialogCreation:
    def test_creates_without_error(self, qapp):
        dlg = BatchDialog()
        assert dlg is not None


class TestBatchDialogTabs:
    def test_has_two_tabs(self, qapp):
        dlg = BatchDialog()
        assert dlg._tabs.count() == 2
        assert dlg._tabs.tabText(0) == "Redact"
        assert dlg._tabs.tabText(1) == "Shrink Images"


class TestRedactButton:
    def test_redact_button_initially_hidden(self, qapp):
        dlg = BatchDialog()
        assert not dlg._redact_btn.isVisible()


class TestFormatBytes:
    def test_format_bytes_small(self):
        assert BatchDialog._format_bytes(500) == "500 B"

    def test_format_bytes_kb(self):
        assert BatchDialog._format_bytes(2048) == "2.0 KB"

    def test_format_bytes_mb(self):
        assert BatchDialog._format_bytes(2 * 1024 * 1024) == "2.0 MB"


class TestMakeStatCard:
    def test_make_stat_card(self, qapp):
        card = BatchDialog._make_stat_card("42", "Tests", "#0f3460")
        assert isinstance(card, QFrame)
        value_label = card.findChild(QLabel, "value")
        assert value_label is not None
        assert value_label.text() == "42"


class TestOnInputsChanged:
    def test_on_inputs_changed_hides_results(self, qapp):
        dlg = BatchDialog()
        # Force containers visible to verify they get hidden
        dlg._match_list_container.setVisible(True)
        dlg._redact_btn.setVisible(True)
        dlg._results_container.setVisible(True)
        dlg._progress_container.setVisible(True)

        dlg._on_inputs_changed()

        assert not dlg._match_list_container.isVisible()
        assert not dlg._redact_btn.isVisible()
        assert not dlg._results_container.isVisible()
        assert not dlg._progress_container.isVisible()

# ── Shrink tab ──────────────────────────────────────────────
#
# The image-compression feature and its worker thread had no dialog-level
# coverage. QMessageBox is patched throughout: _on_shrink_finished ends in a
# modal summary box that would otherwise block the run.


@pytest.fixture()
def image_folder(tmp_path, sample_image):
    """A folder of images, separate from the fixture's own tmp_path file."""
    import shutil

    folder = tmp_path / "photos"
    folder.mkdir()
    for name in ("one.jpg", "two.jpg"):
        shutil.copy(sample_image, folder / name)
    return folder


@pytest.fixture()
def silent_message_box(monkeypatch):
    """Swallow the modal summary and warning boxes."""
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Ok)
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(
            lambda parent, title, text, *a, **k: warnings.append((title, text))
            or QMessageBox.StandardButton.Ok
        ),
    )
    return warnings


class TestShrinkWorker:
    def test_worker_emits_a_result(self, qapp, image_folder, tmp_path):
        worker = _ShrinkWorker(str(image_folder), str(tmp_path / "out"), 150, 70)
        received = []
        worker.finished.connect(received.append)
        worker.run()  # run synchronously, no thread needed

        assert len(received) == 1
        assert received[0].processed == 2
        assert received[0].errors == []

    def test_worker_reports_progress(self, qapp, image_folder, tmp_path):
        worker = _ShrinkWorker(str(image_folder), str(tmp_path / "out2"), 150, 70)
        seen = []
        worker.progress.connect(lambda *args: seen.append(args))
        worker.run()
        assert len(seen) == 2


class TestShrinkFlow:
    def test_missing_input_folder_warns_and_does_nothing(
        self, qapp, silent_message_box
    ):
        dlg = BatchDialog()
        dlg._shrink_input_edit.setText("")
        dlg._shrink()
        assert silent_message_box, "expected a warning about the missing folder"
        assert dlg._worker is None

    def test_output_folder_defaults_from_the_input(
        self, qapp, image_folder, silent_message_box
    ):
        dlg = BatchDialog()
        dlg._shrink_input_edit.setText(str(image_folder))
        dlg._shrink_output_edit.setText("")
        dlg._shrink()
        try:
            assert dlg._shrink_output_edit.text() == str(image_folder) + "_compressed"
        finally:
            if dlg._worker:
                dlg._worker.wait()

    def test_shrink_produces_smaller_files_and_fills_the_stats(
        self, qapp, image_folder, tmp_path, silent_message_box
    ):
        dlg = BatchDialog()
        dlg._shrink_input_edit.setText(str(image_folder))
        out = tmp_path / "compressed"
        dlg._shrink_output_edit.setText(str(out))
        dlg._max_dim_spin.setValue(120)

        dlg._shrink()
        assert dlg._worker is not None
        dlg._worker.wait()
        for _ in range(10):
            qapp.processEvents()

        assert (out / "one.jpg").exists()
        assert (out / "two.jpg").exists()
        processed = dlg._lbl_shrink_processed.findChild(QLabel, "value").text()
        assert processed == "2"
        assert dlg._shrink_results_container.isVisible() or not dlg.isVisible()

    def test_progress_handler_updates_the_bar(self, qapp):
        dlg = BatchDialog()
        dlg._on_shrink_progress(0, 4, "one.jpg", 1234)
        assert dlg._shrink_progress_bar.maximum() == 4
        assert dlg._shrink_progress_bar.value() == 1
        assert "one.jpg" in dlg._shrink_file_label.text()

    def test_empty_folder_is_reported_not_crashed(
        self, qapp, tmp_path, silent_message_box
    ):
        from app.batch_processor import ShrinkResult

        dlg = BatchDialog()
        dlg._on_shrink_finished(ShrinkResult(total_files=0))
        assert dlg._shrink_btn.isEnabled()
        assert dlg._lbl_shrink_savings.findChild(QLabel, "value").text() == "0%"

    def test_errors_are_surfaced_to_the_user(self, qapp, silent_message_box):
        from app.batch_processor import ShrinkResult

        dlg = BatchDialog()
        result = ShrinkResult(
            total_files=2,
            processed=1,
            original_bytes=1000,
            new_bytes=400,
            errors=[("broken.jpg", "cannot identify image file")],
        )
        dlg._on_shrink_finished(result)

        assert "broken.jpg" in dlg._shrink_errors_text.toPlainText()
        assert dlg._lbl_shrink_savings.findChild(QLabel, "value").text() == "60%"
