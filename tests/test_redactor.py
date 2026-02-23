import fitz
import pytest

from app.redactor import apply_redactions, mark_for_redaction, save


class TestMarkForRedaction:
    def test_adds_redact_annotations(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        page = doc[0]
        rects = page.search_for("SECRET_DATA_123")
        assert len(rects) > 0

        mark_for_redaction(page, rects)

        count = 0
        annot = page.first_annot
        while annot:
            if annot.type[0] == fitz.PDF_ANNOT_REDACT:
                count += 1
            annot = annot.next
        assert count == len(rects)
        doc.close()

    def test_custom_fill_color(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        page = doc[0]
        rects = page.search_for("SECRET_DATA_123")

        mark_for_redaction(page, rects, fill=(1, 1, 1))

        annot = page.first_annot
        assert annot is not None
        doc.close()

    def test_empty_rects_does_nothing(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        page = doc[0]
        mark_for_redaction(page, [])
        assert page.first_annot is None
        doc.close()


class TestApplyRedactions:
    def test_removes_text_from_all_pages(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        keyword = "SECRET_DATA_123"

        for page in doc:
            rects = page.search_for(keyword)
            mark_for_redaction(page, rects)

        apply_redactions(doc)

        for page in doc:
            assert len(page.search_for(keyword)) == 0
            assert keyword not in page.get_text("text")
        doc.close()

    def test_preserves_non_matching_text(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        mark_for_redaction(doc[0], doc[0].search_for("SECRET_DATA_123"))
        apply_redactions(doc)

        text = doc[0].get_text("text")
        assert "quick brown fox" in text
        doc.close()

    def test_no_annotations_is_safe(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        original_text = doc[0].get_text("text")
        apply_redactions(doc)  # should be a no-op
        assert doc[0].get_text("text") == original_text
        doc.close()


class TestSave:
    def test_saves_valid_pdf(self, sample_pdf, tmp_path):
        doc = fitz.open(sample_pdf)
        out = str(tmp_path / "output.pdf")
        save(doc, out)
        doc.close()

        reopened = fitz.open(out)
        assert len(reopened) == 3
        reopened.close()

    def test_saves_after_redaction(self, sample_pdf, tmp_path):
        doc = fitz.open(sample_pdf)
        keyword = "SECRET_DATA_123"
        for page in doc:
            mark_for_redaction(page, page.search_for(keyword))
        apply_redactions(doc)

        out = str(tmp_path / "redacted.pdf")
        save(doc, out)
        doc.close()

        reopened = fitz.open(out)
        for page in reopened:
            assert len(page.search_for(keyword)) == 0
            assert keyword not in page.get_text("text")
        reopened.close()
