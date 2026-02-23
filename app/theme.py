APP_STYLE = """
/* ── Global ── */
QMainWindow, QDialog, QWidget {
    background: #1a1a2e;
    color: #e0e0e0;
}

/* ── Menu & Toolbar ── */
QToolBar {
    background: #16213e;
    border: none;
    border-bottom: 2px solid #0f3460;
    padding: 4px 8px;
    spacing: 4px;
}
QToolBar QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 6px 14px;
    color: #e0e0e0;
    font-size: 13px;
    font-weight: bold;
}
QToolBar QToolButton:hover {
    background: #0f3460;
    border-color: #0f3460;
}
QToolBar QToolButton:pressed {
    background: #e94560;
}

/* ── Status Bar ── */
QStatusBar {
    background: #16213e;
    color: #888;
    border-top: 1px solid #0f3460;
    padding: 4px 12px;
    font-size: 12px;
}

/* ── Dock Widget ── */
QDockWidget {
    color: #e0e0e0;
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}
QDockWidget::title {
    background: #16213e;
    border: none;
    border-bottom: 2px solid #e94560;
    padding: 8px 12px;
    font-weight: bold;
    text-align: left;
}

/* ── Inputs ── */
QLineEdit {
    background: #16213e;
    border: 2px solid #0f3460;
    border-radius: 8px;
    padding: 8px 12px;
    color: #e0e0e0;
    font-size: 13px;
    selection-background-color: #e94560;
}
QLineEdit:focus {
    border-color: #e94560;
}

/* ── Buttons ── */
QPushButton {
    background: #0f3460;
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    color: #e0e0e0;
    font-size: 13px;
    font-weight: bold;
}
QPushButton:hover {
    background: #1a4a8a;
}
QPushButton:pressed {
    background: #e94560;
}
QPushButton:disabled {
    background: #2a2a3e;
    color: #555;
}

/* ── Primary Buttons ── */
QPushButton#primary, QPushButton#start {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #e94560, stop:1 #c81e45);
    color: white;
    font-size: 14px;
    padding: 10px 20px;
    border-radius: 10px;
}
QPushButton#primary:hover, QPushButton#start:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #ff5a7a, stop:1 #e94560);
}
QPushButton#primary:disabled, QPushButton#start:disabled {
    background: #333;
    color: #666;
}

/* ── Danger Buttons ── */
QPushButton#danger {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #e94560, stop:1 #c81e45);
    color: white;
}
QPushButton#danger:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #ff5a7a, stop:1 #e94560);
}

/* ── Ghost Buttons ── */
QPushButton#ghost, QPushButton#close {
    background: transparent;
    border: 2px solid #444;
    color: #aaa;
}
QPushButton#ghost:hover, QPushButton#close:hover {
    border-color: #e94560;
    color: #e94560;
}

/* ── Browse Buttons ── */
QPushButton#browse {
    padding: 8px 14px;
    font-size: 12px;
}

/* ── List Widget ── */
QListWidget {
    background: #16213e;
    border: 2px solid #0f3460;
    border-radius: 8px;
    color: #e0e0e0;
    font-size: 12px;
    padding: 4px;
    outline: none;
}
QListWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
}
QListWidget::item:hover {
    background: #0f3460;
}
QListWidget::item:selected {
    background: #e94560;
    color: white;
}

/* ── Scroll Areas ── */
QScrollArea {
    border: none;
    background: #12121f;
}
QScrollArea > QWidget > QWidget {
    background: #12121f;
}

/* ── Scrollbars ── */
QScrollBar:vertical {
    background: #16213e;
    width: 10px;
    border-radius: 5px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #0f3460;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #e94560;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #16213e;
    height: 10px;
    border-radius: 5px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #0f3460;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background: #e94560;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ── Progress Bar ── */
QProgressBar {
    background: #16213e;
    border: none;
    border-radius: 6px;
    text-align: center;
    color: #e0e0e0;
    font-size: 11px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #e94560, stop:1 #ff7eb3);
    border-radius: 6px;
}

/* ── Text Edit ── */
QTextEdit {
    background: #16213e;
    border: 1px solid #333;
    border-radius: 6px;
    color: #e0e0e0;
    font-size: 12px;
    padding: 6px;
}

/* ── Dialog Button Box ── */
QDialogButtonBox QPushButton {
    min-width: 100px;
}

/* ── Labels ── */
QLabel {
    color: #e0e0e0;
}
QLabel#section-label {
    font-size: 11px;
    font-weight: bold;
    color: #e94560;
    letter-spacing: 1px;
}
QLabel#subtitle {
    font-size: 13px;
    color: #888;
}

/* ── Message Boxes ── */
QMessageBox {
    background: #1a1a2e;
}
QMessageBox QLabel {
    color: #e0e0e0;
}
"""
