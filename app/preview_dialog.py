import fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


def _render_page(page, zoom=1.0):
    """Render a fitz page to QPixmap."""
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    fmt = QImage.Format.Format_RGB888 if pix.n == 3 else QImage.Format.Format_RGBA8888
    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
    return QPixmap.fromImage(qimg)


class PreviewDialog(QDialog):
    """Side-by-side before/after preview of pages that have redaction annotations."""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Redaction Preview")
        self.resize(1100, 700)
        self._doc = doc
        self._accepted = False

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("Redaction Preview")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        main_layout.addWidget(title)

        warning = QLabel(
            "Warning: Redaction is permanent and irreversible. "
            "The redacted text will be completely removed from the PDF."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "color: #ff6b6b; background: #2a1a1e; border: 1px solid #5b1a2a;"
            "border-radius: 8px; padding: 10px; font-size: 12px;"
        )
        main_layout.addWidget(warning)

        # Headers
        header_layout = QHBoxLayout()
        before_header = QLabel("BEFORE")
        before_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        before_header.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #e94560;"
            "letter-spacing: 1px; padding: 6px;"
        )
        after_header = QLabel("AFTER")
        after_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        after_header.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #4ecdc4;"
            "letter-spacing: 1px; padding: 6px;"
        )
        header_layout.addWidget(before_header)
        header_layout.addWidget(after_header)
        main_layout.addLayout(header_layout)

        # Side-by-side scroll areas
        side_layout = QHBoxLayout()

        self._before_scroll = QScrollArea()
        self._before_scroll.setWidgetResizable(True)
        self._before_container = QWidget()
        self._before_layout = QVBoxLayout(self._before_container)
        self._before_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._before_scroll.setWidget(self._before_container)

        self._after_scroll = QScrollArea()
        self._after_scroll.setWidgetResizable(True)
        self._after_container = QWidget()
        self._after_layout = QVBoxLayout(self._after_container)
        self._after_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._after_scroll.setWidget(self._after_container)

        side_layout.addWidget(self._before_scroll)
        side_layout.addWidget(self._after_scroll)
        main_layout.addLayout(side_layout)

        # Sync scrolling
        self._before_scroll.verticalScrollBar().valueChanged.connect(
            self._after_scroll.verticalScrollBar().setValue
        )
        self._after_scroll.verticalScrollBar().valueChanged.connect(
            self._before_scroll.verticalScrollBar().setValue
        )

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("ghost")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        confirm_btn = QPushButton("Confirm Redaction")
        confirm_btn.setObjectName("danger")
        confirm_btn.clicked.connect(self.accept)
        btn_layout.addWidget(confirm_btn)
        main_layout.addLayout(btn_layout)

        self._populate_preview()

    @staticmethod
    def _page_has_redactions(page):
        annot = page.first_annot
        while annot:
            if annot.type[0] == fitz.PDF_ANNOT_REDACT:
                return True
            annot = annot.next
        return False

    def _populate_preview(self):
        """Render before/after for each page that has redaction annotations."""
        zoom = 1.0
        pages_with_redactions = [
            i for i in range(len(self._doc))
            if self._page_has_redactions(self._doc[i])
        ]

        if not pages_with_redactions:
            lbl = QLabel("No redaction annotations found.")
            lbl.setStyleSheet("color: #a0a8b8; font-size: 14px; padding: 20px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._before_layout.addWidget(lbl)
            return

        for page_idx in pages_with_redactions:
            page = self._doc[page_idx]

            # "Before" - render with annotations visible (red outlines)
            before_pix = _render_page(page, zoom)
            before_lbl = QLabel()
            before_lbl.setPixmap(before_pix)
            before_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            page_label_before = QLabel(f"Page {page_idx + 1}")
            page_label_before.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._before_layout.addWidget(page_label_before)
            self._before_layout.addWidget(before_lbl)

            # "After" - simulate by rendering with black fill over redact areas
            after_pix = self._render_redacted_preview(page, zoom)
            after_lbl = QLabel()
            after_lbl.setPixmap(after_pix)
            after_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            page_label_after = QLabel(f"Page {page_idx + 1}")
            page_label_after.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._after_layout.addWidget(page_label_after)
            self._after_layout.addWidget(after_lbl)

    def _render_redacted_preview(self, page, zoom):
        """Render a preview of how the page will look after redaction.

        Creates a temporary copy of the page, applies redactions on the copy,
        and renders the result — leaving the original document untouched.
        """
        page_index = page.number
        # Create a temporary single-page document from the original
        tmp_doc = fitz.open()
        tmp_doc.insert_pdf(self._doc, from_page=page_index, to_page=page_index)
        tmp_page = tmp_doc[0]

        # Copy redaction annotations to the temp page
        annot = page.first_annot
        while annot:
            if annot.type[0] == fitz.PDF_ANNOT_REDACT:
                tmp_page.add_redact_annot(annot.rect, fill=(0, 0, 0))
            annot = annot.next

        # Apply redactions on the temp copy
        tmp_page.apply_redactions()

        pixmap = _render_page(tmp_page, zoom)
        tmp_doc.close()
        return pixmap
