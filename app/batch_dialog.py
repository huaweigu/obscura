import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from app.batch_processor import find_files, process_folder, search_folder


class _SearchWorker(QThread):
    """Worker thread that runs search (no redaction)."""

    progress = Signal(int, int, str, int)
    finished = Signal(object)

    def __init__(self, folder, keywords):
        super().__init__()
        self._folder = folder
        self._keywords = keywords

    def run(self):
        result = search_folder(
            self._folder,
            self._keywords,
            progress_callback=self._on_progress,
        )
        self.finished.emit(result)

    def _on_progress(self, file_index, total, current_file, match_count):
        self.progress.emit(file_index, total, current_file, match_count)


class _BatchWorker(QThread):
    """Worker thread that runs batch redaction."""

    progress = Signal(int, int, str, int)
    finished = Signal(object)

    def __init__(self, folder, keywords, output_folder):
        super().__init__()
        self._folder = folder
        self._keywords = keywords
        self._output_folder = output_folder

    def run(self):
        result = process_folder(
            self._folder,
            self._keywords,
            self._output_folder,
            progress_callback=self._on_progress,
        )
        self.finished.emit(result)

    def _on_progress(self, file_index, total, current_file, match_count):
        self.progress.emit(file_index, total, current_file, match_count)


class BatchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Redact")
        self.setFixedWidth(560)
        self._worker = None
        self._search_folder = None
        self._search_output = None
        self._search_keywords = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(28, 28, 28, 24)

        # ── Header ──
        title = QLabel("Batch Redact")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: white;")
        layout.addWidget(title)
        layout.addSpacing(4)

        subtitle = QLabel("Redact keywords across all PDFs and images in a folder.")
        subtitle.setStyleSheet("font-size: 13px; color: #888;")
        layout.addWidget(subtitle)
        layout.addSpacing(24)

        # ── Input folder ──
        lbl = QLabel("INPUT FOLDER")
        lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #e94560; letter-spacing: 1px;")
        layout.addWidget(lbl)
        layout.addSpacing(6)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self._input_edit = QLineEdit()
        self._input_edit.setPlaceholderText("Select folder containing PDFs/images…")
        self._input_edit.textChanged.connect(self._on_inputs_changed)
        input_row.addWidget(self._input_edit)
        browse_in = QPushButton("Browse")
        browse_in.setObjectName("browse")
        browse_in.setFixedWidth(72)
        browse_in.clicked.connect(self._browse_input)
        input_row.addWidget(browse_in)
        layout.addLayout(input_row)
        layout.addSpacing(16)

        # ── Output folder ──
        lbl = QLabel("OUTPUT FOLDER")
        lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #e94560; letter-spacing: 1px;")
        layout.addWidget(lbl)
        layout.addSpacing(6)

        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        self._output_edit = QLineEdit()
        self._output_edit.setPlaceholderText("Defaults to sibling 'redacted' folder")
        output_row.addWidget(self._output_edit)
        browse_out = QPushButton("Browse")
        browse_out.setObjectName("browse")
        browse_out.setFixedWidth(72)
        browse_out.clicked.connect(self._browse_output)
        output_row.addWidget(browse_out)
        layout.addLayout(output_row)
        layout.addSpacing(16)

        # ── Keywords ──
        lbl = QLabel("KEYWORDS")
        lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #e94560; letter-spacing: 1px;")
        layout.addWidget(lbl)
        layout.addSpacing(6)

        self._keyword_edit = QLineEdit()
        self._keyword_edit.setPlaceholderText("Comma-separated, e.g. secret, confidential")
        self._keyword_edit.textChanged.connect(self._on_inputs_changed)
        layout.addWidget(self._keyword_edit)
        layout.addSpacing(24)

        # ── Search button ──
        self._search_btn = QPushButton("SEARCH")
        self._search_btn.setObjectName("start")
        self._search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._search_btn.clicked.connect(self._search)
        layout.addWidget(self._search_btn)
        layout.addSpacing(20)

        # ── Progress section ──
        self._progress_container = QFrame()
        progress_layout = QVBoxLayout(self._progress_container)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(8)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(14)
        self._progress_bar.setTextVisible(False)
        progress_layout.addWidget(self._progress_bar)

        self._file_label = QLabel("")
        self._file_label.setStyleSheet("color: #888; font-size: 12px;")
        self._file_label.setWordWrap(True)
        progress_layout.addWidget(self._file_label)

        self._progress_container.setVisible(False)
        layout.addWidget(self._progress_container)

        # ── Search results: matched file list ──
        self._match_list_container = QFrame()
        match_layout = QVBoxLayout(self._match_list_container)
        match_layout.setContentsMargins(0, 0, 0, 0)
        match_layout.setSpacing(8)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._lbl_scanned = self._make_stat_card("0", "Scanned", "#0f3460")
        self._lbl_matched = self._make_stat_card("0", "Matched", "#0f3460")
        stats_row.addWidget(self._lbl_scanned)
        stats_row.addWidget(self._lbl_matched)
        match_layout.addLayout(stats_row)

        match_header = QLabel("MATCHED FILES")
        match_header.setStyleSheet("font-size: 11px; font-weight: bold; color: #e94560; letter-spacing: 1px; margin-top: 8px;")
        match_layout.addWidget(match_header)

        self._match_list = QTextEdit()
        self._match_list.setReadOnly(True)
        self._match_list.setMaximumHeight(160)
        match_layout.addWidget(self._match_list)

        self._search_errors = QTextEdit()
        self._search_errors.setReadOnly(True)
        self._search_errors.setMaximumHeight(80)
        self._search_errors.setVisible(False)
        match_layout.addWidget(self._search_errors)

        self._match_list_container.setVisible(False)
        layout.addWidget(self._match_list_container)
        layout.addSpacing(12)

        # ── Start Redaction button (shown after search) ──
        self._redact_btn = QPushButton("START REDACTION")
        self._redact_btn.setObjectName("start")
        self._redact_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._redact_btn.clicked.connect(self._redact)
        self._redact_btn.setVisible(False)
        layout.addWidget(self._redact_btn)
        layout.addSpacing(12)

        # ── Redaction results section ──
        self._results_container = QFrame()
        results_layout = QVBoxLayout(self._results_container)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(12)

        redact_stats_row = QHBoxLayout()
        redact_stats_row.setSpacing(12)
        self._lbl_redact_matched = self._make_stat_card("0", "Matched", "#0f3460")
        self._lbl_redacted = self._make_stat_card("0", "Redacted", "#5b1a3a")
        redact_stats_row.addWidget(self._lbl_redact_matched)
        redact_stats_row.addWidget(self._lbl_redacted)
        results_layout.addLayout(redact_stats_row)

        self._errors_text = QTextEdit()
        self._errors_text.setReadOnly(True)
        self._errors_text.setMaximumHeight(100)
        self._errors_text.setVisible(False)
        results_layout.addWidget(self._errors_text)

        self._results_container.setVisible(False)
        layout.addWidget(self._results_container)

        # ── Spacer + Close ──
        layout.addStretch()
        layout.addSpacing(8)
        self._close_btn = QPushButton("Close")
        self._close_btn.setObjectName("close")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.clicked.connect(self.accept)
        layout.addWidget(self._close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    @staticmethod
    def _make_stat_card(value, caption, bg_color):
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {bg_color}; border-radius: 10px; padding: 8px; }}"
        )
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(12, 12, 12, 10)
        vbox.setSpacing(2)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)

        val = QLabel(value)
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val.setStyleSheet("font-size: 28px; font-weight: bold; color: white;")
        val.setObjectName("value")
        vbox.addWidget(val)

        cap = QLabel(caption)
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap.setStyleSheet("font-size: 11px; color: #aaa; text-transform: uppercase; letter-spacing: 1px;")
        vbox.addWidget(cap)

        return card

    def _on_inputs_changed(self):
        """Reset search results when user changes folder or keywords."""
        self._match_list_container.setVisible(False)
        self._redact_btn.setVisible(False)
        self._results_container.setVisible(False)
        self._progress_container.setVisible(False)

    def _update_default_output(self):
        folder = self._input_edit.text().strip()
        if folder and not self._output_edit.text().strip():
            self._output_edit.setText(folder.rstrip(os.sep) + "_redacted")

    def _browse_input(self):
        path = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if path:
            self._input_edit.setText(path)
            self._update_default_output()

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if path:
            self._output_edit.setText(path)

    # ── Step 1: Search ──

    def _search(self):
        folder = self._input_edit.text().strip()
        output = self._output_edit.text().strip()
        raw_keywords = self._keyword_edit.text().strip()

        if not folder:
            QMessageBox.warning(self, "Missing Input", "Please select an input folder.")
            return
        if not output:
            output = folder.rstrip(os.sep) + "_redacted"
            self._output_edit.setText(output)
        keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
        if not keywords:
            QMessageBox.warning(self, "Missing Keyword", "Please enter at least one keyword.")
            return

        # Store for the redact step
        self._search_folder = folder
        self._search_output = output
        self._search_keywords = keywords

        # Search the output folder if it already has redacted files,
        # otherwise search the input folder (mirrors process_folder logic)
        search_target = folder
        if folder != output and os.path.exists(output) and find_files(output):
            search_target = output

        self._search_btn.setEnabled(False)
        self._progress_bar.setValue(0)
        self._progress_container.setVisible(True)
        self._match_list_container.setVisible(False)
        self._redact_btn.setVisible(False)
        self._results_container.setVisible(False)

        self._worker = _SearchWorker(search_target, keywords)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_search_finished)
        self._worker.start()

    def _on_progress(self, file_index, total, current_file, match_count):
        if total > 0:
            self._progress_bar.setMaximum(total)
            self._progress_bar.setValue(file_index + 1)
        self._file_label.setText(f"Scanning: {current_file}")

    def _on_search_finished(self, result):
        self._search_btn.setEnabled(True)
        self._file_label.setText("Search complete.")
        self._progress_bar.setValue(self._progress_bar.maximum())
        self._worker = None

        total_matches = sum(count for _, count in result.matches)

        # Update stat cards
        self._lbl_scanned.findChild(QLabel, "value").setText(str(result.total_files))
        self._lbl_matched.findChild(QLabel, "value").setText(str(len(result.matches)))

        # Populate matched file list
        if result.matches:
            lines = [f"{path}  —  {count} match{'es' if count != 1 else ''}"
                     for path, count in result.matches]
            self._match_list.setPlainText("\n".join(lines))
        else:
            self._match_list.setPlainText("No matches found.")

        # Show errors if any
        if result.errors:
            lines = [f"{path}: {msg}" for path, msg in result.errors]
            self._search_errors.setPlainText("\n".join(lines))
            self._search_errors.setVisible(True)
        else:
            self._search_errors.setVisible(False)

        self._match_list_container.setVisible(True)

        # Show redact button only if there are matches
        if result.matches:
            self._redact_btn.setVisible(True)
        else:
            self._redact_btn.setVisible(False)

    # ── Step 2: Redact ──

    def _redact(self):
        self._redact_btn.setEnabled(False)
        self._search_btn.setEnabled(False)
        self._progress_bar.setValue(0)
        self._progress_container.setVisible(True)
        self._results_container.setVisible(False)
        self._file_label.setText("")

        self._worker = _BatchWorker(
            self._search_folder, self._search_keywords, self._search_output
        )
        self._worker.progress.connect(self._on_redact_progress)
        self._worker.finished.connect(self._on_redact_finished)
        self._worker.start()

    def _on_redact_progress(self, file_index, total, current_file, match_count):
        if total > 0:
            self._progress_bar.setMaximum(total)
            self._progress_bar.setValue(file_index + 1)
        self._file_label.setText(f"Redacting: {current_file}")

    def _on_redact_finished(self, result):
        self._redact_btn.setEnabled(True)
        self._search_btn.setEnabled(True)
        self._file_label.setText("Done.")
        self._progress_bar.setValue(self._progress_bar.maximum())
        self._worker = None

        self._lbl_redact_matched.findChild(QLabel, "value").setText(str(result.total_matches))
        self._lbl_redacted.findChild(QLabel, "value").setText(str(result.total_matches))

        if result.errors:
            lines = [f"{path}: {msg}" for path, msg in result.errors]
            self._errors_text.setPlainText("\n".join(lines))
            self._errors_text.setVisible(True)
        else:
            self._errors_text.setVisible(False)

        self._results_container.setVisible(True)

        # Pop up a summary message box
        if result.errors:
            icon = QMessageBox.Icon.Warning
            title = "Redaction Complete (with errors)"
            msg = (
                f"Scanned {result.total_files} files ({result.files_with_matches} matched).\n"
                f"{result.total_matches} redactions applied.\n"
                f"{len(result.errors)} file(s) had errors."
            )
        elif result.total_matches == 0:
            icon = QMessageBox.Icon.Information
            title = "No Matches Found"
            msg = f"Scanned {result.total_files} files.\nNo matches found for the given keywords."
        else:
            icon = QMessageBox.Icon.Information
            title = "Redaction Complete"
            msg = (
                f"Scanned {result.total_files} files ({result.files_with_matches} matched).\n"
                f"{result.total_matches} redactions applied."
            )
        box = QMessageBox(icon, title, msg, QMessageBox.StandardButton.Ok, self)
        box.exec()
