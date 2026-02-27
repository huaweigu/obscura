from __future__ import annotations

from dataclasses import dataclass, field

import fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QStyle,
    QTabWidget,
)

from app.batch_dialog import BatchDialog
from app.pdf_viewer import PdfViewer
from app.preview_dialog import PreviewDialog
from app.redactor import apply_redactions, mark_for_redaction, save
from app.search_panel import SearchPanel, SearchResult
from app.thumbnail_panel import ThumbnailPanel
from app.toc_panel import TocPanel


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif")


@dataclass
class DocumentState:
    """Per-document state for a single open tab."""

    viewer: PdfViewer
    doc: fitz.Document | None = None
    file_path: str | None = None
    search_results: list = field(default_factory=list)
    ocr_textpages: dict = field(default_factory=dict)
    is_image_source: bool = False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Obscura")
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        self._tab_states: list[DocumentState] = []
        self._connected_viewer: PdfViewer | None = None
        self._mode = "reader"

        self._setup_viewer()
        self._setup_thumbnail_panel()
        self._setup_toc_panel()
        self._setup_search_panel()
        self._setup_toolbar()
        self._setup_statusbar()
        self._setup_shortcuts()

    # ── Properties (delegate to active tab) ───────────────────

    @property
    def _current_state(self) -> DocumentState | None:
        idx = self._tab_widget.currentIndex()
        if 0 <= idx < len(self._tab_states):
            return self._tab_states[idx]
        return None

    @property
    def _viewer(self) -> PdfViewer | None:
        state = self._current_state
        return state.viewer if state else None

    @property
    def _doc(self):
        state = self._current_state
        return state.doc if state else None

    # ── UI Setup ──────────────────────────────────────────────

    def _setup_viewer(self):
        self._tab_widget = QTabWidget()
        self._tab_widget.setTabsClosable(True)
        self._tab_widget.setMovable(True)
        self._tab_widget.setDocumentMode(True)
        self.setCentralWidget(self._tab_widget)
        self._tab_widget.currentChanged.connect(self._on_tab_changed)
        self._tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)

    def _setup_thumbnail_panel(self):
        self._thumb_panel = ThumbnailPanel()
        self._thumb_dock = QDockWidget("Pages", self)
        self._thumb_dock.setWidget(self._thumb_panel)
        self._thumb_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._thumb_dock)
        self._thumb_dock.setVisible(False)
        self._thumb_panel.page_clicked.connect(self._on_thumbnail_clicked)

    def _setup_toc_panel(self):
        self._toc_panel = TocPanel()
        self._toc_dock = QDockWidget("Bookmarks", self)
        self._toc_dock.setWidget(self._toc_panel)
        self._toc_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._toc_dock)
        self._toc_dock.setVisible(False)
        self._toc_panel.page_requested.connect(self._on_thumbnail_clicked)

    def _setup_search_panel(self):
        self._search_panel = SearchPanel()
        self._search_dock = QDockWidget("Search && Redact", self)
        self._search_dock.setWidget(self._search_panel)
        self._search_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._search_dock)

        # Tab the left docks together
        self.tabifyDockWidget(self._thumb_dock, self._toc_dock)
        self.tabifyDockWidget(self._toc_dock, self._search_dock)
        self._search_dock.raise_()  # default visible tab

        # Set a comfortable default width for the left dock area
        self.resizeDocks(
            [self._thumb_dock, self._toc_dock, self._search_dock],
            [260, 260, 260],
            Qt.Orientation.Horizontal,
        )

        self._search_panel.search_requested.connect(self._do_search)
        self._search_panel.result_clicked.connect(self._on_result_clicked)
        self._search_panel.redact_all_requested.connect(self._redact_all)
        self._search_panel.redact_selected_requested.connect(self._redact_selected)

    def _setup_toolbar(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)

        style = self.style()

        open_act = QAction("Open", self)
        open_act.setToolTip("Open File")
        open_act.setShortcut(QKeySequence.StandardKey.Open)
        open_act.triggered.connect(self._open_file)
        tb.addAction(open_act)

        save_act = QAction("Save", self)
        save_act.setToolTip("Save As")
        save_act.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_act.triggered.connect(self._save_file)
        tb.addAction(save_act)

        batch_act = QAction("Batch", self)
        batch_act.setToolTip("Batch Redact")
        batch_act.triggered.connect(self._open_batch_dialog)
        tb.addAction(batch_act)

        tb.addSeparator()

        zoom_out_act = QAction("\u2212", self)  # minus sign
        zoom_out_act.setToolTip("Zoom Out")
        zoom_out_act.setShortcut(QKeySequence.StandardKey.ZoomOut)
        zoom_out_act.triggered.connect(self._zoom_out)
        tb.addAction(zoom_out_act)

        self._zoom_input = QLineEdit("---")
        self._zoom_input.setFixedWidth(56)
        self._zoom_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_input.setStyleSheet(
            "background: transparent; border: 1px solid transparent;"
            "border-radius: 4px; color: #a0a8b8; font-size: 12px;"
            "font-weight: bold; padding: 2px 4px;"
        )
        self._zoom_input.returnPressed.connect(self._on_zoom_input)
        tb.addWidget(self._zoom_input)

        zoom_in_act = QAction("+", self)
        zoom_in_act.setToolTip("Zoom In")
        zoom_in_act.setShortcut(QKeySequence.StandardKey.ZoomIn)
        zoom_in_act.triggered.connect(self._zoom_in)
        tb.addAction(zoom_in_act)

        fit_width_act = QAction("\u2194", self)  # left-right arrow
        fit_width_act.setToolTip("Fit Width")
        fit_width_act.triggered.connect(self._fit_width)
        tb.addAction(fit_width_act)

        fit_page_act = QAction("\u2922", self)  # NE arrow to corner
        fit_page_act.setToolTip("Fit Page")
        fit_page_act.triggered.connect(self._fit_page)
        tb.addAction(fit_page_act)

        tb.addSeparator()

        # Page navigation
        prev_act = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack), "", self
        )
        prev_act.setToolTip("Previous Page")
        prev_act.triggered.connect(self._prev_page)
        tb.addAction(prev_act)

        self._page_label = QLabel("0 / 0")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setFixedWidth(80)
        self._page_label.setStyleSheet(
            "background: #0f3460; color: #e0e0e0; font-size: 13px;"
            "font-weight: bold; border-radius: 10px; padding: 4px 10px;"
        )
        tb.addWidget(self._page_label)

        next_act = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_ArrowForward), "", self
        )
        next_act.setToolTip("Next Page")
        next_act.triggered.connect(self._next_page)
        tb.addAction(next_act)

        tb.addSeparator()

        # Mode toggle
        self._mode_action = QAction("Redactor Mode", self)
        self._mode_action.setToolTip("Toggle Reader / Redactor Mode")
        self._mode_action.setCheckable(True)
        self._mode_action.setShortcut(QKeySequence("Ctrl+M"))
        self._mode_action.toggled.connect(self._toggle_mode)
        self._mode_action.setChecked(True)  # must be after connect so _toggle_mode fires
        tb.addAction(self._mode_action)

    def _setup_statusbar(self):
        self._status_file = ""
        self._status_page = ""
        self.statusBar().showMessage("No file loaded")

    def _setup_shortcuts(self):
        # Copy text selection
        copy_act = QAction("Copy", self)
        copy_act.setShortcut(QKeySequence.StandardKey.Copy)
        copy_act.triggered.connect(self._copy_text)
        self.addAction(copy_act)

        # Page navigation shortcuts
        QShortcut(QKeySequence.StandardKey.MoveToPreviousPage, self, self._prev_page)
        QShortcut(QKeySequence.StandardKey.MoveToNextPage, self, self._next_page)
        QShortcut(QKeySequence("Home"), self, self._first_page)
        QShortcut(QKeySequence("End"), self, self._last_page)

    def _update_status(self):
        parts = []
        if self._status_file:
            parts.append(self._status_file)
        if self._status_page:
            parts.append(self._status_page)
        self.statusBar().showMessage("  |  ".join(parts) if parts else "No file loaded")

    # ── Tab Management ────────────────────────────────────────

    def _on_tab_changed(self, index):
        """Called when the active tab changes."""
        # Disconnect signals from the old viewer
        if self._connected_viewer is not None:
            try:
                self._connected_viewer.page_changed.disconnect(self._on_page_changed)
                self._connected_viewer.zoom_changed.disconnect(self._on_zoom_changed)
            except RuntimeError:
                pass

        state = self._current_state
        if state is None:
            self._connected_viewer = None
            self._thumb_panel.load_document(None)
            self._toc_panel.load_toc(None)
            self._search_panel.clear_results()
            self._page_label.setText("0 / 0")
            self._zoom_input.setText("---")
            self._status_file = ""
            self._status_page = ""
            self.statusBar().showMessage("No file loaded")
            return

        viewer = state.viewer

        # Connect signals from the new viewer
        viewer.page_changed.connect(self._on_page_changed)
        viewer.zoom_changed.connect(self._on_zoom_changed)
        self._connected_viewer = viewer

        # Update toolbar indicators
        if state.doc:
            total = len(state.doc)
            current_page = viewer.current_page()
            self._page_label.setText(f"{current_page} / {total}")
            self._zoom_input.setText(f"{int(viewer.zoom * 100)}%")
            self._status_file = f"File: {state.file_path.split('/')[-1]}"
            self._status_page = f"Page {current_page} / {total}"
            self._update_status()
        else:
            self._page_label.setText("0 / 0")
            self._zoom_input.setText("---")

        # Reload shared panels
        self._thumb_panel.load_document(state.doc)
        has_toc = self._toc_panel.load_toc(state.doc)
        if self._mode == "reader":
            self._toc_dock.setVisible(has_toc)

        # Restore search results for this tab
        if state.search_results:
            self._search_panel.set_results(state.search_results)
        else:
            self._search_panel.clear_results()

    def _on_tab_close_requested(self, index):
        """Handle tab close button click."""
        if index < 0 or index >= len(self._tab_states):
            return

        state = self._tab_states.pop(index)

        # Disconnect if this was the connected viewer
        if self._connected_viewer is state.viewer:
            try:
                state.viewer.page_changed.disconnect(self._on_page_changed)
                state.viewer.zoom_changed.disconnect(self._on_zoom_changed)
            except RuntimeError:
                pass
            self._connected_viewer = None

        if state.doc:
            state.doc.close()

        self._tab_widget.removeTab(index)

    # ── File Operations ───────────────────────────────────────

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            "",
            "Supported Files (*.pdf *.jpg *.jpeg *.png *.bmp *.tiff *.tif);;"
            "PDF Files (*.pdf);;"
            "Image Files (*.jpg *.jpeg *.png *.bmp *.tiff *.tif)",
        )
        if not path:
            return
        self._open_file_by_path(path)

    def _open_file_by_path(self, path):
        """Open a file in a new tab, or switch to it if already open."""
        # Check if already open
        for i, state in enumerate(self._tab_states):
            if state.file_path == path:
                self._tab_widget.setCurrentIndex(i)
                return

        try:
            is_image = path.lower().endswith(IMAGE_EXTENSIONS)
            if is_image:
                doc = self._image_to_pdf(path)
            else:
                doc = fitz.open(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open file:\n{e}")
            return

        viewer = PdfViewer()
        viewer.set_text_selection_enabled(self._mode == "reader")
        viewer.load_document(doc)

        state = DocumentState(
            viewer=viewer,
            doc=doc,
            file_path=path,
            is_image_source=is_image,
        )
        self._tab_states.append(state)

        filename = path.split("/")[-1]
        tab_index = self._tab_widget.addTab(viewer, filename)
        self._tab_widget.setCurrentIndex(tab_index)

    @staticmethod
    def _image_to_pdf(image_path):
        """Convert an image file into a single-page PDF document in memory."""
        img_doc = fitz.open(image_path)
        pdf_bytes = img_doc.convert_to_pdf()
        img_doc.close()
        return fitz.open("pdf", pdf_bytes)

    def _save_file(self):
        if not self._doc:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Redacted PDF", "", "PDF Files (*.pdf)"
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            save(self._doc, path)
            QMessageBox.information(self, "Saved", f"Redacted PDF saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save PDF:\n{e}")

    def _open_batch_dialog(self):
        dialog = BatchDialog(self)
        dialog.exec()

    # ── Drag and Drop ─────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self._open_file_by_path(path)

    # ── Page Navigation ───────────────────────────────────────

    def _prev_page(self):
        if not self._viewer:
            return
        current = self._viewer.current_page()  # 1-based
        if current > 1:
            self._viewer.scroll_to_page(current - 2)

    def _next_page(self):
        if not self._viewer:
            return
        current = self._viewer.current_page()
        if current < self._viewer.page_count:
            self._viewer.scroll_to_page(current)

    def _first_page(self):
        if not self._viewer:
            return
        if self._viewer.page_count > 0:
            self._viewer.scroll_to_page(0)

    def _last_page(self):
        if not self._viewer:
            return
        if self._viewer.page_count > 0:
            self._viewer.scroll_to_page(self._viewer.page_count - 1)

    def _goto_page(self, page_num):
        if not self._viewer:
            return
        if 1 <= page_num <= self._viewer.page_count:
            self._viewer.scroll_to_page(page_num - 1)

    def _zoom_in(self):
        if self._viewer:
            self._viewer.zoom_in()

    def _zoom_out(self):
        if self._viewer:
            self._viewer.zoom_out()

    def _fit_width(self):
        if not self._doc or not self._viewer:
            return
        page = self._doc[0]
        viewport_width = self._viewer.viewport().width()
        new_zoom = viewport_width / page.rect.width
        self._viewer.set_zoom(new_zoom)

    def _fit_page(self):
        if not self._doc or not self._viewer:
            return
        page = self._doc[0]
        viewport_w = self._viewer.viewport().width()
        viewport_h = self._viewer.viewport().height()
        zoom_w = viewport_w / page.rect.width
        zoom_h = viewport_h / page.rect.height
        self._viewer.set_zoom(min(zoom_w, zoom_h))

    def _on_thumbnail_clicked(self, page_index):
        if self._viewer:
            self._viewer.scroll_to_page(page_index)

    # ── Text Selection ────────────────────────────────────────

    def _copy_text(self):
        if self._viewer:
            self._viewer.copy_selected_text()

    # ── Mode Toggle ───────────────────────────────────────────

    def _toggle_mode(self, reader_mode):
        if reader_mode:
            self._mode = "reader"
            self._mode_action.setText("Redactor Mode")
            self.setWindowTitle("Obscura")
            # Show reader panels
            self._thumb_dock.setVisible(True)
            self._thumb_dock.raise_()
            if self._doc:
                has_toc = self._toc_panel.load_toc(self._doc)
                self._toc_dock.setVisible(has_toc)
            # Hide redactor panels
            self._search_dock.setVisible(False)
            # Enable text selection
            if self._viewer:
                self._viewer.set_text_selection_enabled(True)
        else:
            self._mode = "redactor"
            self._mode_action.setText("Reader Mode")
            self.setWindowTitle("Obscura — Redactor")
            # Hide reader panels
            self._thumb_dock.setVisible(False)
            self._toc_dock.setVisible(False)
            # Show redactor panels
            self._search_dock.setVisible(True)
            self._search_dock.raise_()
            # Disable text selection
            if self._viewer:
                self._viewer.set_text_selection_enabled(False)
                self._viewer.clear_selection()

    # ── Zoom ──────────────────────────────────────────────────

    def _on_zoom_changed(self, zoom):
        self._zoom_input.setText(f"{int(zoom * 100)}%")

    def _on_zoom_input(self):
        """Handle user typing a zoom percentage and pressing Enter."""
        text = self._zoom_input.text().strip().rstrip("%").strip()
        try:
            pct = float(text)
        except ValueError:
            # Restore current value
            if self._viewer:
                self._zoom_input.setText(f"{int(self._viewer.zoom * 100)}%")
            return
        if self._viewer:
            self._viewer.set_zoom(pct / 100.0)
        self._zoom_input.clearFocus()

    # ── Search ────────────────────────────────────────────────

    def _do_search(self, keyword):
        state = self._current_state
        if not state or not state.doc:
            return

        doc = state.doc

        # Run OCR on image-sourced docs if not already cached
        if state.is_image_source and not state.ocr_textpages:
            self.statusBar().showMessage("Running OCR…")
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            for i in range(len(doc)):
                page = doc[i]
                state.ocr_textpages[i] = page.get_textpage_ocr(
                    language="eng", full=True
                )
            self._update_status()

        results = []
        highlights = {}
        for page_index in range(len(doc)):
            page = doc[page_index]
            tp = state.ocr_textpages.get(page_index)
            if tp:
                matches = page.search_for(keyword, textpage=tp)
            else:
                matches = page.search_for(keyword)
            for rect in matches:
                snippet = self._extract_snippet(page, rect, keyword, tp)
                results.append(SearchResult(page_index, rect, snippet))
                highlights.setdefault(page_index, []).append(rect)

        state.search_results = results
        self._search_panel.set_results(results)
        state.viewer.set_highlights(highlights)

    def _extract_snippet(self, page, rect, keyword, textpage=None, context_chars=30):
        """Get surrounding text around a match rectangle."""
        if textpage:
            text = page.get_text("text", textpage=textpage)
        else:
            text = page.get_text("text")
        idx = text.lower().find(keyword.lower())
        if idx == -1:
            return keyword
        start = max(0, idx - context_chars)
        end = min(len(text), idx + len(keyword) + context_chars)
        snippet = text[start:end].replace("\n", " ").strip()
        if start > 0:
            snippet = "…" + snippet
        if end < len(text):
            snippet += "…"
        return snippet

    def _on_result_clicked(self, page_index, rect):
        if self._viewer:
            self._viewer.set_active_highlight(page_index, rect)
            self._viewer.scroll_to_page(page_index)

    def _on_page_changed(self, page_num):
        state = self._current_state
        if state and state.doc:
            total = len(state.doc)
            self._status_page = f"Page {page_num} / {total}"
            self._update_status()
            # Sync thumbnail panel
            self._thumb_panel.set_current_page(page_num - 1)
            # Sync page indicator
            self._page_label.setText(f"{page_num} / {total}")

    # ── Redaction ─────────────────────────────────────────────

    def _redact_all(self):
        state = self._current_state
        if not state or not state.search_results or not state.doc:
            return
        self._do_redaction(state.search_results)

    def _redact_selected(self, selected_results):
        if not selected_results or not self._doc:
            return
        self._do_redaction(selected_results)

    def _do_redaction(self, results):
        """Mark redaction annotations, show preview, and apply if confirmed."""
        state = self._current_state
        if not state or not state.doc:
            return
        doc = state.doc
        viewer = state.viewer

        # Group by page
        by_page = {}
        for r in results:
            by_page.setdefault(r.page_index, []).append(r.rect)

        # Mark annotations
        for page_index, rects in by_page.items():
            page = doc[page_index]
            mark_for_redaction(page, rects)

        # Show preview dialog
        dialog = PreviewDialog(doc, self)
        if dialog.exec() == PreviewDialog.DialogCode.Accepted:
            # Apply redactions permanently
            apply_redactions(doc)
            state.search_results.clear()
            self._search_panel.clear_results()
            viewer.clear_highlights()
            viewer.refresh()
            # Refresh thumbnails after redaction
            self._thumb_panel.load_document(doc)
            QMessageBox.information(
                self,
                "Redaction Applied",
                "Text has been permanently redacted.\n"
                "Use 'Save As' to save the redacted PDF.",
            )
        else:
            # Remove unapplied redaction annotations
            for page_index in by_page:
                page = doc[page_index]
                annot = page.first_annot
                while annot:
                    next_annot = annot.next
                    if annot.type[0] == fitz.PDF_ANNOT_REDACT:
                        page.delete_annot(annot)
                    annot = next_annot
