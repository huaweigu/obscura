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
python -m app.main_window
```

## Dependencies

- PySide6
- PyMuPDF
- Pillow
