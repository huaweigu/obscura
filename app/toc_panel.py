from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget


class TocPanel(QWidget):
    """Displays PDF bookmarks/outline as a tree. Click to navigate."""

    page_requested = Signal(int)  # 0-based page index

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QLabel("BOOKMARKS")
        header.setObjectName("section-label")
        layout.addWidget(header)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree)

    def load_toc(self, doc):
        """Populate tree from doc.get_toc(). Returns True if TOC exists."""
        self._tree.clear()
        if not doc:
            return False
        toc = doc.get_toc()
        if not toc:
            return False

        stack = []  # [(level, QTreeWidgetItem)]
        for level, title, page_num in toc:
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, max(page_num - 1, 0))

            if level == 1 or not stack:
                self._tree.addTopLevelItem(item)
                stack = [(level, item)]
            else:
                while len(stack) > 1 and stack[-1][0] >= level:
                    stack.pop()
                parent_item = stack[-1][1]
                parent_item.addChild(item)
                stack.append((level, item))

        self._tree.expandAll()
        return True

    def _on_item_clicked(self, item, column):
        page_index = item.data(0, Qt.ItemDataRole.UserRole)
        if page_index is not None:
            self.page_requested.emit(page_index)
