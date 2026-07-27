from __future__ import annotations

from dataclasses import dataclass, field

import fitz
from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.batch_dialog import BatchDialog
from app.pdf_viewer import PdfViewer
from app.preview_dialog import PreviewDialog
from app.redactor import apply_redactions, mark_for_redaction, save
from app.search_panel import SearchPanel, SearchResult
from app.text_editor import replace_text
from app.thumbnail_panel import ThumbnailPanel
from app.toc_panel import TocPanel

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif")

PANEL_DEFAULT_WIDTH = 260
SETTINGS_ORG = "Obscura"
SETTINGS_APP = "Obscura"


# ── Segmented Control Widget ────────────────────────────────

class SegmentedControl(QWidget):
    """A pill-style segmented control with mutually exclusive buttons."""

    mode_changed = Signal(str)  # emits mode name

    def __init__(self, modes, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self._buttons: dict[str, QPushButton] = {}
        self._active_mode = None

        for i, (key, label) in enumerate(modes):
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setMinimumWidth(56)

            # Corner rounding: left, middle, or right
            if i == 0:
                btn.setProperty("segment", "left")
            elif i == len(modes) - 1:
                btn.setProperty("segment", "right")
            else:
                btn.setProperty("segment", "middle")

            btn.clicked.connect(lambda checked, k=key: self._on_clicked(k))
            layout.addWidget(btn)
            self._buttons[key] = btn

    def _on_clicked(self, mode):
        self.set_active(mode)
        self.mode_changed.emit(mode)

    def set_active(self, mode):
        self._active_mode = mode
        for key, btn in self._buttons.items():
            btn.setChecked(key == mode)

    def active_mode(self):
        return self._active_mode


# ── Welcome Widget ──────────────────────────────────────────

class WelcomeWidget(QWidget):
    """Shown when no documents are open."""

    open_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        title = QLabel("Obscura")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 42px; font-weight: bold; color: #4a9eff;"
            "background: transparent; border: none;"
        )
        layout.addWidget(title)

        subtitle = QLabel("PDF Viewer, Redactor & Editor")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(
            "font-size: 15px; color: #a0a8b8;"
            "background: transparent; border: none;"
        )
        layout.addWidget(subtitle)

        layout.addSpacing(24)

        open_btn = QPushButton("Open File")
        open_btn.setObjectName("primary")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setFixedWidth(180)
        open_btn.clicked.connect(self.open_requested.emit)
        layout.addWidget(open_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(8)

        hint = QLabel("or drag and drop files here")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            "font-size: 12px; color: #666;"
            "background: transparent; border: none;"
        )
        layout.addWidget(hint)

        shortcut_hint = QLabel("Ctrl+O")
        shortcut_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shortcut_hint.setStyleSheet(
            "font-size: 11px; color: #555;"
            "background: transparent; border: none;"
        )
        layout.addWidget(shortcut_hint)


# ── Document State ──────────────────────────────────────────

@dataclass
class DocumentState:
    """Per-document state for a single open tab."""

    viewer: PdfViewer
    doc: fitz.Document | None = None
    file_path: str | None = None
    search_results: list = field(default_factory=list)
    ocr_textpages: dict = field(default_factory=dict)
    is_image_source: bool = False


# ── Main Window ─────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Obscura")
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        self._tab_states: list[DocumentState] = []
        self._connected_viewer: PdfViewer | None = None
        self._mode = "reader"

        # Left dock group state. The panel is a single unit the user opens and
        # closes explicitly; modes only decide which dock inside it is raised.
        self._settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self._panel_act: QAction | None = None
        self._panel_width = PANEL_DEFAULT_WIDTH
        self._raised_dock: QDockWidget | None = None
        self._has_toc = False

        self._setup_central()
        self._setup_thumbnail_panel()
        self._setup_toc_panel()
        self._setup_search_panel()
        self._setup_toolbar()
        self._setup_statusbar()
        self._setup_shortcuts()
        self._restore_panel_settings()

    # ── Properties (delegate to active tab) ───────────────────

    @property
    def _current_state(self) -> DocumentState | None:
        idx = self._tab_widget.currentIndex()
        if 0 <= idx < len(self._tab_states):
            return self._tab_states[idx]
        return None

    @property
    def _viewer(self) -> PdfViewer | None:
        state = self._current_state
        return state.viewer if state else None

    @property
    def _doc(self):
        state = self._current_state
        return state.doc if state else None

    # ── UI Setup ──────────────────────────────────────────────

    def _setup_central(self):
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # Welcome page (index 0)
        self._welcome = WelcomeWidget()
        self._welcome.open_requested.connect(self._open_file)
        self._stack.addWidget(self._welcome)

        # Tab widget (index 1)
        self._tab_widget = QTabWidget()
        self._tab_widget.setTabsClosable(True)
        self._tab_widget.setMovable(True)
        self._tab_widget.setDocumentMode(True)
        self._tab_widget.currentChanged.connect(self._on_tab_changed)
        self._tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        self._stack.addWidget(self._tab_widget)

        # Start on welcome
        self._stack.setCurrentIndex(0)

    def _update_central_view(self):
        """Show welcome when no tabs, show tabs otherwise. Hide tab bar for single tab."""
        count = self._tab_widget.count()
        if count == 0:
            self._stack.setCurrentIndex(0)
        else:
            self._stack.setCurrentIndex(1)
            self._tab_widget.tabBar().setVisible(count > 1)

    def _setup_thumbnail_panel(self):
        self._thumb_panel = ThumbnailPanel()
        self._thumb_dock = QDockWidget("Pages", self)
        self._thumb_dock.setWidget(self._thumb_panel)
        self._thumb_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._thumb_dock)
        self._thumb_dock.setVisible(False)
        self._thumb_panel.page_clicked.connect(self._on_thumbnail_clicked)

    def _setup_toc_panel(self):
        self._toc_panel = TocPanel()
        self._toc_dock = QDockWidget("Bookmarks", self)
        self._toc_dock.setWidget(self._toc_panel)
        self._toc_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._toc_dock)
        self._toc_dock.setVisible(False)
        self._toc_panel.page_requested.connect(self._on_thumbnail_clicked)

    def _setup_search_panel(self):
        self._search_panel = SearchPanel()
        self._search_dock = QDockWidget("Search && Redact", self)
        self._search_dock.setWidget(self._search_panel)
        self._search_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._search_dock)
        self._search_dock.setVisible(False)

        # Tab the left docks together
        self.tabifyDockWidget(self._thumb_dock, self._toc_dock)
        self.tabifyDockWidget(self._toc_dock, self._search_dock)

        self._search_panel.search_requested.connect(self._do_search)
        self._search_panel.result_clicked.connect(self._on_result_clicked)
        self._search_panel.redact_all_requested.connect(self._redact_all)
        self._search_panel.redact_selected_requested.connect(self._redact_selected)

    # ── Left Panel (tabified dock group) ──────────────────────

    def _panel_docks(self):
        return (self._thumb_dock, self._toc_dock, self._search_dock)

    def _is_panel_open(self):
        """True if any left dock is showing.

        Uses isHidden() rather than isVisible() so the answer is meaningful
        before the window is shown on screen.
        """
        return any(not dock.isHidden() for dock in self._panel_docks())

    def _dock_for_mode(self):
        """The dock a given mode wants raised when the panel is open."""
        if self._mode == "redactor":
            return self._search_dock
        return self._thumb_dock

    def _raise_dock(self, dock):
        """Make `dock` the current tab of the panel, if it can be shown."""
        if dock is self._toc_dock and not self._has_toc:
            dock = self._thumb_dock
        self._raised_dock = dock
        if not dock.isHidden():
            dock.raise_()

    def _capture_panel_width(self):
        """Remember the panel's current width so re-opening restores it."""
        if not self._is_panel_open():
            return
        width = self._search_dock.width()
        if width > 0:
            self._panel_width = width

    def _set_panel_open(self, open_, raise_dock=None, remember=True):
        """Show or hide the whole left dock group as one unit."""
        self._capture_panel_width()

        if open_:
            self._thumb_dock.setVisible(True)
            self._toc_dock.setVisible(self._has_toc)
            self._search_dock.setVisible(True)
            self._raise_dock(raise_dock or self._dock_for_mode())
            self.resizeDocks(
                list(self._panel_docks()),
                [self._panel_width] * 3,
                Qt.Orientation.Horizontal,
            )
        else:
            for dock in self._panel_docks():
                dock.setVisible(False)

        if self._panel_act is not None:
            self._panel_act.setChecked(open_)
        if remember:
            self._save_panel_settings()

    def _toggle_panel(self):
        self._set_panel_open(not self._is_panel_open())

    def _focus_search(self):
        """Ctrl+F: open the panel on the Search tab and focus its input."""
        self._set_panel_open(True, raise_dock=self._search_dock)
        self._search_panel.focus_input()

    def _restore_panel_settings(self):
        self._panel_width = int(
            self._settings.value("panel/width", PANEL_DEFAULT_WIDTH)
        )
        if self._panel_width <= 0:
            self._panel_width = PANEL_DEFAULT_WIDTH
        open_ = self._settings.value("panel/open", False, type=bool)
        self._set_panel_open(open_, remember=False)

    def _save_panel_settings(self):
        self._settings.setValue("panel/open", self._is_panel_open())
        self._settings.setValue("panel/width", self._panel_width)

    def closeEvent(self, event):
        self._capture_panel_width()
        self._save_panel_settings()
        super().closeEvent(event)

    def _setup_toolbar(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)

        # ── Group 0: Panel toggle ──
        self._panel_act = QAction("▣", self)  # white square containing square
        self._panel_act.setCheckable(True)
        self._panel_act.setToolTip("Toggle Panel  (Ctrl+\\)")
        # triggered() carries the action's new checked state.
        self._panel_act.triggered.connect(lambda checked: self._set_panel_open(checked))
        tb.addAction(self._panel_act)

        tb.addSeparator()

        # ── Group 1: File operations ──
        open_act = QAction("Open", self)
        open_act.setToolTip("Open File  (Ctrl+O)")
        open_act.setShortcut(QKeySequence.StandardKey.Open)
        open_act.triggered.connect(self._open_file)
        tb.addAction(open_act)

        quick_save_act = QAction("Save", self)
        quick_save_act.setToolTip("Save  (Ctrl+S)")
        quick_save_act.setShortcut(QKeySequence.StandardKey.Save)
        quick_save_act.triggered.connect(self._quick_save)
        tb.addAction(quick_save_act)

        save_as_act = QAction("Save As", self)
        save_as_act.setToolTip("Save As  (Ctrl+Shift+S)")
        save_as_act.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_act.triggered.connect(self._save_file)
        tb.addAction(save_as_act)

        tb.addSeparator()

        # ── Group 2: Zoom controls ──
        zoom_out_act = QAction("\u2212", self)  # minus sign
        zoom_out_act.setToolTip("Zoom Out  (Ctrl+-)")
        zoom_out_act.setShortcut(QKeySequence.StandardKey.ZoomOut)
        zoom_out_act.triggered.connect(self._zoom_out)
        tb.addAction(zoom_out_act)

        self._zoom_combo = QComboBox()
        self._zoom_combo.setEditable(True)
        self._zoom_combo.setFixedWidth(100)
        self._zoom_combo.setObjectName("zoom-combo")
        for preset in ["50%", "75%", "100%", "125%", "150%", "200%", "Fit Width", "Fit Page"]:
            self._zoom_combo.addItem(preset)
        self._zoom_combo.setCurrentText("---")
        self._zoom_combo.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_combo.activated.connect(self._on_zoom_combo_activated)
        self._zoom_combo.lineEdit().returnPressed.connect(self._on_zoom_input)
        tb.addWidget(self._zoom_combo)

        zoom_in_act = QAction("+", self)
        zoom_in_act.setToolTip("Zoom In  (Ctrl++)")
        zoom_in_act.setShortcut(QKeySequence.StandardKey.ZoomIn)
        zoom_in_act.triggered.connect(self._zoom_in)
        tb.addAction(zoom_in_act)

        tb.addSeparator()

        # ── Group 3: Page navigation ──
        prev_act = QAction("\u2039", self)  # single left angle
        prev_act.setToolTip("Previous Page  (Page Up)")
        prev_act.triggered.connect(self._prev_page)
        tb.addAction(prev_act)

        self._page_label = QLabel("0 / 0")
        self._page_label.setObjectName("page-indicator")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setFixedWidth(80)
        tb.addWidget(self._page_label)

        next_act = QAction("\u203a", self)  # single right angle
        next_act.setToolTip("Next Page  (Page Down)")
        next_act.triggered.connect(self._next_page)
        tb.addAction(next_act)

        tb.addSeparator()

        # ── Group 4: Mode switcher ──
        self._mode_switcher = SegmentedControl([
            ("reader", "Read"),
            ("redactor", "Redact"),
            ("editor", "Edit"),
        ])
        self._mode_switcher.mode_changed.connect(self._on_mode_changed)
        self._mode_switcher.set_active("reader")
        tb.addWidget(self._mode_switcher)

        # ── Spacer ──
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        # Without this the global QWidget rule paints it as a stray dark box.
        spacer.setStyleSheet("background: transparent;")
        tb.addWidget(spacer)

        # ── Batch (right-aligned, secondary) ──
        batch_act = QAction("Batch", self)
        batch_act.setToolTip("Batch Redact")
        batch_act.triggered.connect(self._open_batch_dialog)
        tb.addAction(batch_act)

    def _setup_statusbar(self):
        self._status_file = ""
        self._status_page = ""
        self._status_mode = ""
        self.statusBar().showMessage("No file loaded")

    def _setup_shortcuts(self):
        # Copy text selection
        copy_act = QAction("Copy", self)
        copy_act.setShortcut(QKeySequence.StandardKey.Copy)
        copy_act.triggered.connect(self._copy_text)
        self.addAction(copy_act)

        # Page navigation shortcuts
        QShortcut(QKeySequence.StandardKey.MoveToPreviousPage, self, self._prev_page)
        QShortcut(QKeySequence.StandardKey.MoveToNextPage, self, self._next_page)
        QShortcut(QKeySequence("Home"), self, self._first_page)
        QShortcut(QKeySequence("End"), self, self._last_page)

        # Mode shortcuts
        QShortcut(QKeySequence("Ctrl+M"), self, lambda: self._switch_mode("redactor"))
        QShortcut(QKeySequence("Ctrl+E"), self, lambda: self._switch_mode("editor"))

        # Panel shortcuts
        QShortcut(QKeySequence("Ctrl+\\"), self, self._toggle_panel)
        QShortcut(QKeySequence.StandardKey.Find, self, self._focus_search)

    def _switch_mode(self, mode):
        self._mode_switcher.set_active(mode)
        self._on_mode_changed(mode)

    def _update_status(self):
        parts = []
        if self._status_file:
            parts.append(self._status_file)
        if self._status_page:
            parts.append(self._status_page)
        if self._status_mode:
            parts.append(self._status_mode)
        self.statusBar().showMessage("  |  ".join(parts) if parts else "No file loaded")

    # ── Tab Management ────────────────────────────────────────

    def _on_tab_changed(self, index):
        """Called when the active tab changes."""
        # Disconnect signals from the old viewer
        if self._connected_viewer is not None:
            try:
                self._connected_viewer.page_changed.disconnect(self._on_page_changed)
                self._connected_viewer.zoom_changed.disconnect(self._on_zoom_changed)
                self._connected_viewer.text_edit_committed.disconnect(self._on_text_edit_committed)
            except RuntimeError:
                pass

        state = self._current_state
        if state is None:
            self._connected_viewer = None
            self._thumb_panel.load_document(None)
            self._toc_panel.load_toc(None)
            self._has_toc = False
            if self._is_panel_open():
                self._toc_dock.setVisible(False)
            self._search_panel.clear_results()
            self._page_label.setText("0 / 0")
            self._zoom_combo.setCurrentText("---")
            self._status_file = ""
            self._status_page = ""
            self._update_status()
            self._update_central_view()
            return

        viewer = state.viewer

        # Connect signals from the new viewer
        viewer.page_changed.connect(self._on_page_changed)
        viewer.zoom_changed.connect(self._on_zoom_changed)
        viewer.text_edit_committed.connect(self._on_text_edit_committed)
        self._connected_viewer = viewer

        # Update toolbar indicators
        if state.doc:
            total = len(state.doc)
            current_page = viewer.current_page()
            self._page_label.setText(f"{current_page} / {total}")
            self._zoom_combo.setCurrentText(f"{int(viewer.zoom * 100)}%")
            self._status_file = f"File: {state.file_path.split('/')[-1]}"
            self._status_page = f"Page {current_page} / {total}"
            self._update_status()
        else:
            self._page_label.setText("0 / 0")
            self._zoom_combo.setCurrentText("---")

        # Reload shared panels
        self._thumb_panel.load_document(state.doc)
        self._has_toc = self._toc_panel.load_toc(state.doc)
        # Bookmarks only exists as a tab for documents that have an outline.
        if self._is_panel_open():
            self._toc_dock.setVisible(self._has_toc)
            if self._raised_dock is self._toc_dock and not self._has_toc:
                self._raise_dock(self._thumb_dock)

        # Sync viewer mode with current app mode
        if self._mode == "editor":
            viewer.set_editor_mode_enabled(True)
            viewer.set_text_selection_enabled(False)
        elif self._mode == "reader":
            viewer.set_editor_mode_enabled(False)
            viewer.set_text_selection_enabled(True)
        else:
            viewer.set_editor_mode_enabled(False)
            viewer.set_text_selection_enabled(False)

        # Restore search results for this tab
        if state.search_results:
            self._search_panel.set_results(state.search_results)
        else:
            self._search_panel.clear_results()

        self._update_central_view()

    def _on_tab_close_requested(self, index):
        """Handle tab close button click."""
        if index < 0 or index >= len(self._tab_states):
            return

        state = self._tab_states.pop(index)

        # Disconnect if this was the connected viewer
        if self._connected_viewer is state.viewer:
            try:
                state.viewer.page_changed.disconnect(self._on_page_changed)
                state.viewer.zoom_changed.disconnect(self._on_zoom_changed)
                state.viewer.text_edit_committed.disconnect(self._on_text_edit_committed)
            except RuntimeError:
                pass
            self._connected_viewer = None

        if state.doc:
            state.doc.close()

        self._tab_widget.removeTab(index)
        self._update_central_view()

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
        self._open_file_by_path(path)

    def _open_file_by_path(self, path):
        """Open a file in a new tab, or switch to it if already open."""
        # Check if already open
        for i, state in enumerate(self._tab_states):
            if state.file_path == path:
                self._tab_widget.setCurrentIndex(i)
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

        viewer = PdfViewer()
        viewer.set_text_selection_enabled(self._mode == "reader")
        viewer.set_editor_mode_enabled(self._mode == "editor")
        viewer.load_document(doc)

        state = DocumentState(
            viewer=viewer,
            doc=doc,
            file_path=path,
            is_image_source=is_image,
        )
        self._tab_states.append(state)

        filename = path.split("/")[-1]
        tab_index = self._tab_widget.addTab(viewer, filename)
        self._tab_widget.setCurrentIndex(tab_index)
        self._update_central_view()

    @staticmethod
    def _image_to_pdf(image_path):
        """Convert an image file into a single-page PDF document in memory."""
        img_doc = fitz.open(image_path)
        pdf_bytes = img_doc.convert_to_pdf()
        img_doc.close()
        return fitz.open("pdf", pdf_bytes)

    def _quick_save(self):
        """Save to the original file path. Falls back to Save As for image sources."""
        state = self._current_state
        if not state or not state.doc:
            return
        if not state.file_path or state.is_image_source:
            self._save_file()
            return
        try:
            state.doc.saveIncr()
        except Exception:
            # Incremental save fails on repaired files — do full save via temp file
            try:
                import os
                import tempfile
                fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=os.path.dirname(state.file_path))
                os.close(fd)
                state.doc.save(tmp, garbage=4, deflate=True)
                state.doc.close()
                os.replace(tmp, state.file_path)
                state.doc = fitz.open(state.file_path)
                state.viewer.load_document(state.doc)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save PDF:\n{e}")
                return
        self.statusBar().showMessage(f"Saved to {state.file_path.split('/')[-1]}", 3000)

    def _save_file(self):
        if not self._doc:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF", "", "PDF Files (*.pdf)"
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            save(self._doc, path)
            self.statusBar().showMessage(f"Saved to {path.split('/')[-1]}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save PDF:\n{e}")

    def _open_batch_dialog(self):
        dialog = BatchDialog(self)
        dialog.exec()

    # ── Drag and Drop ─────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                self._open_file_by_path(path)

    # ── Page Navigation ───────────────────────────────────────

    def _prev_page(self):
        if not self._viewer:
            return
        current = self._viewer.current_page()  # 1-based
        if current > 1:
            self._viewer.scroll_to_page(current - 2)

    def _next_page(self):
        if not self._viewer:
            return
        current = self._viewer.current_page()
        if current < self._viewer.page_count:
            self._viewer.scroll_to_page(current)

    def _first_page(self):
        if not self._viewer:
            return
        if self._viewer.page_count > 0:
            self._viewer.scroll_to_page(0)

    def _last_page(self):
        if not self._viewer:
            return
        if self._viewer.page_count > 0:
            self._viewer.scroll_to_page(self._viewer.page_count - 1)

    def _goto_page(self, page_num):
        if not self._viewer:
            return
        if 1 <= page_num <= self._viewer.page_count:
            self._viewer.scroll_to_page(page_num - 1)

    def _zoom_in(self):
        if self._viewer:
            self._viewer.zoom_in()

    def _zoom_out(self):
        if self._viewer:
            self._viewer.zoom_out()

    def _fit_width(self):
        if self._viewer:
            self._viewer.fit_width()

    def _fit_page(self):
        if self._viewer:
            self._viewer.fit_page()

    def _on_thumbnail_clicked(self, page_index):
        if self._viewer:
            self._viewer.scroll_to_page(page_index)

    # ── Text Selection ────────────────────────────────────────

    def _copy_text(self):
        if self._viewer:
            self._viewer.copy_selected_text()

    # ── Mode Toggle ───────────────────────────────────────────

    def _on_mode_changed(self, mode):
        if mode == "reader":
            self._activate_reader_mode()
        elif mode == "redactor":
            self._activate_redactor_mode()
        elif mode == "editor":
            self._activate_editor_mode()

    # Modes set interaction state and pick which dock is raised. They do NOT
    # open or close the panel — that stays under the user's control via the
    # toolbar toggle / Ctrl+\ — with one exception, noted in Redact below.

    def _activate_reader_mode(self):
        self._mode = "reader"
        self.setWindowTitle("Obscura")
        self._status_mode = "Read"
        self._raise_dock(self._thumb_dock)
        # Enable text selection, disable editor
        if self._viewer:
            self._viewer.set_text_selection_enabled(True)
            self._viewer.set_editor_mode_enabled(False)
        self._update_status()

    def _activate_redactor_mode(self):
        self._mode = "redactor"
        self.setWindowTitle("Obscura — Redact")
        self._status_mode = "Redact"
        # Redact is the one mode that force-opens the panel: the search input
        # is its only entry point, so the mode is unusable without it. The
        # user can collapse it again and that choice is what persists.
        self._set_panel_open(True, raise_dock=self._search_dock)
        # Disable text selection and editor
        if self._viewer:
            self._viewer.set_text_selection_enabled(False)
            self._viewer.clear_selection()
            self._viewer.set_editor_mode_enabled(False)
        self._update_status()

    def _activate_editor_mode(self):
        self._mode = "editor"
        self.setWindowTitle("Obscura — Edit")
        self._status_mode = "Edit"
        self._raise_dock(self._thumb_dock)
        # Disable text selection, enable editor
        if self._viewer:
            self._viewer.set_text_selection_enabled(False)
            self._viewer.clear_selection()
            self._viewer.set_editor_mode_enabled(True)
        self._update_status()

    # ── Zoom ──────────────────────────────────────────────────

    def _on_zoom_changed(self, zoom):
        self._zoom_combo.setCurrentText(f"{int(zoom * 100)}%")

    def _on_zoom_combo_activated(self, index):
        """Handle selecting a zoom preset from the dropdown."""
        text = self._zoom_combo.currentText().strip()
        if text == "Fit Width":
            self._fit_width()
        elif text == "Fit Page":
            self._fit_page()
        else:
            self._apply_zoom_text(text)

    def _on_zoom_input(self):
        """Handle user typing a zoom percentage and pressing Enter."""
        text = self._zoom_combo.currentText().strip()
        if text == "Fit Width":
            self._fit_width()
        elif text == "Fit Page":
            self._fit_page()
        else:
            self._apply_zoom_text(text)
        self._zoom_combo.lineEdit().clearFocus()

    def _apply_zoom_text(self, text):
        text = text.rstrip("%").strip()
        try:
            pct = float(text)
        except ValueError:
            if self._viewer:
                self._zoom_combo.setCurrentText(f"{int(self._viewer.zoom * 100)}%")
            return
        if self._viewer:
            self._viewer.set_zoom(pct / 100.0)

    # ── Search ────────────────────────────────────────────────

    def _do_search(self, keyword):
        state = self._current_state
        if not state or not state.doc:
            return

        doc = state.doc

        # Run OCR on image-sourced docs if not already cached
        if state.is_image_source and not state.ocr_textpages:
            self.statusBar().showMessage("Running OCR…")
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            for i in range(len(doc)):
                page = doc[i]
                state.ocr_textpages[i] = page.get_textpage_ocr(
                    language="eng", full=True
                )
            self._update_status()

        results = []
        highlights = {}
        for page_index in range(len(doc)):
            page = doc[page_index]
            tp = state.ocr_textpages.get(page_index)
            if tp:
                matches = page.search_for(keyword, textpage=tp)
            else:
                matches = page.search_for(keyword)
            for occurrence, rect in enumerate(matches):
                snippet = self._extract_snippet(page, keyword, occurrence, tp)
                results.append(SearchResult(page_index, rect, snippet))
                highlights.setdefault(page_index, []).append(rect)

        state.search_results = results
        self._search_panel.set_results(results)
        state.viewer.set_highlights(highlights)

    def _extract_snippet(
        self, page, keyword, occurrence, textpage=None, context_chars=30
    ):
        """Text surrounding the Nth occurrence of `keyword` on this page.

        search_for() returns matches in reading order and str.find walks the
        extracted text in that same order, so the Nth rect corresponds to the
        Nth occurrence. Without the index every match on a page produced the
        same snippet, which made the results list useless for choosing which
        occurrence to redact.
        """
        if textpage:
            text = page.get_text("text", textpage=textpage)
        else:
            text = page.get_text("text")

        needle = keyword.lower()
        haystack = text.lower()
        idx = -1
        for _ in range(occurrence + 1):
            idx = haystack.find(needle, idx + 1)
            if idx == -1:
                # Fewer text occurrences than rects — possible when the text
                # layer differs from what search_for matched (ligatures, odd
                # encodings). Fall back rather than mislabel the row.
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
        if self._viewer:
            self._viewer.set_active_highlight(page_index, rect)
            self._viewer.scroll_to_page(page_index)

    def _on_page_changed(self, page_num):
        state = self._current_state
        if state and state.doc:
            total = len(state.doc)
            self._status_page = f"Page {page_num} / {total}"
            self._update_status()
            # Sync thumbnail panel
            self._thumb_panel.set_current_page(page_num - 1)
            # Sync page indicator
            self._page_label.setText(f"{page_num} / {total}")

    # ── Redaction ─────────────────────────────────────────────

    def _redact_all(self):
        state = self._current_state
        if not state or not state.search_results or not state.doc:
            return
        self._do_redaction(state.search_results)

    def _redact_selected(self, selected_results):
        if not selected_results or not self._doc:
            return
        self._do_redaction(selected_results)

    def _do_redaction(self, results):
        """Mark redaction annotations, show preview, and apply if confirmed."""
        state = self._current_state
        if not state or not state.doc:
            return
        doc = state.doc
        viewer = state.viewer

        # Group by page
        by_page = {}
        for r in results:
            by_page.setdefault(r.page_index, []).append(r.rect)

        # Mark annotations
        for page_index, rects in by_page.items():
            page = doc[page_index]
            mark_for_redaction(page, rects)

        # Show preview dialog
        dialog = PreviewDialog(doc, self)
        if dialog.exec() == PreviewDialog.DialogCode.Accepted:
            # Apply redactions permanently
            apply_redactions(doc)
            state.search_results.clear()
            self._search_panel.clear_results()
            viewer.clear_highlights()
            viewer.refresh()
            # Refresh thumbnails after redaction
            self._thumb_panel.load_document(doc)
            QMessageBox.information(
                self,
                "Redaction Applied",
                "Text has been permanently redacted.\n"
                "Use 'Save As' to save the redacted PDF.",
            )
        else:
            # Remove unapplied redaction annotations
            for page_index in by_page:
                page = doc[page_index]
                annot = page.first_annot
                while annot:
                    next_annot = annot.next
                    if annot.type[0] == fitz.PDF_ANNOT_REDACT:
                        page.delete_annot(annot)
                    annot = next_annot

    # ── Text Editing ─────────────────────────────────────────

    def _on_text_edit_committed(self, page_index, span, new_text):
        """Handle an in-place edit commit from the viewer."""
        state = self._current_state
        if not state or not state.doc:
            return

        page = state.doc[page_index]

        replace_text(
            page,
            span["bbox"],
            span["text"],
            new_text,
            span["font"],
            span["size"],
            span["color"],
            origin=span["origin"],
        )

        # Refresh viewer and thumbnails
        state.viewer.refresh()
        self._thumb_panel.load_document(state.doc)
        self.statusBar().showMessage("Text edited", 3000)
