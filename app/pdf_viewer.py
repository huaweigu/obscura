import fitz
from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class PageLabel(QLabel):
    """A label that renders a single PDF page and optional highlight/selection overlays."""

    # Signal for in-place edit commit (page_index, span_info dict, new_text)
    text_edit_committed = Signal(int, dict, str)

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
        # Editor mode state
        self._editor_mode_enabled = False
        # In-place edit state
        self._inline_editor = None  # active QLineEdit overlay
        self._editing_span = None  # span dict being edited

    def set_active_highlight(self, rect):
        """Set a single rect as the active (focused) highlight."""
        self._active_highlight = rect
        self.update()

    def clear_active_highlight(self):
        self._active_highlight = None
        self.update()

    def set_text_selection_enabled(self, enabled):
        self._text_selection_enabled = enabled
        if enabled:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        elif not self._editor_mode_enabled:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_editor_mode_enabled(self, enabled):
        self._editor_mode_enabled = enabled
        if enabled:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif not self._text_selection_enabled:
            self.setCursor(Qt.CursorShape.ArrowCursor)

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
        if event.button() == Qt.MouseButton.LeftButton and self._editor_mode_enabled:
            # If clicking outside an active inline editor, commit it first
            if self._inline_editor:
                self._commit_inline_edit()
                return

            pos = event.position()
            pdf_x = pos.x() / self._scale
            pdf_y = pos.y() / self._scale
            self._start_inline_edit(pdf_x, pdf_y)
            return
        if not self._text_selection_enabled:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._selecting = True
            self._selection_start = event.position().toPoint()
            self._selection_end = self._selection_start
            self._selection_rect = None
            self.update()

    # ── In-place text editing ────────────────────────────────

    def _start_inline_edit(self, pdf_x, pdf_y):
        """Show a QLineEdit overlay on top of the clicked text span."""
        from app.text_editor import get_span_at_point

        # Need the fitz page — walk up to PdfViewer to get the doc
        viewer = self.parent()
        while viewer and not isinstance(viewer, PdfViewer):
            viewer = viewer.parent()
        if not viewer or not viewer.doc:
            return
        if self._page_index >= len(viewer.doc):
            return

        page = viewer.doc[self._page_index]
        span = get_span_at_point(page, fitz.Point(pdf_x, pdf_y))
        if span is None:
            return

        self._editing_span = span
        bbox = span["bbox"]  # (x0, y0, x1, y1) in PDF coords

        # Convert bbox to widget coords
        wx = int(bbox[0] * self._scale)
        wy = int(bbox[1] * self._scale)
        ww = int((bbox[2] - bbox[0]) * self._scale)
        wh = int((bbox[3] - bbox[1]) * self._scale)

        # Scaled font size for the editor
        scaled_font_size = max(8, int(span["size"] * self._scale * 0.85))

        editor = QLineEdit(self)
        editor.setText(span["text"])
        editor.setGeometry(wx, wy, max(ww, 60), max(wh, 20))
        editor.setFont(QFont("Helvetica", scaled_font_size))
        editor.setStyleSheet(
            "QLineEdit {"
            "  background: rgba(255, 255, 255, 230);"
            "  border: 2px solid #4a9eff;"
            "  border-radius: 2px;"
            "  color: #111;"
            "  padding: 0px 2px;"
            "  selection-background-color: #4a9eff;"
            "}"
        )
        editor.selectAll()
        editor.setFocus()
        editor.show()

        editor.returnPressed.connect(self._commit_inline_edit)
        editor.installEventFilter(self)

        self._inline_editor = editor

    def _commit_inline_edit(self):
        """Commit the inline edit and emit signal."""
        if not self._inline_editor or not self._editing_span:
            return

        new_text = self._inline_editor.text().strip()
        span = self._editing_span

        # Clean up
        self._inline_editor.deleteLater()
        self._inline_editor = None
        self._editing_span = None

        if new_text and new_text != span["text"]:
            self.text_edit_committed.emit(self._page_index, span, new_text)

    def _cancel_inline_edit(self):
        """Cancel the inline edit without committing."""
        if self._inline_editor:
            self._inline_editor.removeEventFilter(self)
            self._inline_editor.deleteLater()
            self._inline_editor = None
            self._editing_span = None

    def cancel_inline_edit(self):
        """Public alias — used by the viewer before it discards this label."""
        self._cancel_inline_edit()

    def eventFilter(self, obj, event):
        """Handle Escape key and focus-out on the inline editor."""
        if obj is self._inline_editor:
            if event.type() == event.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    self._cancel_inline_edit()
                    return True
            elif event.type() == event.Type.FocusOut:
                # Commit on focus loss (clicking elsewhere)
                self._commit_inline_edit()
                return True
        return super().eventFilter(obj, event)

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


FIT_WIDTH = "width"
FIT_PAGE = "page"


class PdfViewer(QScrollArea):
    """Scrollable multi-page PDF viewer with zoom, highlight, and text selection support."""

    page_changed = Signal(int)  # emits 1-based page number
    zoom_changed = Signal(float)  # emits current zoom level
    text_edit_committed = Signal(int, dict, str)  # page_index, span_info, new_text

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
        # Active (focused) result, kept at viewer level so it survives the
        # full re-render that every zoom change performs.
        self._active_page = None
        self._active_rect = None
        self._last_reported_page = -1
        self._text_selection_enabled = False
        self._editor_mode_enabled = False
        # Documents open fitted to the window, like Preview/Acrobat/Chrome,
        # rather than at a fixed 100%. The mode is sticky: it survives window
        # resizes and panel toggles, and is dropped only when the user picks
        # an explicit zoom.
        self._fit_mode = FIT_WIDTH
        self._fit_pending = False
        self._scroll_top_after_fit = False

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

    @property
    def fit_mode(self):
        """FIT_WIDTH, FIT_PAGE, or None when an explicit zoom is in force."""
        return self._fit_mode

    def load_document(self, doc, reset_position=True):
        """Load a fitz.Document and render all pages.

        `reset_position` starts the reader at the top, which is right when
        opening a file. Callers that are reloading the *same* document — a
        save that rewrites the file, say — pass False so the reader stays
        where they were.
        """
        self._doc = doc
        self._highlights.clear()
        self._active_page = None
        self._active_rect = None
        self._scroll_top_after_fit = reset_position
        if self._fit_mode:
            # Sizes the page to the window instead of opening at a fixed 100%.
            # If the widget has no geometry yet, resizeEvent re-fits later.
            self._apply_fit()
        else:
            self._render_all()
        if reset_position:
            self.verticalScrollBar().setValue(0)

    def resizeEvent(self, event):
        """Keep the page fitted when the window or the side panel changes."""
        super().resizeEvent(event)
        if self._fit_mode and self._doc:
            self._schedule_fit()

    def _schedule_fit(self):
        """Re-fit once the current layout pass has finished.

        Re-rendering inside resizeEvent fights Qt's own layout: the page
        widgets end up sharing one geometry and the scroll range collapses to
        zero. Deferring lets the resize complete first, and coalesces the
        burst of resizes produced by dragging a window edge.
        """
        if self._fit_pending:
            return
        self._fit_pending = True
        QTimer.singleShot(0, self, self._run_pending_fit)

    def _run_pending_fit(self):
        self._fit_pending = False
        changed = bool(self._fit_mode and self._doc) and self._apply_fit()
        if self._scroll_top_after_fit and not changed:
            # The fit has converged, so this is the reader's real starting
            # position. Release the pin.
            self._scroll_top_after_fit = False
            self.verticalScrollBar().setValue(0)

    def _render_all(self):
        """Render all pages at the current zoom level.

        Every page widget is rebuilt, so any state living on a PageLabel must
        be restored from viewer-level state at the end of this method.
        """
        # Clear existing
        for lbl in self._page_labels:
            lbl.cancel_inline_edit()
            self._layout.removeWidget(lbl)
            lbl.deleteLater()
        self._page_labels.clear()

        if not self._doc:
            return

        for i in range(len(self._doc)):
            lbl = self._render_page(i)
            self._layout.addWidget(lbl)
            self._page_labels.append(lbl)

        # Re-apply the active result marker onto the fresh labels.
        if (
            self._active_rect is not None
            and self._active_page is not None
            and 0 <= self._active_page < len(self._page_labels)
        ):
            self._page_labels[self._active_page].set_active_highlight(self._active_rect)

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
        lbl._scale = self._zoom  # always set scale for coordinate conversion
        lbl.set_text_selection_enabled(self._text_selection_enabled)
        lbl.set_editor_mode_enabled(self._editor_mode_enabled)

        # Connect editor mode signal
        lbl.text_edit_committed.connect(self.text_edit_committed)

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

    def _scroll_anchor(self):
        """Current reading position as (page_index, fraction down that page).

        Anchored on the viewport centre — the same point current_page() uses —
        so restoring the anchor keeps the reader on the page they were on.
        """
        if not self._page_labels:
            return None
        centre = self.verticalScrollBar().value() + self.viewport().height() / 2
        for i, lbl in enumerate(self._page_labels):
            geo = lbl.geometry()
            if geo.top() <= centre <= geo.bottom():
                return i, (centre - geo.top()) / max(geo.height(), 1)
        # Centre fell in the gap between pages; anchor to the nearest one.
        if centre < self._page_labels[0].geometry().top():
            return 0, 0.0
        return len(self._page_labels) - 1, 1.0

    def _restore_scroll_anchor(self, anchor):
        if anchor is None:
            return
        page_index, fraction = anchor
        if not 0 <= page_index < len(self._page_labels):
            return
        geo = self._page_labels[page_index].geometry()
        centre = geo.top() + fraction * geo.height()
        self.verticalScrollBar().setValue(
            int(centre - self.viewport().height() / 2)
        )

    def set_zoom(self, zoom):
        """Set an explicit zoom level. This leaves any active fit mode."""
        self._fit_mode = None
        self._apply_zoom(zoom)

    @staticmethod
    def _clamp_zoom(zoom):
        return max(0.05, min(zoom, 5.0))

    def _apply_zoom(self, zoom):
        """Re-render at `zoom`, keeping the reader's place. Fit mode intact."""
        # A freshly opened document has no place to keep — pin it to the top
        # until the fit has converged, otherwise the anchor computed against
        # half-laid-out geometry drops the reader into the middle of page 1.
        anchor = None if self._scroll_top_after_fit else self._scroll_anchor()
        self._zoom = self._clamp_zoom(zoom)
        self._render_all()
        # The new page geometry has to exist before the anchor can be mapped
        # onto it. Deferring to the event loop is not enough — the timer fires
        # before the layout is recomputed — so force the layout here.
        # Note: only activate() the layout. adjustSize() on the container
        # fights setWidgetResizable(True), which leaves every page sharing one
        # geometry and collapses the scroll range until the next layout pass.
        self._layout.activate()
        if anchor is None:
            self.verticalScrollBar().setValue(0)
        else:
            self._restore_scroll_anchor(anchor)
        # Belt and braces: if the scroll range only widens on a later resize
        # event, the value above would have been clamped. Re-apply once Qt has
        # settled. `self` is passed as the context object so the callback is
        # dropped if this viewer is destroyed first (closing a tab does that).
        QTimer.singleShot(0, self, lambda a=anchor: self._restore_scroll_anchor(a))
        self.zoom_changed.emit(self._zoom)

    def zoom_in(self):
        self.set_zoom(self._zoom + 0.25)

    def zoom_out(self):
        self.set_zoom(self._zoom - 0.25)

    # ── Fit modes ────────────────────────────────────────────
    #
    # These live on the viewer because only the viewer knows the chrome it
    # adds around a page: container margins plus whichever scrollbars show.

    def _chrome_width(self):
        """Horizontal space the viewer itself consumes, as things stand now."""
        margins = self._layout.contentsMargins()
        bar = self.verticalScrollBar()
        return margins.left() + margins.right() + (bar.width() if bar.isVisible() else 0)

    def _chrome_height(self):
        """Vertical space the viewer itself consumes, as things stand now."""
        margins = self._layout.contentsMargins()
        bar = self.horizontalScrollBar()
        return margins.top() + margins.bottom() + (bar.height() if bar.isVisible() else 0)

    def _fit_available(self):
        """Space a page may occupy, assuming both scrollbars are present.

        Whether a scrollbar shows depends on the zoom we are about to pick, so
        measuring the current state gives a different answer before and after
        the fit. Normalising to "both bars showing" makes the result
        deterministic and idempotent: reserving room needlessly costs a dozen
        pixels, whereas not reserving it produces exactly the overflow these
        fit modes exist to avoid.
        """
        margins = self._layout.contentsMargins()
        vbar = self.verticalScrollBar()
        hbar = self.horizontalScrollBar()
        v_reserve = vbar.sizeHint().width()
        h_reserve = hbar.sizeHint().height()

        # viewport() already excludes a bar that is currently showing.
        width = self.viewport().width() + (v_reserve if vbar.isVisible() else 0)
        height = self.viewport().height() + (h_reserve if hbar.isVisible() else 0)

        return (
            width - v_reserve - margins.left() - margins.right(),
            height - h_reserve - margins.top() - margins.bottom(),
        )

    def fit_width(self):
        """Fit the widest page to the viewport width, and stay fitted."""
        self._fit_mode = FIT_WIDTH
        self._apply_fit()

    def fit_page(self):
        """Fit a whole page into the viewport, and stay fitted."""
        self._fit_mode = FIT_PAGE
        self._apply_fit()

    def _apply_fit(self):
        """Recompute the zoom for the current fit mode and viewport.

        Returns True if that re-rendered. _run_pending_fit uses the answer to
        tell a converged fit from one still settling, so every path here must
        report a bool.
        """
        if not self._doc or len(self._doc) == 0:
            return False
        widest = max(page.rect.width for page in self._doc)
        tallest = max(page.rect.height for page in self._doc)
        if widest <= 0 or tallest <= 0:
            return False

        avail_w, avail_h = self._fit_available()
        if avail_w <= 0:
            return False

        if self._fit_mode == FIT_PAGE:
            if avail_h <= 0:
                return False
            zoom = min(avail_w / widest, avail_h / tallest)
        else:
            zoom = avail_w / widest

        # Compare against the clamped value: re-rendering is what makes the
        # scrollbar appear or disappear, which resizes the viewport, which
        # schedules another fit. Without this the viewer re-renders forever.
        zoom = self._clamp_zoom(zoom)
        if abs(zoom - self._zoom) < 1e-6:
            return False

        self._apply_zoom(zoom)
        return True

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
        self._active_page = None
        self._active_rect = None
        for lbl in self._page_labels:
            lbl.clear_highlights()
            lbl.clear_active_highlight()

    def set_active_highlight(self, page_index, rect):
        """Highlight a single result rect in a distinct color."""
        self._active_page = page_index
        self._active_rect = rect
        for i, lbl in enumerate(self._page_labels):
            if i == page_index:
                lbl.set_active_highlight(rect)
            else:
                lbl.clear_active_highlight()

    def clear_active_highlight(self):
        self._active_page = None
        self._active_rect = None
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

    def set_editor_mode_enabled(self, enabled):
        """Enable or disable editor mode on all pages."""
        self._editor_mode_enabled = enabled
        for lbl in self._page_labels:
            lbl.set_editor_mode_enabled(enabled)

    def refresh(self):
        """Re-render all pages (e.g. after redaction is applied)."""
        self._render_all()
