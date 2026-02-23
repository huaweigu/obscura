import fitz
import pytest

from app.search_panel import SearchResult


class TestSearchResult:
    def test_stores_attributes(self):
        rect = fitz.Rect(10, 20, 100, 40)
        r = SearchResult(page_index=2, rect=rect, snippet="hello world")
        assert r.page_index == 2
        assert r.rect == rect
        assert r.snippet == "hello world"

    def test_default_snippet(self):
        r = SearchResult(page_index=0, rect=fitz.Rect(0, 0, 1, 1))
        assert r.snippet == ""


class TestPdfSearch:
    """Test PyMuPDF search_for directly on sample PDFs."""

    def test_finds_keyword_on_all_pages(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        keyword = "SECRET_DATA_123"
        for i in range(len(doc)):
            matches = doc[i].search_for(keyword)
            assert len(matches) == 2, f"Expected 2 matches on page {i + 1}"
        doc.close()

    def test_case_insensitive_not_default(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        # PyMuPDF search_for is case-insensitive by default
        matches = doc[0].search_for("secret_data_123")
        assert len(matches) >= 2
        doc.close()

    def test_no_matches_for_absent_keyword(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        matches = doc[0].search_for("NONEXISTENT_XYZ")
        assert len(matches) == 0
        doc.close()

    def test_search_returns_rects(self, sample_pdf):
        doc = fitz.open(sample_pdf)
        matches = doc[0].search_for("SECRET_DATA_123")
        for m in matches:
            assert isinstance(m, fitz.Rect)
            assert m.width > 0
            assert m.height > 0
        doc.close()
