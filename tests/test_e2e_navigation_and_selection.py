"""E2E tests for navigation and text selection.

These flows had no coverage at all: dragging to select text and copying it,
clicking a thumbnail or a bookmark to navigate, opening files by drag and
drop, and the page navigation controls. They are driven through the real
event handlers rather than by poking private state, so the mouse and drop
handling is genuinely exercised.
"""

import fitz
import pytest
from PySide6.QtCore import QEvent, QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def _settle(qapp, n=10):
    for _ in range(n):
        qapp.processEvents()


def _open(qapp, path, width=1200, height=800):
    win = MainWindow()
    win.resize(width, height)
    win.show()
    win._open_file_by_path(path)
    _settle(qapp)
    return win


def _close(win):
    for state in win._tab_states:
        if state.doc and not state.doc.is_closed:
            state.doc.close()
        state.is_dirty = False
    win._tab_states.clear()
    win.close()


def _mouse(kind, x, y):
    return QMouseEvent(
        kind,
        QPointF(x, y),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _drag_select(label, x0, y0, x1, y1):
    """Drive a real press/move/release selection on a page label."""
    label.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, x0, y0))
    label.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, x1, y1))
    label.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, x1, y1))


@pytest.fixture()
def selectable_pdf(tmp_path):
    """A page whose text sits at a known position, for selection tests."""
    path = tmp_path / "selectable.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "SELECTABLE_PHRASE_ONE", fontsize=14)
    page.insert_text((72, 400), "UNRELATED_TEXT_BELOW", fontsize=14)
    doc.save(str(path))
    doc.close()
    return str(path)


class TestTextSelectionAndCopy:
    def test_drag_selects_text_on_the_page(self, qapp, selectable_pdf):
        win = _open(qapp, selectable_pdf)
        try:
            win._switch_mode("reader")  # selection is a Read-mode affordance
            _settle(qapp)

            label = win._viewer._page_labels[0]
            scale = win._viewer.zoom
            # Cover the first line, in widget coordinates.
            _drag_select(label, 60 * scale, 80 * scale, 320 * scale, 115 * scale)

            assert label._selection_rect is not None
            assert not label._selection_rect.isNull()

            text = label.get_selected_text(win._doc)
            assert "SELECTABLE_PHRASE_ONE" in text
            assert "UNRELATED_TEXT_BELOW" not in text
        finally:
            _close(win)

    def test_copy_puts_the_selection_on_the_clipboard(self, qapp, selectable_pdf):
        win = _open(qapp, selectable_pdf)
        try:
            win._switch_mode("reader")
            _settle(qapp)
            QApplication.clipboard().clear()

            label = win._viewer._page_labels[0]
            scale = win._viewer.zoom
            _drag_select(label, 60 * scale, 80 * scale, 320 * scale, 115 * scale)

            win._copy_text()
            _settle(qapp)

            assert "SELECTABLE_PHRASE_ONE" in QApplication.clipboard().text()
        finally:
            _close(win)

    def test_selection_is_disabled_outside_read_mode(self, qapp, selectable_pdf):
        win = _open(qapp, selectable_pdf)
        try:
            win._switch_mode("redactor")
            _settle(qapp)

            label = win._viewer._page_labels[0]
            scale = win._viewer.zoom
            _drag_select(label, 60 * scale, 80 * scale, 320 * scale, 115 * scale)

            assert label._selection_rect is None
            assert label.get_selected_text(win._doc) == ""
        finally:
            _close(win)

    def test_switching_mode_clears_an_existing_selection(
        self, qapp, selectable_pdf
    ):
        win = _open(qapp, selectable_pdf)
        try:
            win._switch_mode("reader")
            _settle(qapp)
            label = win._viewer._page_labels[0]
            scale = win._viewer.zoom
            _drag_select(label, 60 * scale, 80 * scale, 320 * scale, 115 * scale)
            assert label._selection_rect is not None

            win._switch_mode("redactor")
            _settle(qapp)
            assert win._viewer._page_labels[0]._selection_rect is None
        finally:
            _close(win)

    def test_copy_with_no_selection_is_harmless(self, qapp, selectable_pdf):
        win = _open(qapp, selectable_pdf)
        try:
            QApplication.clipboard().setText("untouched")
            win._copy_text()
            assert QApplication.clipboard().text() == "untouched"
        finally:
            _close(win)


class TestThumbnailNavigation:
    def test_clicking_a_thumbnail_scrolls_to_that_page(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            win._toggle_panel()  # thumbnails live in the side panel
            _settle(qapp)
            assert win._viewer.current_page() == 1

            thumb = win._thumb_panel._thumbnails[2]  # third page
            thumb.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, 5, 5))
            _settle(qapp)

            assert win._viewer.current_page() == 3
        finally:
            _close(win)

    def test_scrolling_highlights_the_matching_thumbnail(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            win._toggle_panel()
            _settle(qapp)

            win._goto_page(2)
            _settle(qapp)

            assert win._thumb_panel._current_page == 1  # 0-based
            assert win._thumb_panel._thumbnails[1]._selected is True
            assert win._thumb_panel._thumbnails[0]._selected is False
        finally:
            _close(win)

    def test_thumbnail_count_matches_the_document(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            win._toggle_panel()
            _settle(qapp)
            assert len(win._thumb_panel._thumbnails) == len(win._doc)
        finally:
            _close(win)


class TestBookmarkNavigation:
    def test_clicking_a_bookmark_scrolls_to_its_page(
        self, qapp, sample_pdf_with_toc
    ):
        win = _open(qapp, sample_pdf_with_toc)
        try:
            win._toggle_panel()
            _settle(qapp)
            assert win._has_toc is True

            tree = win._toc_panel._tree
            chapter_four = tree.topLevelItem(3)
            assert chapter_four.text(0) == "Chapter 4"

            win._toc_panel._on_item_clicked(chapter_four, 0)
            _settle(qapp)

            assert win._viewer.current_page() == 4
        finally:
            _close(win)

    def test_bookmarks_are_listed_for_a_document_with_an_outline(
        self, qapp, sample_pdf_with_toc
    ):
        win = _open(qapp, sample_pdf_with_toc)
        try:
            assert win._toc_panel._tree.topLevelItemCount() == 5
        finally:
            _close(win)


class TestDragAndDropOpen:
    def _drop(self, win, paths):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        enter = QDragEnterEvent(
            QPointF(10, 10).toPoint(),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        win.dragEnterEvent(enter)
        drop = QDropEvent(
            QPointF(10, 10),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        win.dropEvent(drop)
        return enter

    def test_dropping_a_file_opens_it(self, qapp, sample_pdf):
        win = MainWindow()
        win.show()
        try:
            assert win._tab_widget.count() == 0
            enter = self._drop(win, [sample_pdf])
            _settle(qapp)

            assert enter.isAccepted()
            assert win._tab_widget.count() == 1
            assert win._current_state.file_path == sample_pdf
            assert win._stack.currentIndex() == 1  # welcome screen replaced
        finally:
            _close(win)

    def test_dropping_two_files_opens_both(
        self, qapp, sample_pdf, second_sample_pdf
    ):
        win = MainWindow()
        win.show()
        try:
            self._drop(win, [sample_pdf, second_sample_pdf])
            _settle(qapp)
            assert win._tab_widget.count() == 2
        finally:
            _close(win)

    def test_dropping_an_already_open_file_reuses_its_tab(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            self._drop(win, [sample_pdf])
            _settle(qapp)
            assert win._tab_widget.count() == 1
        finally:
            _close(win)


class TestPageNavigationControls:
    def test_next_and_previous_move_one_page(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            assert win._viewer.current_page() == 1

            win._next_page()
            _settle(qapp)
            assert win._viewer.current_page() == 2

            win._prev_page()
            _settle(qapp)
            assert win._viewer.current_page() == 1
        finally:
            _close(win)

    def test_home_and_end_jump_to_first_and_last(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            win._last_page()
            _settle(qapp)
            assert win._viewer.current_page() == 3

            win._first_page()
            _settle(qapp)
            assert win._viewer.current_page() == 1
        finally:
            _close(win)

    def test_navigation_stops_at_the_ends(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            win._prev_page()  # already on page 1
            _settle(qapp)
            assert win._viewer.current_page() == 1

            win._last_page()
            _settle(qapp)
            win._next_page()  # already on the last page
            _settle(qapp)
            assert win._viewer.current_page() == 3
        finally:
            _close(win)

    def test_page_indicator_and_status_bar_follow_navigation(
        self, qapp, sample_pdf
    ):
        win = _open(qapp, sample_pdf)
        try:
            win._goto_page(2)
            _settle(qapp)
            assert win._page_label.text() == "2 / 3"
            assert "Page 2 / 3" in win.statusBar().currentMessage()
        finally:
            _close(win)

    def test_goto_page_ignores_out_of_range_values(self, qapp, sample_pdf):
        win = _open(qapp, sample_pdf)
        try:
            win._goto_page(99)
            _settle(qapp)
            assert win._viewer.current_page() == 1

            win._goto_page(0)
            _settle(qapp)
            assert win._viewer.current_page() == 1
        finally:
            _close(win)
