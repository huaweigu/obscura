import fitz
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QLabel


class PageLabel(QLabel):
    """A label that renders a single PDF page and optional highlight overlays."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlights = []  # list of fitz.Rect in page coordinates
        self._page_rect = None  # fitz page mediabox
        self._scale = 1.0

    def set_highlights(self, rects, page_rect, scale):
        self.highlights = rects
        self._page_rect = page_rect
        self._scale = scale
        self.update()

    def clear_highlights(self):
        self.highlights = []
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.highlights or self._page_rect is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(255, 255, 0, 100)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        for r in self.highlights:
            x = int(r.x0 * self._scale)
            y = int(r.y0 * self._scale)
            w = int(r.width * self._scale)
            h = int(r.height * self._scale)
            painter.drawRect(QRect(x, y, w, h))
        painter.end()


class PdfViewer(QScrollArea):
    """Scrollable multi-page PDF viewer with zoom and highlight support."""

    page_changed = Signal(int)  # emits 1-based page number

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._layout.setSpacing(10)
        self.setWidget(self._container)

        self._doc = None
        self._zoom = 1.5  # default DPI multiplier (1.0 = 72 DPI)
        self._page_labels = []  # list of PageLabel widgets
        self._highlights = {}  # page_index -> list of fitz.Rect
        self._last_reported_page = -1

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    @property
    def doc(self):
        return self._doc

    @property
    def zoom(self):
        return self._zoom

    @property
    def page_count(self):
        return len(self._doc) if self._doc else 0

    def load_document(self, doc):
        """Load a fitz.Document and render all pages."""
        self._doc = doc
        self._highlights.clear()
        self._render_all()

    def _render_all(self):
        """Render all pages at the current zoom level."""
        # Clear existing
        for lbl in self._page_labels:
            self._layout.removeWidget(lbl)
            lbl.deleteLater()
        self._page_labels.clear()

        if not self._doc:
            return

        for i in range(len(self._doc)):
            lbl = self._render_page(i)
            self._layout.addWidget(lbl)
            self._page_labels.append(lbl)

    def _render_page(self, page_index):
        """Render a single page to a PageLabel."""
        page = self._doc[page_index]
        mat = fitz.Matrix(self._zoom, self._zoom)
        pix = page.get_pixmap(matrix=mat)
        fmt = QImage.Format.Format_RGB888 if pix.n == 3 else QImage.Format.Format_RGBA8888
        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
        qpixmap = QPixmap.fromImage(qimg)

        lbl = PageLabel()
        lbl.setPixmap(qpixmap)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Apply any highlights for this page
        if page_index in self._highlights:
            lbl.set_highlights(self._highlights[page_index], page.rect, self._zoom)

        return lbl

    def set_zoom(self, zoom):
        """Set the zoom level and re-render."""
        self._zoom = max(0.5, min(zoom, 5.0))
        self._render_all()

    def zoom_in(self):
        self.set_zoom(self._zoom + 0.25)

    def zoom_out(self):
        self.set_zoom(self._zoom - 0.25)

    def set_highlights(self, highlights_by_page):
        """Set highlight rectangles. highlights_by_page: dict of page_index -> [fitz.Rect]."""
        self._highlights = highlights_by_page
        # Update existing page labels
        for i, lbl in enumerate(self._page_labels):
            if i in self._highlights:
                page = self._doc[i]
                lbl.set_highlights(self._highlights[i], page.rect, self._zoom)
            else:
                lbl.clear_highlights()

    def clear_highlights(self):
        self._highlights.clear()
        for lbl in self._page_labels:
            lbl.clear_highlights()

    def scroll_to_page(self, page_index):
        """Scroll the viewer so that the given page is visible."""
        if 0 <= page_index < len(self._page_labels):
            lbl = self._page_labels[page_index]
            self.ensureWidgetVisible(lbl, 0, 50)

    def current_page(self):
        """Return the 1-based index of the page currently most visible."""
        if not self._page_labels:
            return 0
        viewport_center = self.verticalScrollBar().value() + self.viewport().height() // 2
        for i, lbl in enumerate(self._page_labels):
            top = lbl.geometry().top()
            bottom = lbl.geometry().bottom()
            if top <= viewport_center <= bottom:
                return i + 1
        return 1

    def _on_scroll(self):
        page = self.current_page()
        if page != self._last_reported_page:
            self._last_reported_page = page
            self.page_changed.emit(page)

    def refresh(self):
        """Re-render all pages (e.g. after redaction is applied)."""
        self._render_all()
