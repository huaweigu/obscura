

def mark_for_redaction(page, rects, fill=(0, 0, 0)):
    """Add redaction annotations to a page for the given rectangles."""
    for rect in rects:
        page.add_redact_annot(rect, fill=fill)


def apply_redactions(doc):
    """Apply all pending redaction annotations across all pages.

    This permanently removes the underlying text from the content stream.
    """
    for page in doc:
        if page.first_annot:
            page.apply_redactions()


def save(doc, path):
    """Save the document with cleanup of orphaned objects."""
    doc.save(path, garbage=4, deflate=True)
