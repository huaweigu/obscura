import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field

import fitz
from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # no limit — local desktop app, user's own files

from app.redactor import apply_redactions, mark_for_redaction, save

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif")


@dataclass
class SearchResult:
    total_files: int = 0
    matches: list = field(default_factory=list)  # [(rel_path, count)]
    errors: list = field(default_factory=list)  # [(rel_path, error_msg)]


@dataclass
class BatchResult:
    total_files: int = 0
    files_with_matches: int = 0
    total_matches: int = 0
    errors: list = field(default_factory=list)  # [(path, error_msg)]


@dataclass
class ShrinkResult:
    total_files: int = 0
    processed: int = 0
    original_bytes: int = 0
    new_bytes: int = 0
    errors: list = field(default_factory=list)  # [(rel_path, error_msg)]


def find_image_files(folder, recursive=True):
    """Walk folder tree and return paths matching IMAGE_EXTENSIONS only."""
    results = []
    if recursive:
        for root, _dirs, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(IMAGE_EXTENSIONS):
                    results.append(os.path.join(root, f))
    else:
        for f in os.listdir(folder):
            full = os.path.join(folder, f)
            if os.path.isfile(full) and f.lower().endswith(IMAGE_EXTENSIONS):
                results.append(full)
    results.sort()
    return results


def shrink_images(folder, output_folder, max_dimension=1920, jpeg_quality=80,
                  progress_callback=None):
    """Resize and recompress images in a folder.

    Args:
        folder: Input folder path.
        output_folder: Where to save compressed images.
        max_dimension: Max pixels on the longest side. Images smaller than
            this are only recompressed, not upscaled.
        jpeg_quality: JPEG save quality (1-100).
        progress_callback: Optional callable(file_index, total, current_file, saved_bytes).

    Returns:
        ShrinkResult with summary statistics.
    """
    folder = os.path.abspath(folder)
    output_folder = os.path.abspath(output_folder)
    os.makedirs(output_folder, exist_ok=True)

    # Copy full folder structure first (non-image files preserved as-is)
    if folder != output_folder:
        shutil.copytree(folder, output_folder, dirs_exist_ok=True)

    image_files = find_image_files(output_folder)
    result = ShrinkResult(total_files=len(image_files))

    for i, file_path in enumerate(image_files):
        rel_path = os.path.relpath(file_path, output_folder)
        saved_bytes = 0
        try:
            original_size = os.path.getsize(file_path)
            result.original_bytes += original_size

            img = Image.open(file_path)
            # Preserve EXIF orientation
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)

            # Resize if larger than max_dimension (never upscale)
            if max(img.width, img.height) > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

            # Save to temp file then replace
            ext = os.path.splitext(file_path)[1].lower()
            fd, tmp = tempfile.mkstemp(suffix=ext, dir=os.path.dirname(file_path))
            os.close(fd)

            if ext in (".jpg", ".jpeg"):
                # Convert RGBA to RGB for JPEG
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(tmp, format="JPEG", quality=jpeg_quality, optimize=True)
            elif ext == ".png":
                img.save(tmp, format="PNG", optimize=True)
            elif ext in (".tiff", ".tif"):
                img.save(tmp, format="TIFF")
            elif ext == ".bmp":
                # Convert BMP to PNG for better compression
                tmp_png = tmp.rsplit(".", 1)[0] + ".png"
                img.save(tmp_png, format="PNG", optimize=True)
                os.remove(tmp)
                tmp = tmp_png
                # Also rename the output file
                new_path = file_path.rsplit(".", 1)[0] + ".png"
                shutil.move(tmp, new_path)
                os.remove(file_path)
                new_size = os.path.getsize(new_path)
                result.new_bytes += new_size
                saved_bytes = original_size - new_size
                result.processed += 1
                if progress_callback:
                    progress_callback(i, len(image_files), rel_path, saved_bytes)
                continue

            shutil.move(tmp, file_path)
            new_size = os.path.getsize(file_path)
            result.new_bytes += new_size
            saved_bytes = original_size - new_size
            result.processed += 1
        except Exception as e:
            result.errors.append((rel_path, str(e)))

        if progress_callback:
            progress_callback(i, len(image_files), rel_path, saved_bytes)

    return result


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


def search_file(file_path, keywords):
    """Search a file for keywords without applying any redactions.

    Returns match_count (int).
    """
    if isinstance(keywords, str):
        keywords = [keywords]

    is_image = file_path.lower().endswith(IMAGE_EXTENSIONS)
    if is_image:
        doc = image_to_pdf(file_path)
    else:
        doc = fitz.open(file_path)

    match_count = 0
    try:
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
                match_count += len(rects)

        # Also check form field values
        for page_index in range(len(doc)):
            page = doc[page_index]
            for widget in page.widgets():
                val = widget.field_value or ""
                for kw in keywords:
                    if kw.lower() in val.lower():
                        match_count += len(re.findall(re.escape(kw), val, flags=re.IGNORECASE))
    finally:
        doc.close()

    return match_count


def search_folder(folder, keywords, progress_callback=None):
    """Search all supported files in a folder for keywords (no redaction).

    Args:
        folder: Folder path to search.
        keywords: A string or list of strings to search for.
        progress_callback: Optional callable(file_index, total, current_file, match_count).

    Returns:
        SearchResult with matched files and counts.
    """
    folder = os.path.abspath(folder)
    files = find_files(folder)
    result = SearchResult(total_files=len(files))

    if isinstance(keywords, str):
        keywords = [keywords]

    for i, file_path in enumerate(files):
        rel_path = os.path.relpath(file_path, folder)
        match_count = 0
        try:
            match_count = search_file(file_path, keywords)
            if match_count > 0:
                result.matches.append((rel_path, match_count))
        except Exception as e:
            result.errors.append((rel_path, str(e)))

        if progress_callback:
            progress_callback(i, len(files), rel_path, match_count)

    return result


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


def process_folder(folder, keywords, output_folder, matched_rel_paths=None,
                    progress_callback=None):
    """Batch-redact files in a folder.

    Copies the entire input folder to output_folder first (if different),
    then redacts files in-place within the output folder.

    Args:
        folder: Input folder path.
        keywords: A string or list of strings to redact.
        output_folder: Where to save redacted files.
        matched_rel_paths: If provided, only redact these files (relative
            paths from the search step). Skips re-scanning unmatched files.
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

    # Step 2: Determine which files to redact
    if matched_rel_paths is not None:
        files = [os.path.join(output_folder, rp) for rp in matched_rel_paths]
    else:
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
