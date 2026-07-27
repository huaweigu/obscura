import fitz
import pytest

from app.text_editor import (
    _extract_page_font,
    _find_widget_for_span,
    _font_has_glyphs,
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


# ── Form fields ─────────────────────────────────────────────
#
# Editing text that belongs to an AcroForm widget takes a completely
# different path from ordinary page text: the field value is updated and the
# appearance stream is patched in place to preserve the original layout.
# None of that had any coverage.


@pytest.fixture()
def form_pdf(tmp_path):
    """A PDF with a filled-in text form field."""
    path = tmp_path / "form.pdf"
    doc = fitz.open()
    page = doc.new_page()

    widget = fitz.Widget()
    widget.field_name = "employer"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.rect = fitz.Rect(72, 100, 320, 124)
    widget.field_value = "Acme Corporation"
    widget.text_fontsize = 11
    page.add_widget(widget)

    page.insert_text((72, 300), "Ordinary page text here", fontsize=11)
    doc.save(str(path))
    doc.close()
    return str(path)


class TestFindWidgetForSpan:
    def test_finds_the_widget_overlapping_a_span(self, form_pdf):
        doc = fitz.open(form_pdf)
        page = doc[0]
        widget = _find_widget_for_span(page, (80, 105, 200, 120))
        assert widget is not None
        assert widget.field_name == "employer"
        doc.close()

    def test_returns_none_away_from_any_widget(self, form_pdf):
        doc = fitz.open(form_pdf)
        page = doc[0]
        assert _find_widget_for_span(page, (72, 295, 250, 310)) is None
        doc.close()


class TestReplaceTextInFormField:
    def test_updates_the_field_value(self, form_pdf, tmp_path):
        doc = fitz.open(form_pdf)
        page = doc[0]

        replace_text(
            page,
            (80, 105, 200, 120),
            "Acme Corporation",
            "Globex Industries",
            "helv",
            11,
            0,
        )

        out = tmp_path / "edited.pdf"
        doc.save(str(out))
        doc.close()

        reopened = fitz.open(str(out))
        values = [w.field_value for w in reopened[0].widgets()]
        reopened.close()
        assert "Globex Industries" in values

    def test_the_field_survives_a_save_and_reload(self, form_pdf, tmp_path):
        doc = fitz.open(form_pdf)
        replace_text(
            doc[0], (80, 105, 200, 120), "Acme Corporation", "Initech", "helv", 11, 0
        )
        out = tmp_path / "roundtrip.pdf"
        doc.save(str(out))
        doc.close()

        reopened = fitz.open(str(out))
        widgets = list(reopened[0].widgets())
        assert len(widgets) == 1
        assert widgets[0].field_value == "Initech"
        assert widgets[0].field_name == "employer"
        reopened.close()

    def test_ordinary_page_text_still_uses_the_redact_path(
        self, form_pdf, tmp_path
    ):
        """Text outside any widget must not be routed through the form path."""
        doc = fitz.open(form_pdf)
        page = doc[0]
        span = get_span_at_point(page, fitz.Point(100, 297))
        assert span is not None

        replace_text(
            page,
            span["bbox"],
            span["text"],
            "Replaced body text",
            span["font"],
            span["size"],
            span["color"],
            origin=span["origin"],
        )

        out = tmp_path / "body.pdf"
        doc.save(str(out))
        doc.close()

        reopened = fitz.open(str(out))
        text = reopened[0].get_text("text")
        reopened.close()
        assert "Replaced body text" in text
        assert "Ordinary page text here" not in text


class TestEmbeddedFontHelpers:
    def test_font_has_glyphs_accepts_plain_ascii(self):
        font = fitz.Font("helv")
        assert _font_has_glyphs(font, "Hello World") is True

    def test_font_has_glyphs_rejects_missing_glyphs(self):
        font = fitz.Font("helv")
        # Base-14 Helvetica has no CJK coverage.
        assert _font_has_glyphs(font, "你好") is False

    def test_extract_page_font_returns_none_for_unknown_font(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        assert _extract_page_font(doc[0], "NoSuchFontName") is None
        doc.close()
