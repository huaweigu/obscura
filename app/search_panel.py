from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SearchResult:
    """Holds data for a single search match."""

    __slots__ = ("page_index", "rect", "snippet")

    def __init__(self, page_index, rect, snippet=""):
        self.page_index = page_index
        self.rect = rect
        self.snippet = snippet


class SearchPanel(QWidget):
    """Search input, results list, and redaction action buttons."""

    search_requested = Signal(str)  # keyword
    result_clicked = Signal(int, object)  # page_index, rect
    redact_all_requested = Signal()
    redact_selected_requested = Signal(list)  # list of SearchResult

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # Section label
        section = QLabel("SEARCH")
        section.setObjectName("section-label")
        layout.addWidget(section)

        # Search input row
        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Enter keyword to search…")
        self._search_input.returnPressed.connect(self._on_search)
        self._search_btn = QPushButton("Search")
        self._search_btn.setObjectName("primary")
        self._search_btn.clicked.connect(self._on_search)
        input_row.addWidget(self._search_input)
        input_row.addWidget(self._search_btn)
        layout.addLayout(input_row)

        # Results count label
        self._count_label = QLabel("")
        self._count_label.setStyleSheet("color: #a0a8b8; font-size: 12px;")
        layout.addWidget(self._count_label)

        # Results list
        self._results_list = QListWidget()
        self._results_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._results_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._results_list)

        # Redact buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._redact_all_btn = QPushButton("Redact All")
        self._redact_all_btn.setObjectName("danger")
        self._redact_all_btn.setEnabled(False)
        self._redact_all_btn.clicked.connect(self._on_redact_all)
        self._redact_selected_btn = QPushButton("Redact Selected")
        self._redact_selected_btn.setObjectName("danger")
        self._redact_selected_btn.setEnabled(False)
        self._redact_selected_btn.clicked.connect(self._on_redact_selected)
        btn_row.addWidget(self._redact_all_btn)
        btn_row.addWidget(self._redact_selected_btn)
        layout.addLayout(btn_row)

        self._results = []  # list of SearchResult

    def set_results(self, results):
        """Populate the results list from a list of SearchResult objects."""
        self._results = results
        self._results_list.clear()
        for r in results:
            text = f"Page {r.page_index + 1}: {r.snippet}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, r)
            self._results_list.addItem(item)
        count = len(results)
        self._count_label.setText(f"{count} match{'es' if count != 1 else ''} found")
        self._redact_all_btn.setEnabled(count > 0)
        self._redact_selected_btn.setEnabled(count > 0)

    def focus_input(self):
        """Put the keyboard cursor in the search box and select what's there."""
        self._search_input.setFocus()
        self._search_input.selectAll()

    def clear_results(self):
        self._results.clear()
        self._results_list.clear()
        self._count_label.setText("")
        self._redact_all_btn.setEnabled(False)
        self._redact_selected_btn.setEnabled(False)

    def _on_search(self):
        keyword = self._search_input.text().strip()
        if keyword:
            self.search_requested.emit(keyword)

    def _on_item_clicked(self, item):
        result = item.data(Qt.ItemDataRole.UserRole)
        if result:
            self.result_clicked.emit(result.page_index, result.rect)

    def _on_redact_all(self):
        self.redact_all_requested.emit()

    def _on_redact_selected(self):
        selected = []
        for item in self._results_list.selectedItems():
            result = item.data(Qt.ItemDataRole.UserRole)
            if result:
                selected.append(result)
        if selected:
            self.redact_selected_requested.emit(selected)
