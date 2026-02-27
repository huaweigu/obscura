import fitz
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QLabel, QGraphicsDropShadowEffect


class PageLabel(QLabel):
    """A label that renders a single PDF page and optional highlight/selection overlays."""

    def __init__(self, page_index=0, parent=None):
        super().__init__(parent)
        self._page_index = page_index
        self.highlights = []  # list of fitz.Rect in page coordinates
        self._page_rect = None  # fitz page mediabox
        self._scale = 1.0
        # Text selection state
        self._selection_start = None
        self._selection_end = None
        self._selection_rect = None  # QRect in widget coords
        self._selecting = False
        self._text_selection_enabled = False
        self._active_highlight = None  # fitz.Rect in page coordinates

    def set_active_highlight(self, rect):
        """Set a single rect as the active (focused) highlight."""
        self._active_highlight = rect
        self.update()

    def clear_active_highlight(self):
        self._active_highlight = None
        self.update()

    def set_text_selection_enabled(self, enabled):
        self._text_selection_enabled = enabled
        self.setCursor(
            Qt.CursorShape.IBeamCursor if enabled else Qt.CursorShape.ArrowCursor
        )

    def set_highlights(self, rects, page_rect, scale):
        self.highlights = rects
        self._page_rect = page_rect
        self._scale = scale
        self.update()

    def clear_highlights(self):
        self.highlights = []
        self.update()

    def clear_selection(self):
        self._selection_start = None
        self._selection_end = None
        self._selection_rect = None
        self._selecting = False
        self.update()

    def get_selected_text(self, doc):
        """Extract text from the current selection rectangle."""
        if not self._selection_rect or self._selection_rect.isNull():
            return ""
        if not doc or self._page_index >= len(doc):
            return ""
        x0 = self._selection_rect.x() / self._scale
        y0 = self._selection_rect.y() / self._scale
        x1 = (self._selection_rect.x() + self._selection_rect.width()) / self._scale
        y1 = (self._selection_rect.y() + self._selection_rect.height()) / self._scale
        clip = fitz.Rect(x0, y0, x1, y1)
        page = doc[self._page_index]
        return page.get_text("text", clip=clip).strip()

    def mousePressEvent(self, event):
        if not self._text_selection_enabled:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._selecting = True
            self._selection_start = event.position().toPoint()
            self._selection_end = self._selection_start
            self._selection_rect = None
            self.update()

    def mouseMoveEvent(self, event):
        if not self._selecting:
            return
        self._selection_end = event.position().toPoint()
        self._update_selection_rect()
        self.update()

    def mouseReleaseEvent(self, event):
        if not self._selecting:
            return
        self._selecting = False
        self._selection_end = event.position().toPoint()
        self._update_selection_rect()
        self.update()

    def _update_selection_rect(self):
        if self._selection_start and self._selection_end:
            x1 = min(self._selection_start.x(), self._selection_end.x())
            y1 = min(self._selection_start.y(), self._selection_end.y())
            x2 = max(self._selection_start.x(), self._selection_end.x())
            y2 = max(self._selection_start.y(), self._selection_end.y())
            self._selection_rect = QRect(x1, y1, x2 - x1, y2 - y1)

    def paintEvent(self, event):
        super().paintEvent(event)
        has_highlights = self.highlights and self._page_rect is not None
        has_active = self._active_highlight is not None and self._page_rect is not None
        has_selection = self._selection_rect and not self._selection_rect.isNull()
        if not has_highlights and not has_active and not has_selection:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Draw search highlights (yellow)
        if has_highlights:
            painter.setBrush(QColor(255, 255, 0, 100))
            painter.setPen(Qt.PenStyle.NoPen)
            for r in self.highlights:
                x = int(r.x0 * self._scale)
                y = int(r.y0 * self._scale)
                w = int(r.width * self._scale)
                h = int(r.height * self._scale)
                painter.drawRect(QRect(x, y, w, h))
        # Draw active highlight (orange, more visible)
        if has_active:
            r = self._active_highlight
            x = int(r.x0 * self._scale)
            y = int(r.y0 * self._scale)
            w = int(r.width * self._scale)
            h = int(r.height * self._scale)
            painter.setBrush(QColor(255, 165, 0, 160))
            painter.setPen(QColor(255, 140, 0, 220))
            painter.drawRect(QRect(x, y, w, h))
        # Draw text selection (blue)
        if has_selection:
            painter.setBrush(QColor(51, 153, 255, 80))
            painter.setPen(QColor(51, 153, 255, 200))
            painter.drawRect(self._selection_rect)
        painter.end()


class PdfViewer(QScrollArea):
    """Scrollable multi-page PDF viewer with zoom, highlight, and text selection support."""

    page_changed = Signal(int)  # emits 1-based page number
    zoom_changed = Signal(float)  # emits current zoom level

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._layout.setSpacing(24)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self.setWidget(self._container)

        self._doc = None
        self._zoom = 1.0  # default DPI multiplier (1.0 = 72 DPI)
        self._page_labels = []  # list of PageLabel widgets
        self._highlights = {}  # page_index -> list of fitz.Rect
        self._last_reported_page = -1
        self._text_selection_enabled = False

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

        lbl = PageLabel(page_index=page_index)
        lbl.setPixmap(qpixmap)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.set_text_selection_enabled(self._text_selection_enabled)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 80))
        lbl.setGraphicsEffect(shadow)

        # Apply any highlights for this page
        if page_index in self._highlights:
            lbl.set_highlights(self._highlights[page_index], page.rect, self._zoom)

        return lbl

    def set_zoom(self, zoom):
        """Set the zoom level and re-render."""
        self._zoom = max(0.05, min(zoom, 5.0))
        self._render_all()
        self.zoom_changed.emit(self._zoom)

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

    def set_active_highlight(self, page_index, rect):
        """Highlight a single result rect in a distinct color."""
        for i, lbl in enumerate(self._page_labels):
            if i == page_index:
                lbl.set_active_highlight(rect)
            else:
                lbl.clear_active_highlight()

    def clear_active_highlight(self):
        for lbl in self._page_labels:
            lbl.clear_active_highlight()

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

    def set_text_selection_enabled(self, enabled):
        """Enable or disable text selection on all pages."""
        self._text_selection_enabled = enabled
        for lbl in self._page_labels:
            lbl.set_text_selection_enabled(enabled)

    def copy_selected_text(self):
        """Copy text from the active selection to clipboard."""
        if not self._doc:
            return
        from PySide6.QtWidgets import QApplication

        for lbl in self._page_labels:
            text = lbl.get_selected_text(self._doc)
            if text:
                QApplication.clipboard().setText(text)
                return

    def clear_selection(self):
        """Clear text selection on all pages."""
        for lbl in self._page_labels:
            lbl.clear_selection()

    def refresh(self):
        """Re-render all pages (e.g. after redaction is applied)."""
        self._render_all()
