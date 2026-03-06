import fitz

from app.text_editor import (
    add_text_annotation,
    get_span_at_point,
    int_to_rgb,
    map_font,
    replace_text,
)


class TestMapFont:
    def test_helvetica_variants(self):
        assert map_font("Helvetica") == "helv"
        assert map_font("Helvetica-Bold") == "helv"
        assert map_font("Arial") == "helv"

    def test_times_variants(self):
        assert map_font("Times") == "tiro"
        assert map_font("TimesNewRoman") == "tiro"

    def test_courier_variants(self):
        assert map_font("Courier") == "cour"
        assert map_font("CourierNew") == "cour"

    def test_unknown_falls_back_to_helv(self):
        assert map_font("SomeUnknownFont") == "helv"

    def test_case_insensitive(self):
        assert map_font("HELVETICA") == "helv"
        assert map_font("times") == "tiro"


class TestIntToRgb:
    def test_black(self):
        assert int_to_rgb(0x000000) == (0.0, 0.0, 0.0)

    def test_white(self):
        r, g, b = int_to_rgb(0xFFFFFF)
        assert abs(r - 1.0) < 0.01
        assert abs(g - 1.0) < 0.01
        assert abs(b - 1.0) < 0.01

    def test_red(self):
        r, g, b = int_to_rgb(0xFF0000)
        assert abs(r - 1.0) < 0.01
        assert g == 0.0
        assert b == 0.0

    def test_arbitrary_color(self):
        r, g, b = int_to_rgb(0x336699)
        assert abs(r - 0x33 / 255) < 0.01
        assert abs(g - 0x66 / 255) < 0.01
        assert abs(b - 0x99 / 255) < 0.01


class TestGetSpanAtPoint:
    def test_finds_span_at_text_location(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        page = doc[0]
        # The sample PDF has text starting at (72, 72)
        # Search for known text to find its location
        rects = page.search_for("Page 1")
        assert len(rects) > 0
        # Use center of the first match rect
        rect = rects[0]
        center = fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
        span = get_span_at_point(page, center)
        assert span is not None
        assert "Page 1" in span["text"] or "Page" in span["text"]
        assert "font" in span
        assert "size" in span
        assert "bbox" in span
        doc.close()

    def test_returns_none_for_empty_area(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        page = doc[0]
        # Bottom-right corner should have no text
        span = get_span_at_point(page, fitz.Point(500, 700))
        assert span is None
        doc.close()


class TestReplaceText:
    def test_replaces_text_on_page(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        page = doc[0]
        # Find the span for "SECRET_DATA_123"
        rects = page.search_for("SECRET_DATA_123")
        assert len(rects) > 0
        rect = rects[0]
        center = fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
        span = get_span_at_point(page, center)
        assert span is not None

        replace_text(
            page,
            span["bbox"],
            span["text"],
            "REPLACED",
            span["font"],
            span["size"],
            span["color"],
        )

        # The new text should be present
        text = page.get_text("text")
        assert "REPLACED" in text
        doc.close()


class TestAddTextAnnotation:
    def test_adds_freetext_annotation(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        page = doc[0]
        point = fitz.Point(100, 500)
        annot = add_text_annotation(page, point, "Hello World", fontsize=14)
        assert annot is not None
        # Verify annotation exists on page
        found = False
        a = page.first_annot
        while a:
            if a.type[0] == fitz.PDF_ANNOT_FREE_TEXT:
                found = True
                break
            a = a.next
        assert found
        doc.close()
