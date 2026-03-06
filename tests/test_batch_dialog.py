from PySide6.QtWidgets import QFrame, QLabel

from app.batch_dialog import BatchDialog


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
