import os
import re
import shutil
import tempfile
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


def redact_file(file_path, keywords):
    """Open a file, search all pages for keywords, mark & apply redactions.

    Args:
        file_path: Path to a PDF or image file.
        keywords: A string or list of strings to redact.

    Returns (doc, match_count). The caller is responsible for saving/closing doc.
    """
    if isinstance(keywords, str):
        keywords = [keywords]

    is_image = file_path.lower().endswith(IMAGE_EXTENSIONS)
    if is_image:
        doc = image_to_pdf(file_path)
    else:
        doc = fitz.open(file_path)

    match_count = 0

    for page_index in range(len(doc)):
        page = doc[page_index]
        tp = None
        if is_image:
            tp = page.get_textpage_ocr(language="eng", full=True)
        for kw in keywords:
            if tp:
                rects = page.search_for(kw, textpage=tp)
            else:
                rects = page.search_for(kw)
            if rects:
                match_count += len(rects)
                mark_for_redaction(page, rects)

    # Also scrub form field values that contain keywords
    for page_index in range(len(doc)):
        page = doc[page_index]
        for widget in page.widgets():
            val = widget.field_value or ""
            original_val = val
            for kw in keywords:
                if kw.lower() in val.lower():
                    # Replace keyword occurrences (case-insensitive)
                    val = re.sub(re.escape(kw), "█" * len(kw), val, flags=re.IGNORECASE)
            if val != original_val:
                match_count += 1
                widget.field_value = val
                widget.update()

    if match_count > 0:
        apply_redactions(doc)

    return doc, match_count


def process_folder(folder, keywords, output_folder, progress_callback=None):
    """Batch-redact all supported files in a folder.

    Copies the entire input folder to output_folder first (if different),
    then redacts matched files in-place within the output folder.

    Args:
        folder: Input folder path.
        keywords: A string or list of strings to redact.
        output_folder: Where to save redacted files.
        progress_callback: Optional callable(file_index, total, current_file, match_count).

    Returns:
        BatchResult with summary statistics.
    """
    folder = os.path.abspath(folder)
    output_folder = os.path.abspath(output_folder)

    # Step 1: Copy entire folder to output (only if it doesn't have files yet)
    if folder != output_folder:
        if not os.path.exists(output_folder):
            shutil.copytree(folder, output_folder)
        elif not find_files(output_folder):
            # Output exists but is empty — copy into it
            shutil.copytree(folder, output_folder, dirs_exist_ok=True)

    # Step 2: Find files in the output folder and redact in-place
    files = find_files(output_folder)
    result = BatchResult(total_files=len(files))

    for i, file_path in enumerate(files):
        rel_path = os.path.relpath(file_path, output_folder)
        match_count = 0
        try:
            doc, match_count = redact_file(file_path, keywords)

            if match_count > 0:
                result.files_with_matches += 1
                result.total_matches += match_count
                # Save to temp file, then replace original
                fd, tmp = tempfile.mkstemp(
                    suffix=os.path.splitext(file_path)[1],
                    dir=os.path.dirname(file_path),
                )
                os.close(fd)
                if file_path.lower().endswith(IMAGE_EXTENSIONS):
                    pix = doc[0].get_pixmap(dpi=300)
                    pix.save(tmp)
                else:
                    save(doc, tmp)
                doc.close()
                doc = None
                shutil.move(tmp, file_path)

            if doc is not None:
                doc.close()
        except Exception as e:
            result.errors.append((rel_path, str(e)))

        if progress_callback:
            progress_callback(i, len(files), rel_path, match_count)

    return result
