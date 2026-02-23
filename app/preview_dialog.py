import fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
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

        warning = QLabel(
            "<b>Warning:</b> Redaction is permanent and irreversible. "
            "The redacted text will be completely removed from the PDF."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #c0392b; padding: 8px;")
        main_layout.addWidget(warning)

        # Headers
        header_layout = QHBoxLayout()
        before_header = QLabel("<b>Before (with annotations)</b>")
        before_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        after_header = QLabel("<b>After (redacted)</b>")
        after_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Confirm Redaction")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        self._populate_preview()

    def _populate_preview(self):
        """Render before/after for each page that has redaction annotations."""
        zoom = 1.0
        pages_with_redactions = []
        for i in range(len(self._doc)):
            page = self._doc[i]
            annot = page.first_annot
            while annot:
                if annot.type[0] == fitz.PDF_ANNOT_REDACT:
                    pages_with_redactions.append(i)
                    break
                annot = annot.next
            else:
                continue

        if not pages_with_redactions:
            lbl = QLabel("No redaction annotations found.")
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
