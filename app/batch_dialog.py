import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from app.batch_processor import process_folder


class _BatchWorker(QThread):
    """Worker thread that runs batch redaction."""

    progress = Signal(int, int, str, int)  # file_index, total, current_file, match_count
    finished = Signal(object)  # BatchResult

    def __init__(self, folder, keyword, output_folder):
        super().__init__()
        self._folder = folder
        self._keyword = keyword
        self._output_folder = output_folder

    def run(self):
        result = process_folder(
            self._folder,
            self._keyword,
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
        self.setMinimumWidth(500)
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Input folder
        layout.addWidget(QLabel("Input Folder:"))
        row = QHBoxLayout()
        self._input_edit = QLineEdit()
        self._input_edit.setPlaceholderText("Select folder containing PDFs/images…")
        row.addWidget(self._input_edit)
        browse_in = QPushButton("Browse…")
        browse_in.clicked.connect(self._browse_input)
        row.addWidget(browse_in)
        layout.addLayout(row)

        # Output folder
        layout.addWidget(QLabel("Output Folder:"))
        row = QHBoxLayout()
        self._output_edit = QLineEdit()
        self._output_edit.setPlaceholderText("Defaults to <input folder>/redacted")
        row.addWidget(self._output_edit)
        browse_out = QPushButton("Browse…")
        browse_out.clicked.connect(self._browse_output)
        row.addWidget(browse_out)
        layout.addLayout(row)

        # Keyword
        layout.addWidget(QLabel("Keyword to Redact:"))
        self._keyword_edit = QLineEdit()
        self._keyword_edit.setPlaceholderText("Enter text to redact…")
        layout.addWidget(self._keyword_edit)

        # Start button
        self._start_btn = QPushButton("Start")
        self._start_btn.clicked.connect(self._start)
        layout.addWidget(self._start_btn)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        # Current file label
        self._file_label = QLabel("")
        self._file_label.setVisible(False)
        layout.addWidget(self._file_label)

        # Results / errors
        self._results_text = QTextEdit()
        self._results_text.setReadOnly(True)
        self._results_text.setVisible(False)
        self._results_text.setMaximumHeight(200)
        layout.addWidget(self._results_text)

        # Close button
        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.accept)
        layout.addWidget(self._close_btn)

    def _update_default_output(self):
        folder = self._input_edit.text().strip()
        if folder and not self._output_edit.text().strip():
            self._output_edit.setText(os.path.join(os.path.dirname(folder), "redacted"))

    def _browse_input(self):
        path = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if path:
            self._input_edit.setText(path)
            self._update_default_output()

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if path:
            self._output_edit.setText(path)

    def _start(self):
        folder = self._input_edit.text().strip()
        output = self._output_edit.text().strip()
        keyword = self._keyword_edit.text().strip()

        if not folder:
            QMessageBox.warning(self, "Missing Input", "Please select an input folder.")
            return
        if not output:
            output = os.path.join(os.path.dirname(folder), "redacted")
            self._output_edit.setText(output)
        if not keyword:
            QMessageBox.warning(self, "Missing Keyword", "Please enter a keyword to redact.")
            return

        self._start_btn.setEnabled(False)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._file_label.setVisible(True)
        self._results_text.setVisible(False)

        self._worker = _BatchWorker(folder, keyword, output)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, file_index, total, current_file, match_count):
        if total > 0:
            self._progress_bar.setMaximum(total)
            self._progress_bar.setValue(file_index + 1)
        self._file_label.setText(f"Processing: {current_file}")

    def _on_finished(self, result):
        self._start_btn.setEnabled(True)
        self._file_label.setText("Done.")
        self._progress_bar.setValue(self._progress_bar.maximum())

        lines = [
            f"Files scanned: {result.total_files}",
            f"Files with matches: {result.files_with_matches}",
            f"Total matches redacted: {result.total_matches}",
        ]
        if result.errors:
            lines.append(f"\nErrors ({len(result.errors)}):")
            for path, msg in result.errors:
                lines.append(f"  {path}: {msg}")

        self._results_text.setPlainText("\n".join(lines))
        self._results_text.setVisible(True)
        self._worker = None
