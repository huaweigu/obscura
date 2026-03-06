import fitz
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget

from app.search_panel import SearchPanel, SearchResult


def _make_results(n):
    """Return a list of n SearchResult objects with distinct pages and rects."""
    results = []
    for i in range(n):
        rect = fitz.Rect(10 + i, 20 + i, 100 + i, 40 + i)
        results.append(SearchResult(page_index=i, rect=rect, snippet=f"match {i}"))
    return results


class TestSearchPanelCreation:
    def test_creates_without_error(self, qapp):
        panel = SearchPanel()
        assert panel is not None


class TestSearchSignals:
    def test_search_signal_on_button_click(self, qapp):
        panel = SearchPanel()
        received = []
        panel.search_requested.connect(lambda text: received.append(text))

        panel._search_input.setText("hello")
        panel._search_btn.click()

        assert received == ["hello"]

    def test_search_signal_on_enter(self, qapp):
        panel = SearchPanel()
        received = []
        panel.search_requested.connect(lambda text: received.append(text))

        panel._search_input.setText("world")
        panel._search_input.returnPressed.emit()

        assert received == ["world"]

    def test_empty_input_no_signal(self, qapp):
        panel = SearchPanel()
        received = []
        panel.search_requested.connect(lambda text: received.append(text))

        panel._search_input.setText("")
        panel._search_btn.click()

        assert received == []


class TestSetResults:
    def test_set_results_populates_list(self, qapp):
        panel = SearchPanel()
        results = _make_results(3)
        panel.set_results(results)

        assert panel._results_list.count() == 3
        # Verify first item text contains page number and snippet
        first_text = panel._results_list.item(0).text()
        assert "Page 1" in first_text
        assert "match 0" in first_text

    def test_set_results_enables_buttons(self, qapp):
        panel = SearchPanel()
        assert not panel._redact_all_btn.isEnabled()
        assert not panel._redact_selected_btn.isEnabled()

        panel.set_results(_make_results(2))

        assert panel._redact_all_btn.isEnabled()
        assert panel._redact_selected_btn.isEnabled()

    def test_count_label_plural_and_singular(self, qapp):
        panel = SearchPanel()

        panel.set_results(_make_results(5))
        assert panel._count_label.text() == "5 matches found"

        panel.set_results(_make_results(1))
        assert panel._count_label.text() == "1 match found"


class TestClearResults:
    def test_clear_results_disables_buttons(self, qapp):
        panel = SearchPanel()
        panel.set_results(_make_results(3))
        assert panel._redact_all_btn.isEnabled()

        panel.clear_results()

        assert panel._results_list.count() == 0
        assert panel._count_label.text() == ""
        assert not panel._redact_all_btn.isEnabled()
        assert not panel._redact_selected_btn.isEnabled()


class TestRedactSignals:
    def test_redact_all_signal(self, qapp):
        panel = SearchPanel()
        panel.set_results(_make_results(2))

        received = []
        panel.redact_all_requested.connect(lambda: received.append(True))
        panel._redact_all_btn.click()

        assert received == [True]

    def test_redact_selected_signal(self, qapp):
        panel = SearchPanel()
        results = _make_results(3)
        panel.set_results(results)

        received = []
        panel.redact_selected_requested.connect(lambda items: received.append(items))

        # Select the first and third items
        panel._results_list.item(0).setSelected(True)
        panel._results_list.item(2).setSelected(True)
        panel._redact_selected_btn.click()

        assert len(received) == 1
        selected = received[0]
        assert len(selected) == 2
        assert selected[0].page_index == 0
        assert selected[1].page_index == 2
