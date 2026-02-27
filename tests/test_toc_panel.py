import fitz
import pytest

from app.toc_panel import TocPanel


class TestTocPanel:
    def test_load_toc_with_bookmarks(self, qapp):
        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        doc.new_page()
        doc.set_toc([
            [1, "Chapter 1", 1],
            [2, "Section 1.1", 1],
            [2, "Section 1.2", 2],
            [1, "Chapter 2", 3],
        ])

        panel = TocPanel()
        has_toc = panel.load_toc(doc)
        assert has_toc is True
        assert panel._tree.topLevelItemCount() == 2  # 2 chapters

        ch1 = panel._tree.topLevelItem(0)
        assert ch1.text(0) == "Chapter 1"
        assert ch1.childCount() == 2  # 2 sections

        ch2 = panel._tree.topLevelItem(1)
        assert ch2.text(0) == "Chapter 2"

    def test_load_toc_empty(self, qapp):
        doc = fitz.open()
        doc.new_page()

        panel = TocPanel()
        has_toc = panel.load_toc(doc)
        assert has_toc is False
        assert panel._tree.topLevelItemCount() == 0

    def test_load_toc_none_doc(self, qapp):
        panel = TocPanel()
        has_toc = panel.load_toc(None)
        assert has_toc is False

    def test_page_index_stored_correctly(self, qapp):
        from PySide6.QtCore import Qt

        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        doc.set_toc([[1, "Intro", 2]])

        panel = TocPanel()
        panel.load_toc(doc)

        item = panel._tree.topLevelItem(0)
        page_index = item.data(0, Qt.ItemDataRole.UserRole)
        assert page_index == 1  # page 2 → 0-based index 1
