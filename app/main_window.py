import fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
)

from app.pdf_viewer import PdfViewer
from app.preview_dialog import PreviewDialog
from app.redactor import apply_redactions, mark_for_redaction, save
from app.search_panel import SearchPanel, SearchResult


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Text Redactor")
        self.resize(1200, 800)

        self._doc = None
        self._file_path = None
        self._search_results = []

        self._setup_viewer()
        self._setup_search_panel()
        self._setup_toolbar()
        self._setup_statusbar()

    # ── UI Setup ──────────────────────────────────────────────

    def _setup_viewer(self):
        self._viewer = PdfViewer()
        self.setCentralWidget(self._viewer)
        self._viewer.page_changed.connect(self._on_page_changed)

    def _setup_search_panel(self):
        self._search_panel = SearchPanel()
        dock = QDockWidget("Search && Redact", self)
        dock.setWidget(self._search_panel)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

        self._search_panel.search_requested.connect(self._do_search)
        self._search_panel.result_clicked.connect(self._on_result_clicked)
        self._search_panel.redact_all_requested.connect(self._redact_all)
        self._search_panel.redact_selected_requested.connect(self._redact_selected)

    def _setup_toolbar(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)

        open_act = QAction("Open", self)
        open_act.setShortcut(QKeySequence.StandardKey.Open)
        open_act.triggered.connect(self._open_file)
        tb.addAction(open_act)

        save_act = QAction("Save As", self)
        save_act.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_act.triggered.connect(self._save_file)
        tb.addAction(save_act)

        tb.addSeparator()

        zoom_in_act = QAction("Zoom In", self)
        zoom_in_act.setShortcut(QKeySequence.StandardKey.ZoomIn)
        zoom_in_act.triggered.connect(self._viewer.zoom_in)
        tb.addAction(zoom_in_act)

        zoom_out_act = QAction("Zoom Out", self)
        zoom_out_act.setShortcut(QKeySequence.StandardKey.ZoomOut)
        zoom_out_act.triggered.connect(self._viewer.zoom_out)
        tb.addAction(zoom_out_act)

    def _setup_statusbar(self):
        self._status_file = ""
        self._status_page = ""
        self.statusBar().showMessage("No file loaded")

    def _update_status(self):
        parts = []
        if self._status_file:
            parts.append(self._status_file)
        if self._status_page:
            parts.append(self._status_page)
        self.statusBar().showMessage("  |  ".join(parts) if parts else "No file loaded")

    # ── File Operations ───────────────────────────────────────

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF", "", "PDF Files (*.pdf)"
        )
        if not path:
            return
        try:
            doc = fitz.open(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open PDF:\n{e}")
            return

        self._doc = doc
        self._file_path = path
        self._search_results.clear()
        self._search_panel.clear_results()
        self._viewer.load_document(doc)

        self._status_file = f"File: {path.split('/')[-1]}"
        self._status_page = f"Page 1 / {len(doc)}"
        self._update_status()

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

    # ── Search ────────────────────────────────────────────────

    def _do_search(self, keyword):
        if not self._doc:
            return
        results = []
        highlights = {}
        for page_index in range(len(self._doc)):
            page = self._doc[page_index]
            matches = page.search_for(keyword)
            for rect in matches:
                # Extract a short text snippet around the match area
                snippet = self._extract_snippet(page, rect, keyword)
                results.append(SearchResult(page_index, rect, snippet))
                highlights.setdefault(page_index, []).append(rect)

        self._search_results = results
        self._search_panel.set_results(results)
        self._viewer.set_highlights(highlights)

    def _extract_snippet(self, page, rect, keyword, context_chars=30):
        """Get surrounding text around a match rectangle."""
        # Get all text on the page
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
        self._viewer.scroll_to_page(page_index)

    def _on_page_changed(self, page_num):
        if self._doc:
            self._status_page = f"Page {page_num} / {len(self._doc)}"
            self._update_status()

    # ── Redaction ─────────────────────────────────────────────

    def _redact_all(self):
        if not self._search_results or not self._doc:
            return
        self._do_redaction(self._search_results)

    def _redact_selected(self, selected_results):
        if not selected_results or not self._doc:
            return
        self._do_redaction(selected_results)

    def _do_redaction(self, results):
        """Mark redaction annotations, show preview, and apply if confirmed."""
        # Group by page
        by_page = {}
        for r in results:
            by_page.setdefault(r.page_index, []).append(r.rect)

        # Mark annotations
        for page_index, rects in by_page.items():
            page = self._doc[page_index]
            mark_for_redaction(page, rects)

        # Show preview dialog
        dialog = PreviewDialog(self._doc, self)
        if dialog.exec() == PreviewDialog.DialogCode.Accepted:
            # Apply redactions permanently
            apply_redactions(self._doc)
            self._search_results.clear()
            self._search_panel.clear_results()
            self._viewer.clear_highlights()
            self._viewer.refresh()
            QMessageBox.information(
                self,
                "Redaction Applied",
                "Text has been permanently redacted.\n"
                "Use 'Save As' to save the redacted PDF.",
            )
        else:
            # Remove unapplied redaction annotations
            for page_index in by_page:
                page = self._doc[page_index]
                annot = page.first_annot
                while annot:
                    next_annot = annot.next
                    if annot.type[0] == fitz.PDF_ANNOT_REDACT:
                        page.delete_annot(annot)
                    annot = next_annot
