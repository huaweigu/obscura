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


@pytest.fixture()
def repeated_keyword_pdf(tmp_path):
    """One page with three occurrences of a keyword in different contexts."""
    path = tmp_path / "repeated.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "alpha TARGET one", fontsize=12)
    page.insert_text((72, 200), "beta TARGET two", fontsize=12)
    page.insert_text((72, 300), "gamma TARGET three", fontsize=12)
    doc.save(str(path))
    doc.close()
    return str(path)


class TestSnippetExtraction:
    """Each result row must describe its own match, not the page's first one."""

    def test_snippets_are_distinct_per_match(self, main_window, repeated_keyword_pdf):
        main_window._open_file_by_path(repeated_keyword_pdf)
        main_window._do_search("TARGET")

        results = main_window._current_state.search_results
        assert len(results) == 3

        snippets = [r.snippet for r in results]
        assert len(set(snippets)) == 3, f"snippets are not distinct: {snippets}"

    def test_each_snippet_carries_its_own_context(
        self, main_window, repeated_keyword_pdf
    ):
        main_window._open_file_by_path(repeated_keyword_pdf)
        main_window._do_search("TARGET")

        snippets = [r.snippet for r in main_window._current_state.search_results]
        # search_for returns matches in reading order.
        assert "alpha" in snippets[0]
        assert "beta" in snippets[1]
        assert "gamma" in snippets[2]

    def test_snippet_includes_the_keyword(self, main_window, repeated_keyword_pdf):
        main_window._open_file_by_path(repeated_keyword_pdf)
        main_window._do_search("TARGET")
        for r in main_window._current_state.search_results:
            assert "TARGET" in r.snippet

    def test_extract_snippet_falls_back_to_keyword(self, main_window, sample_pdf):
        """More rects than text occurrences (ligatures, odd encodings) must
        not raise or produce a wrong snippet."""
        main_window._open_file_by_path(sample_pdf)
        page = main_window._doc[0]
        snippet = main_window._extract_snippet(page, "SECRET_DATA_123", occurrence=99)
        assert snippet == "SECRET_DATA_123"

    def test_snippet_marks_truncation_with_ellipsis(self, main_window, tmp_path):
        path = tmp_path / "long.pdf"
        doc = fitz.open()
        page = doc.new_page()
        # insert_text does not wrap, so build the padding as separate lines
        # rather than one long line that would run off the page.
        lines = ["padding words here and there"] * 4
        lines += ["NEEDLE is buried in the middle"]
        lines += ["more padding words follow after"] * 4
        page.insert_text((40, 100), "\n".join(lines), fontsize=9)
        doc.save(str(path))
        doc.close()

        main_window._open_file_by_path(str(path))
        main_window._do_search("NEEDLE")
        snippet = main_window._current_state.search_results[0].snippet
        assert snippet.startswith("…")
        assert snippet.endswith("…")

    def test_snippets_distinct_across_pages(self, main_window, sample_pdf):
        """The 3-page fixture has 2 matches per page in different sentences."""
        main_window._open_file_by_path(sample_pdf)
        main_window._do_search("SECRET_DATA_123")
        results = main_window._current_state.search_results
        assert len(results) == 6

        for page_index in range(3):
            page_snippets = [
                r.snippet for r in results if r.page_index == page_index
            ]
            assert len(set(page_snippets)) == 2, (
                f"page {page_index} snippets not distinct: {page_snippets}"
            )
