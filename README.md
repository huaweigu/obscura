# Obscura

A desktop application for searching, redacting, and editing text in PDF and image files.

## Features

- **PDF Viewer** — Multi-tab PDF viewing with thumbnails and table of contents
- **Search & Redact** — Find text across pages and redact matches with a single click
- **Batch Redaction** — Redact multiple keywords across an entire folder of files
- **Image Support** — OCR-based search and redaction for JPG/JPEG/PNG/BMP/TIFF
- **Text Editing** — Find and replace text in PDFs
- **Dark Theme** — Modern dark UI

## Requirements

- Python 3.10+
- Tesseract OCR (for image support)

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
python run.py              # launch the app
python run.py report.pdf   # open a file straight away
```

`run.py` is the entry point: it locates the Tesseract data directory and
handles macOS "Open With" events. `app/main_window.py` is a module, not a
script — running it directly does nothing.

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Open a file |
| `Ctrl+S` / `Ctrl+Shift+S` | Save / Save As |
| `Ctrl+\` | Show or hide the side panel |
| `Ctrl+F` | Open the panel on Search and focus the input |
| `Ctrl+M` / `Ctrl+E` | Redact mode / Edit mode |
| `Ctrl++` / `Ctrl+-` | Zoom in / out |
| `Page Up` / `Page Down` / `Home` / `End` | Navigate pages |

The side panel (Pages, Bookmarks, Search & Redact) starts collapsed so the
document gets the full window, and remembers whether you left it open.
Documents open fitted to the window width; typing a zoom percentage leaves
fit mode.

## Tests

```bash
python -m pytest        # unit + end-to-end
python -m ruff check .  # lint
```

## Dependencies

- PySide6
- PyMuPDF
- Pillow
