"""Core logic for PDF text editing: span identification, text replacement, and annotations."""

import fitz

# ── Font Mapping ─────────────────────────────────────────────

FONT_MAP = {
    "helv": "helv",
    "helvetica": "helv",
    "arial": "helv",
    "tiro": "tiro",
    "times": "tiro",
    "timesnewroman": "tiro",
    "cour": "cour",
    "courier": "cour",
    "couriernew": "cour",
    "symb": "symb",
    "symbol": "symb",
    "zadb": "zadb",
    "zapfdingbats": "zadb",
}


def map_font(font_name):
    """Map a PDF font name to a Base-14 fontname for insertion."""
    key = font_name.lower().replace("-", "").replace(" ", "")
    for pattern, base14 in FONT_MAP.items():
        if pattern in key:
            return base14
    return "helv"  # safe default


def int_to_rgb(color_int):
    """Convert integer color from get_text('dict') to (r, g, b) floats 0-1."""
    r = ((color_int >> 16) & 0xFF) / 255
    g = ((color_int >> 8) & 0xFF) / 255
    b = (color_int & 0xFF) / 255
    return (r, g, b)


# ── Font Extraction ──────────────────────────────────────────

def _extract_page_font(page, font_name):
    """Try to extract the embedded font matching font_name from the page.

    Returns a writable fitz.Font if the font is embedded and usable, else None.
    """
    doc = page.parent
    if doc is None:
        return None

    for xref, _ext, _ftype, basefont, name, _encoding in page.get_fonts():
        if xref == 0:
            continue
        if basefont != font_name and name != font_name:
            # Fuzzy: strip subset prefix (e.g. "ABCDEF+ArialMT" -> "ArialMT")
            clean_base = basefont.split("+", 1)[-1] if "+" in basefont else basefont
            if clean_base != font_name:
                continue
        try:
            _basename, _ext, _subtype, buffer = doc.extract_font(xref)
        except Exception:
            continue
        if not buffer:
            continue
        try:
            font = fitz.Font(fontbuffer=buffer)
            if font.is_writable:
                return font
        except Exception:
            continue
    return None


def _font_has_glyphs(font, text):
    """Check that the font has glyphs for every character in text."""
    return all(font.has_glyph(ord(ch)) for ch in text)


# ── Span Identification ─────────────────────────────────────

def get_span_at_point(page, point):
    """Return the text span dict at a given PDF point, or None.

    Uses page.get_text("dict") to walk blocks -> lines -> spans and checks
    if the point falls inside each span's bbox.

    Returns a dict with keys: text, font, size, color, flags, bbox, origin.
    """
    data = page.get_text("dict")
    px, py = point.x, point.y

    for block in data.get("blocks", []):
        if block.get("type") != 0:  # skip image blocks
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                bbox = span["bbox"]
                # bbox is (x0, y0, x1, y1)
                if bbox[0] <= px <= bbox[2] and bbox[1] <= py <= bbox[3]:
                    return {
                        "text": span["text"],
                        "font": span["font"],
                        "size": span["size"],
                        "color": span["color"],
                        "flags": span["flags"],
                        "bbox": bbox,
                        "origin": span["origin"],
                    }
    return None


# ── Widget Detection ─────────────────────────────────────────

def _find_widget_for_span(page, span_bbox):
    """Find a form widget whose rect overlaps the span bbox.

    Returns the widget if found, else None.
    """
    span_rect = fitz.Rect(span_bbox)
    for widget in page.widgets():
        if widget.rect.intersects(span_rect):
            return widget
    return None


def _patch_widget_appearance(doc, widget, old_text, new_text):
    """Patch the widget's appearance stream and field value directly.

    This preserves the original layout (line spacing, clipping, positioning)
    instead of regenerating it with widget.update() which may change spacing.

    Also updates the /V (value) key on the correct object (widget or parent)
    so the logical field value persists on save.

    Returns True if successful, False if fallback is needed.
    """
    xref = widget.xref
    ap_n = doc.xref_get_key(xref, "AP/N")
    if ap_n[0] != "xref":
        return False

    n_xref = int(ap_n[1].split()[0])
    stream = doc.xref_stream(n_xref)
    if not stream:
        return False

    try:
        stream_text = stream.decode("latin-1")
    except Exception:
        return False

    # PDF-escape special characters for matching in stream
    old_escaped = old_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    new_escaped = new_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    if old_escaped not in stream_text:
        return False

    patched = stream_text.replace(old_escaped, new_escaped, 1)
    doc.update_stream(n_xref, patched.encode("latin-1"))

    # Persist the field value (/V key) — may be on widget or its parent
    new_value = fitz.get_pdf_str(widget.field_value)
    v_xref = xref
    if doc.xref_get_key(xref, "V")[0] == "null":
        parent = doc.xref_get_key(xref, "Parent")
        if parent[0] == "xref":
            v_xref = int(parent[1].split()[0])
    doc.xref_set_key(v_xref, "V", new_value)

    return True


# ── Text Replacement ─────────────────────────────────────────

def replace_text(page, span_bbox, old_text, new_text, font, size, color, origin=None):
    """Replace text on a PDF page.

    If the text belongs to a form field widget, updates the widget value
    and patches the appearance stream directly to preserve layout.
    Otherwise uses redact+reinsert with the original embedded font when
    available.

    Args:
        page: fitz.Page to modify.
        span_bbox: (x0, y0, x1, y1) tuple of the span bounding box.
        old_text: Original text.
        new_text: Replacement text.
        font: Original font name from the span dict.
        size: Font size.
        color: Integer color from the span dict.
        origin: (x, y) baseline origin from the span dict. If None, falls
                back to (bbox.x0, bbox.y1) which is approximate.
    """
    # Check if text belongs to a form widget
    widget = _find_widget_for_span(page, span_bbox)
    if widget and widget.field_value is not None:
        # Replace the old text within the widget value
        old_value = widget.field_value
        if old_text in old_value:
            widget.field_value = old_value.replace(old_text, new_text, 1)
        else:
            widget.field_value = new_text

        # Patch appearance stream directly to preserve original layout;
        # widget.update() regenerates with different line spacing
        doc = page.parent
        if not doc or not _patch_widget_appearance(doc, widget, old_text, new_text):
            widget.update()  # fallback if patching fails
        return

    # Regular page text: extract font before redaction
    embedded_font = _extract_page_font(page, font)
    if embedded_font and not _font_has_glyphs(embedded_font, new_text):
        embedded_font = None

    rect = fitz.Rect(span_bbox)

    # Redact the old text (white fill to avoid black box)
    page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions()

    rgb = int_to_rgb(color) if isinstance(color, int) else color

    if origin:
        insert_point = fitz.Point(origin[0], origin[1])
    else:
        insert_point = fitz.Point(span_bbox[0], span_bbox[3])

    if embedded_font:
        tw = fitz.TextWriter(page.rect)
        tw.append(insert_point, new_text, font=embedded_font, fontsize=size)
        tw.write_text(page, color=rgb)
    else:
        fontname = map_font(font)
        page.insert_text(
            insert_point,
            new_text,
            fontname=fontname,
            fontsize=size,
            color=rgb,
        )


# ── Freetext Annotation ─────────────────────────────────────

def add_text_annotation(page, point, text, fontsize=12):
    """Add a freetext annotation at the given position.

    Creates a rectangle sized to roughly fit the text and places a
    freetext annotation there.
    """
    # Estimate a reasonable rect for the text
    width = max(len(text) * fontsize * 0.6, 100)
    height = fontsize * 1.8
    rect = fitz.Rect(point.x, point.y, point.x + width, point.y + height)

    annot = page.add_freetext_annot(
        rect,
        text,
        fontsize=fontsize,
        fontname="helv",
        text_color=(0, 0, 0),
        fill_color=(1, 1, 0.8),  # light yellow background
    )
    return annot
