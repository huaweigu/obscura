import fitz
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QScrollArea, QVBoxLayout, QWidget


class ThumbnailLabel(QLabel):
    """A clickable thumbnail for one PDF page."""

    clicked = Signal(int)  # emits 0-based page index

    def __init__(self, page_index, parent=None):
        super().__init__(parent)
        self._page_index = page_index
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("border: 2px solid transparent; border-radius: 4px;")

    def set_selected(self, selected):
        self._selected = selected
        if selected:
            self.setStyleSheet("border: 2px solid #4a9eff; border-radius: 4px;")
        else:
            self.setStyleSheet("border: 2px solid transparent; border-radius: 4px;")

    def mousePressEvent(self, event):
        self.clicked.emit(self._page_index)


class ThumbnailPanel(QWidget):
    """Scrollable vertical strip of page thumbnails."""

    page_clicked = Signal(int)  # emits 0-based page index

    THUMB_SCALE = 0.22

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._layout.setSpacing(12)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._scroll.setWidget(self._container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

        self._thumbnails = []  # list of ThumbnailLabel
        self._current_page = 0

    def load_document(self, doc):
        """Generate thumbnails for all pages."""
        self._clear()
        if not doc:
            return
        for i in range(len(doc)):
            page = doc[i]
            pixmap = self._render_thumbnail(page)

            lbl = ThumbnailLabel(i)
            lbl.setPixmap(pixmap)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.clicked.connect(self._on_thumb_clicked)

            # Drop shadow
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(12)
            shadow.setOffset(0, 2)
            shadow.setColor(QColor(0, 0, 0, 60))
            lbl.setGraphicsEffect(shadow)

            self._layout.addWidget(lbl)

            num = QLabel(str(i + 1))
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setStyleSheet("color: #a0a8b8; font-size: 11px; margin-bottom: 4px;")
            self._layout.addWidget(num)

            self._thumbnails.append(lbl)

        self._current_page = 0
        if self._thumbnails:
            self._thumbnails[0].set_selected(True)

    def set_current_page(self, page_index):
        """Highlight the thumbnail for the given page."""
        if 0 <= self._current_page < len(self._thumbnails):
            self._thumbnails[self._current_page].set_selected(False)
        self._current_page = page_index
        if 0 <= page_index < len(self._thumbnails):
            self._thumbnails[page_index].set_selected(True)
            self._scroll.ensureWidgetVisible(self._thumbnails[page_index])

    def _render_thumbnail(self, page):
        mat = fitz.Matrix(self.THUMB_SCALE, self.THUMB_SCALE)
        pix = page.get_pixmap(matrix=mat)
        fmt = (
            QImage.Format.Format_RGB888
            if pix.n == 3
            else QImage.Format.Format_RGBA8888
        )
        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
        return QPixmap.fromImage(qimg)

    def _on_thumb_clicked(self, page_index):
        self.page_clicked.emit(page_index)

    def _clear(self):
        self._thumbnails.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
