import fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
)

from app.batch_dialog import BatchDialog
from app.pdf_viewer import PdfViewer
from app.preview_dialog import PreviewDialog
from app.redactor import apply_redactions, mark_for_redaction, save
from app.search_panel import SearchPanel, SearchResult


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Text Redactor")
        self.resize(1200, 800)

        self._doc = None
        self._file_path = None
        self._search_results = []
        self._ocr_textpages = {}  # page_index -> fitz.TextPage (for image-based docs)
        self._is_image_source = False

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

        batch_act = QAction("Batch Redact", self)
        batch_act.triggered.connect(self._open_batch_dialog)
        tb.addAction(batch_act)

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
            self,
            "Open File",
            "",
            "Supported Files (*.pdf *.jpg *.jpeg *.png *.bmp *.tiff *.tif);;"
            "PDF Files (*.pdf);;"
            "Image Files (*.jpg *.jpeg *.png *.bmp *.tiff *.tif)",
        )
        if not path:
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

        self._doc = doc
        self._file_path = path
        self._is_image_source = is_image
        self._search_results.clear()
        self._ocr_textpages.clear()
        self._search_panel.clear_results()
        self._viewer.load_document(doc)

        self._status_file = f"File: {path.split('/')[-1]}"
        self._status_page = f"Page 1 / {len(doc)}"
        self._update_status()

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

    # ── Search ────────────────────────────────────────────────

    def _do_search(self, keyword):
        if not self._doc:
            return

        # Run OCR on image-sourced docs if not already cached
        if self._is_image_source and not self._ocr_textpages:
            self.statusBar().showMessage("Running OCR…")
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            for i in range(len(self._doc)):
                page = self._doc[i]
                self._ocr_textpages[i] = page.get_textpage_ocr(
                    language="eng", full=True
                )
            self._update_status()

        results = []
        highlights = {}
        for page_index in range(len(self._doc)):
            page = self._doc[page_index]
            tp = self._ocr_textpages.get(page_index)
            if tp:
                matches = page.search_for(keyword, textpage=tp)
            else:
                matches = page.search_for(keyword)
            for rect in matches:
                snippet = self._extract_snippet(page, rect, keyword, tp)
                results.append(SearchResult(page_index, rect, snippet))
                highlights.setdefault(page_index, []).append(rect)

        self._search_results = results
        self._search_panel.set_results(results)
        self._viewer.set_highlights(highlights)

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
