import os

import fitz
import pytest

from app.batch_processor import (
    BatchResult,
    find_files,
    image_to_pdf,
    process_folder,
    redact_file,
)


@pytest.fixture()
def sample_tree(tmp_path):
    """Create a folder tree with PDFs and images for batch testing."""
    # Root PDF with keyword
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "This has SECRET_DATA_123 in it.", fontsize=12)
    doc.save(str(tmp_path / "root.pdf"))
    doc.close()

    # Root PDF without keyword
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Nothing special here.", fontsize=12)
    doc.save(str(tmp_path / "clean.pdf"))
    doc.close()

    # Subfolder PDF with keyword
    sub = tmp_path / "sub"
    sub.mkdir()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Another SECRET_DATA_123 document.", fontsize=12)
    doc.save(str(sub / "nested.pdf"))
    doc.close()

    # Non-supported file (should be ignored)
    (tmp_path / "readme.txt").write_text("just text")

    return tmp_path


@pytest.fixture()
def output_dir(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    return out


class TestFindFiles:
    def test_finds_pdfs_recursively(self, sample_tree):
        files = find_files(str(sample_tree))
        names = [os.path.basename(f) for f in files]
        assert "root.pdf" in names
        assert "clean.pdf" in names
        assert "nested.pdf" in names
        assert "readme.txt" not in names

    def test_non_recursive(self, sample_tree):
        files = find_files(str(sample_tree), recursive=False)
        names = [os.path.basename(f) for f in files]
        assert "root.pdf" in names
        assert "nested.pdf" not in names

    def test_empty_folder(self, tmp_path):
        assert find_files(str(tmp_path)) == []


class TestImageToPdf:
    def test_converts_image(self, sample_image):
        doc = image_to_pdf(sample_image)
        assert len(doc) == 1
        doc.close()


class TestRedactFile:
    def test_redacts_matching_pdf(self, sample_tree):
        path = str(sample_tree / "root.pdf")
        doc, count = redact_file(path, "SECRET_DATA_123")
        assert count > 0
        assert "SECRET_DATA_123" not in doc[0].get_text("text")
        doc.close()

    def test_no_matches_returns_zero(self, sample_tree):
        path = str(sample_tree / "clean.pdf")
        doc, count = redact_file(path, "SECRET_DATA_123")
        assert count == 0
        doc.close()


class TestProcessFolder:
    def test_processes_folder(self, sample_tree, output_dir):
        result = process_folder(
            str(sample_tree), "SECRET_DATA_123", str(output_dir)
        )
        assert isinstance(result, BatchResult)
        assert result.total_files == 3  # root.pdf, clean.pdf, sub/nested.pdf
        assert result.files_with_matches == 2
        assert result.total_matches > 0
        assert len(result.errors) == 0

    def test_all_files_copied_to_output(self, sample_tree, output_dir):
        process_folder(str(sample_tree), "SECRET_DATA_123", str(output_dir))
        # All files should exist in output
        assert os.path.exists(str(output_dir / "root.pdf"))
        assert os.path.exists(str(output_dir / "sub" / "nested.pdf"))
        assert os.path.exists(str(output_dir / "clean.pdf"))

    def test_output_files_are_redacted(self, sample_tree, output_dir):
        process_folder(str(sample_tree), "SECRET_DATA_123", str(output_dir))
        doc = fitz.open(str(output_dir / "root.pdf"))
        assert "SECRET_DATA_123" not in doc[0].get_text("text")
        doc.close()

    def test_preserves_subfolder_structure(self, sample_tree, output_dir):
        process_folder(str(sample_tree), "SECRET_DATA_123", str(output_dir))
        assert os.path.isfile(str(output_dir / "sub" / "nested.pdf"))

    def test_progress_callback(self, sample_tree, output_dir):
        calls = []
        def cb(idx, total, path, matches):
            calls.append((idx, total, path, matches))
        process_folder(str(sample_tree), "SECRET_DATA_123", str(output_dir), progress_callback=cb)
        assert len(calls) == 3  # one per file

    def test_corrupted_file_does_not_halt(self, sample_tree, output_dir):
        # Create a corrupted PDF
        bad = sample_tree / "bad.pdf"
        bad.write_bytes(b"not a pdf")

        result = process_folder(str(sample_tree), "SECRET_DATA_123", str(output_dir))
        assert len(result.errors) == 1
        assert result.errors[0][0] == "bad.pdf"
        # Other files still processed
        assert result.files_with_matches == 2


class TestMultiKeyword:
    """Test multi-keyword redaction and re-run scenarios."""

    @pytest.fixture()
    def tax_tree(self, tmp_path):
        """Mimic a tax folder with PDFs and images across subfolders."""
        # w2/ - PDF with employer name and employee name
        w2 = tmp_path / "w2"
        w2.mkdir()
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), (
            "W-2 Wage and Tax Statement\n"
            "Employer: Acme Corp\n"
            "Employee: John Smith\n"
            "SSN: 123-45-6789\n"
            "Wages: $150,000"
        ), fontsize=12)
        doc.save(str(w2 / "w2_john.pdf"))
        doc.close()

        # brokerage/ - PDF with account holder
        brokerage = tmp_path / "brokerage"
        brokerage.mkdir()
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), (
            "1099-B Consolidated Statement\n"
            "Account Holder: John Smith\n"
            "Acme Corp RSU Sale\n"
            "Proceeds: $50,000"
        ), fontsize=12)
        doc.save(str(brokerage / "1099b.pdf"))
        doc.close()

        # donation/ - PDF without target keywords
        donation = tmp_path / "donation"
        donation.mkdir()
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), (
            "Charitable Donation Receipt\n"
            "Organization: Local Food Bank\n"
            "Amount: $500"
        ), fontsize=12)
        doc.save(str(donation / "receipt.pdf"))
        doc.close()

        # hsa/ - another PDF with employee name
        hsa = tmp_path / "hsa"
        hsa.mkdir()
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), (
            "HSA 1099-SA\n"
            "Account Holder: John Smith\n"
            "Distributions: $2,000"
        ), fontsize=12)
        doc.save(str(hsa / "1099sa.pdf"))
        doc.close()

        return tmp_path

    def test_multiple_keywords_single_pass(self, tax_tree, tmp_path):
        out = tmp_path / "out"
        result = process_folder(str(tax_tree), ["Acme", "Smith"], str(out))
        assert result.total_files == 4
        assert result.files_with_matches == 3  # w2, brokerage, hsa
        # Verify both keywords are gone
        doc = fitz.open(str(out / "w2" / "w2_john.pdf"))
        text = doc[0].get_text("text")
        assert "Acme" not in text
        assert "Smith" not in text
        assert "Wages" in text  # non-target text preserved
        doc.close()

    def test_unmatched_files_still_copied(self, tax_tree, tmp_path):
        out = tmp_path / "out"
        process_folder(str(tax_tree), ["Acme", "Smith"], str(out))
        # donation receipt has no matches but should still be in output
        assert os.path.isfile(str(out / "donation" / "receipt.pdf"))
        doc = fitz.open(str(out / "donation" / "receipt.pdf"))
        assert "Charitable Donation" in doc[0].get_text("text")
        doc.close()

    def test_rerun_on_same_output(self, tax_tree, tmp_path):
        out = tmp_path / "out"
        # Pass 1: redact employer
        r1 = process_folder(str(tax_tree), "Acme", str(out))
        assert r1.files_with_matches == 2  # w2 and brokerage

        # Pass 2: redact employee name in-place on output
        r2 = process_folder(str(out), "Smith", str(out))
        assert r2.files_with_matches == 3  # w2, brokerage, hsa
        assert r2.errors == []

        # Verify both keywords gone from final output
        doc = fitz.open(str(out / "w2" / "w2_john.pdf"))
        text = doc[0].get_text("text")
        assert "Acme" not in text
        assert "Smith" not in text
        doc.close()

    def test_full_folder_structure_preserved(self, tax_tree, tmp_path):
        out = tmp_path / "out"
        process_folder(str(tax_tree), "Acme", str(out))
        assert os.path.isdir(str(out / "w2"))
        assert os.path.isdir(str(out / "brokerage"))
        assert os.path.isdir(str(out / "donation"))
        assert os.path.isdir(str(out / "hsa"))
