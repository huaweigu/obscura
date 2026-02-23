import os
import shutil
from dataclasses import dataclass, field

import fitz

from app.redactor import apply_redactions, mark_for_redaction, save

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif")


@dataclass
class BatchResult:
    total_files: int = 0
    files_with_matches: int = 0
    total_matches: int = 0
    errors: list = field(default_factory=list)  # [(path, error_msg)]


def image_to_pdf(image_path):
    """Convert an image file into a single-page PDF document in memory."""
    img_doc = fitz.open(image_path)
    pdf_bytes = img_doc.convert_to_pdf()
    img_doc.close()
    doc = fitz.open("pdf", pdf_bytes)
    doc._pdf_bytes = pdf_bytes  # prevent GC of the backing buffer
    return doc


def find_files(folder, recursive=True):
    """Walk folder tree and return paths matching *.pdf + IMAGE_EXTENSIONS."""
    supported = (".pdf",) + IMAGE_EXTENSIONS
    results = []
    if recursive:
        for root, _dirs, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(supported):
                    results.append(os.path.join(root, f))
    else:
        for f in os.listdir(folder):
            full = os.path.join(folder, f)
            if os.path.isfile(full) and f.lower().endswith(supported):
                results.append(full)
    results.sort()
    return results


def redact_file(file_path, keyword):
    """Open a file, search all pages for keyword, mark & apply redactions.

    Returns (doc, match_count). The caller is responsible for saving/closing doc.
    """
    is_image = file_path.lower().endswith(IMAGE_EXTENSIONS)
    if is_image:
        doc = image_to_pdf(file_path)
    else:
        doc = fitz.open(file_path)

    match_count = 0

    for page_index in range(len(doc)):
        page = doc[page_index]
        if is_image:
            tp = page.get_textpage_ocr(language="eng", full=True)
            rects = page.search_for(keyword, textpage=tp)
        else:
            rects = page.search_for(keyword)
        if rects:
            match_count += len(rects)
            mark_for_redaction(page, rects)

    if match_count > 0:
        apply_redactions(doc)

    return doc, match_count


def process_folder(folder, keyword, output_folder, progress_callback=None):
    """Batch-redact all supported files in a folder.

    Args:
        folder: Input folder path.
        keyword: Text to redact.
        output_folder: Where to save redacted files.
        progress_callback: Optional callable(file_index, total, current_file, match_count).

    Returns:
        BatchResult with summary statistics.
    """
    files = find_files(folder)
    result = BatchResult(total_files=len(files))

    for i, file_path in enumerate(files):
        rel_path = os.path.relpath(file_path, folder)
        match_count = 0
        try:
            doc, match_count = redact_file(file_path, keyword)

            # Build output path preserving subfolder structure
            out_path = os.path.join(output_folder, rel_path)

            if match_count > 0:
                result.files_with_matches += 1
                result.total_matches += match_count
                # Images become PDFs
                if file_path.lower().endswith(IMAGE_EXTENSIONS):
                    out_path = os.path.splitext(out_path)[0] + ".pdf"
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                save(doc, out_path)
            else:
                # Copy unmatched files as-is
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                shutil.copy2(file_path, out_path)

            doc.close()
        except Exception as e:
            result.errors.append((rel_path, str(e)))

        if progress_callback:
            progress_callback(i, len(files), rel_path, match_count)

    return result
