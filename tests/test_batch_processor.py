import os

import fitz
import pytest

from app.batch_processor import (
    BatchResult,
    find_files,
    find_image_files,
    image_to_pdf,
    process_folder,
    redact_file,
    search_file,
    search_folder,
    shrink_images,
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

    def test_redacts_form_field_values(self, tmp_path):
        """Form field (widget) values containing keyword should be scrubbed."""
        path = str(tmp_path / "form.pdf")
        doc = fitz.open()
        page = doc.new_page()
        widget = fitz.Widget()
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_name = "Name"
        widget.field_value = "John Smith"
        widget.rect = fitz.Rect(72, 72, 300, 92)
        page.add_widget(widget)
        doc.save(path)
        doc.close()

        doc, count = redact_file(path, "Smith")
        assert count >= 1
        # Check the widget value is scrubbed
        for w in doc[0].widgets():
            if w.field_name == "Name":
                assert "Smith" not in w.field_value
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


# ── Search without redaction ────────────────────────────────
#
# search_file / search_folder are the dry-run half of the batch feature —
# they tell the user what *would* be redacted. Neither had any coverage.


class TestSearchFile:
    def test_counts_matches_in_a_pdf(self, tmp_path):
        path = tmp_path / "one.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Acme here and Acme again", fontsize=11)
        doc.save(str(path))
        doc.close()

        assert search_file(str(path), "Acme") == 2

    def test_accepts_a_bare_string_or_a_list(self, tmp_path):
        path = tmp_path / "two.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "Acme and Globex", fontsize=11)
        doc.save(str(path))
        doc.close()

        assert search_file(str(path), "Acme") == 1
        assert search_file(str(path), ["Acme", "Globex"]) == 2

    def test_returns_zero_when_absent(self, tmp_path):
        path = tmp_path / "three.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "nothing to see", fontsize=11)
        doc.save(str(path))
        doc.close()

        assert search_file(str(path), "Acme") == 0

    def test_does_not_modify_the_file(self, tmp_path):
        path = tmp_path / "untouched.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "Acme stays put", fontsize=11)
        doc.save(str(path))
        doc.close()
        before = path.read_bytes()

        search_file(str(path), "Acme")

        assert path.read_bytes() == before
        reopened = fitz.open(str(path))
        assert "Acme" in reopened[0].get_text("text")
        reopened.close()


class TestSearchFolder:
    def test_reports_only_files_with_matches(self, tax_tree):
        result = search_folder(str(tax_tree), "Acme")
        assert result.total_files > 0
        matched = [rel for rel, _count in result.matches]
        assert len(matched) == 2  # w2 and brokerage
        assert all(count > 0 for _rel, count in result.matches)
        assert result.errors == []

    def test_leaves_the_source_folder_untouched(self, tax_tree):
        target = tax_tree / "w2" / "w2_john.pdf"
        before = target.read_bytes()

        search_folder(str(tax_tree), "Acme")

        assert target.read_bytes() == before

    def test_reports_progress_for_every_file(self, tax_tree):
        seen = []
        search_folder(
            str(tax_tree),
            "Acme",
            progress_callback=lambda i, total, name, count: seen.append(
                (i, total, name)
            ),
        )
        assert len(seen) == seen[0][1]  # one callback per file
        assert [i for i, _t, _n in seen] == list(range(len(seen)))

    def test_no_matches_gives_an_empty_list(self, tax_tree):
        result = search_folder(str(tax_tree), "NOTHING_MATCHES_THIS")
        assert result.matches == []
        assert result.total_files > 0

    def test_search_agrees_with_what_redaction_removes(self, tax_tree, tmp_path):
        """The dry run must predict the real run."""
        searched = search_folder(str(tax_tree), "Acme")
        out = tmp_path / "out"
        redacted = process_folder(str(tax_tree), "Acme", str(out))
        assert len(searched.matches) == redacted.files_with_matches


# ── Image discovery and shrinking ───────────────────────────


class TestFindImageFiles:
    # Note: the sample_image fixture writes into tmp_path itself, so these
    # tests scan a dedicated subfolder rather than picking that file up.

    def test_finds_only_images(self, tmp_path, sample_image):
        import shutil

        root = tmp_path / "scan"
        root.mkdir()
        shutil.copy(sample_image, root / "a.jpg")
        doc = fitz.open()
        doc.new_page()
        doc.save(str(root / "not_an_image.pdf"))
        doc.close()
        (root / "notes.txt").write_text("ignore me")

        found = find_image_files(str(root))
        assert [os.path.basename(p) for p in found] == ["a.jpg"]

    def test_recurses_by_default(self, tmp_path, sample_image):
        import shutil

        root = tmp_path / "scan"
        sub = root / "nested"
        sub.mkdir(parents=True)
        shutil.copy(sample_image, root / "top.jpg")
        shutil.copy(sample_image, sub / "deep.jpg")

        assert len(find_image_files(str(root))) == 2
        assert len(find_image_files(str(root), recursive=False)) == 1

    def test_returns_sorted_paths(self, tmp_path, sample_image):
        import shutil

        root = tmp_path / "scan"
        root.mkdir()
        for name in ("c.jpg", "a.jpg", "b.jpg"):
            shutil.copy(sample_image, root / name)
        found = [os.path.basename(p) for p in find_image_files(str(root))]
        assert found == sorted(found)


class TestShrinkImages:
    def test_reduces_file_size(self, tmp_path, sample_image):
        import shutil

        src = tmp_path / "src"
        src.mkdir()
        shutil.copy(sample_image, src / "big.jpg")
        out = tmp_path / "out"

        result = shrink_images(str(src), str(out), max_dimension=200)

        assert result.processed == 1
        assert result.errors == []
        assert result.new_bytes <= result.original_bytes
        assert (out / "big.jpg").exists()

    def test_caps_the_longest_side(self, tmp_path, sample_image):
        import shutil

        from PIL import Image

        src = tmp_path / "src"
        src.mkdir()
        shutil.copy(sample_image, src / "big.jpg")
        out = tmp_path / "out"

        shrink_images(str(src), str(out), max_dimension=120)

        with Image.open(out / "big.jpg") as img:
            assert max(img.size) <= 120

    def test_leaves_the_originals_alone(self, tmp_path, sample_image):
        import shutil

        src = tmp_path / "src"
        src.mkdir()
        shutil.copy(sample_image, src / "big.jpg")
        before = (src / "big.jpg").read_bytes()

        shrink_images(str(src), str(tmp_path / "out"), max_dimension=100)

        assert (src / "big.jpg").read_bytes() == before

    def test_reports_progress(self, tmp_path, sample_image):
        import shutil

        src = tmp_path / "src"
        src.mkdir()
        for name in ("a.jpg", "b.jpg"):
            shutil.copy(sample_image, src / name)

        seen = []
        shrink_images(
            str(src),
            str(tmp_path / "out"),
            max_dimension=150,
            progress_callback=lambda *args: seen.append(args),
        )
        assert len(seen) == 2

    def test_non_image_files_are_preserved(self, tmp_path, sample_image):
        import shutil

        src = tmp_path / "src"
        src.mkdir()
        shutil.copy(sample_image, src / "pic.jpg")
        (src / "readme.txt").write_text("keep me")
        out = tmp_path / "out"

        shrink_images(str(src), str(out), max_dimension=150)

        assert (out / "readme.txt").read_text() == "keep me"
