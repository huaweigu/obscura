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
    background: #4a9eff;
}
QToolBar::separator {
    background: #0f3460;
    width: 1px;
    margin: 4px 8px;
}

/* ── Status Bar ── */
QStatusBar {
    background: #16213e;
    color: #a0a8b8;
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
    border-bottom: 1px solid #0f3460;
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
    selection-background-color: #4a9eff;
}
QLineEdit:focus {
    border-color: #4a9eff;
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
    background: #1c2d52;
}
QPushButton:disabled {
    background: #2a2a3e;
    color: #555;
}

/* ── Primary Buttons ── */
QPushButton#primary, QPushButton#start {
    background: #4a9eff;
    color: white;
    font-size: 14px;
    padding: 10px 20px;
    border-radius: 10px;
}
QPushButton#primary:hover, QPushButton#start:hover {
    background: #6bb3ff;
}
QPushButton#primary:disabled, QPushButton#start:disabled {
    background: #333;
    color: #666;
}

/* ── Danger Buttons ── */
QPushButton#danger {
    background: #e94560;
    color: white;
}
QPushButton#danger:hover {
    background: #ff5a7a;
}

/* ── Ghost Buttons ── */
QPushButton#ghost, QPushButton#close {
    background: transparent;
    border: 2px solid #444;
    color: #aaa;
}
QPushButton#ghost:hover, QPushButton#close:hover {
    border-color: #a0a8b8;
    color: #a0a8b8;
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
    border-left: 3px solid transparent;
}
QListWidget::item:hover {
    background: #0f3460;
}
QListWidget::item:selected {
    background: rgba(74, 158, 255, 0.2);
    border-left: 3px solid #4a9eff;
    color: #e0e0e0;
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
    background: #4a9eff;
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
    background: #4a9eff;
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
    background: #4a9eff;
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
    font-weight: 600;
    color: #a0a8b8;
    letter-spacing: 1px;
}
QLabel#subtitle {
    font-size: 13px;
    color: #a0a8b8;
}

/* ── Spin Box ── */
QSpinBox {
    background: #16213e;
    border: 2px solid #0f3460;
    border-radius: 8px;
    padding: 4px 8px;
    color: #e0e0e0;
    font-size: 13px;
}
QSpinBox:focus {
    border-color: #4a9eff;
}
QSpinBox::up-button, QSpinBox::down-button {
    width: 0;
    border: none;
}

/* ── Tree Widget ── */
QTreeWidget {
    background: #16213e;
    border: 2px solid #0f3460;
    border-radius: 8px;
    color: #e0e0e0;
    font-size: 12px;
    padding: 4px;
    outline: none;
}
QTreeWidget::item {
    padding: 4px 8px;
    border-radius: 4px;
    border-left: 3px solid transparent;
}
QTreeWidget::item:hover {
    background: #0f3460;
}
QTreeWidget::item:selected {
    background: rgba(74, 158, 255, 0.2);
    border-left: 3px solid #4a9eff;
    color: #e0e0e0;
}
QTreeWidget::branch {
    background: transparent;
}

/* ── Tab Bar (Dock Tabs) ── */
QTabBar::tab {
    background: #16213e;
    color: #a0a8b8;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background: #1c2d52;
    color: #e0e0e0;
    border-bottom: 2px solid #4a9eff;
}
QTabBar::tab:hover:!selected {
    color: #e0e0e0;
    background: rgba(74, 158, 255, 0.1);
}

/* ── Document Tab Widget ── */
QTabWidget::pane {
    border: none;
    background: #12121f;
}
QTabWidget > QTabBar::tab {
    background: #16213e;
    color: #a0a8b8;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 18px;
    font-size: 12px;
    font-weight: bold;
    min-width: 80px;
}
QTabWidget > QTabBar::tab:selected {
    background: #1c2d52;
    color: #e0e0e0;
    border-bottom: 2px solid #4a9eff;
}
QTabWidget > QTabBar::tab:hover:!selected {
    color: #e0e0e0;
    background: rgba(74, 158, 255, 0.1);
}

/* ── Message Boxes ── */
QMessageBox {
    background: #1a1a2e;
}
QMessageBox QLabel {
    color: #e0e0e0;
}
"""
