import os

import pytest

fitz = pytest.importorskip("pymupdf")

from pdftool.document import (PasswordRequired, PdfDoc, PdfError, merge_files,  # noqa: E402
                              parse_ranges)


def make_pdf(path, pages=3, rotate=0):
    d = fitz.open()
    for i in range(pages):
        p = d.new_page(width=400, height=500)
        p.insert_text((50, 100), f"Hello world page {i + 1}", fontsize=18)
        p.insert_text((50, 150), "Second line of text", fontsize=14)
        if rotate:
            p.set_rotation(rotate)
    d.save(str(path))
    d.close()
    return str(path)


def test_parse_ranges():
    assert parse_ranges("1-2,4", 5) == [0, 1, 3]
    assert parse_ranges("3-", 5) == [2, 3, 4]
    assert parse_ranges("all", 3) == [0, 1, 2]
    assert parse_ranges("", 2) == [0, 1]
    for bad in ("9", "0", "4-2", "a"):
        with pytest.raises(ValueError):
            parse_ranges(bad, 5)


def test_open_words_search(tmp_path):
    pdf = PdfDoc.open(make_pdf(tmp_path / "a.pdf"))
    assert pdf.page_count == 3
    assert pdf.page_sizes()[0] == (400.0, 500.0)
    words = [w[4] for w in pdf.words(0)]
    assert "Hello" in words and "world" in words
    assert len(pdf.search(1, "Hello world")) == 1
    w, h, stride, data = pdf.render(0, 1.0)
    assert (w, h) == (400, 500) and len(data) >= w * h * 3


def test_markup_undo_redo(tmp_path):
    pdf = PdfDoc.open(make_pdf(tmp_path / "a.pdf"))
    rect = tuple(pdf.words(0)[0][:4])
    pdf.add_markup(0, "highlight", [rect], (1, 1, 0))
    assert pdf.modified and pdf.can_undo
    assert [a["type"] for a in pdf.annots(0)] == ["Highlight"]
    pdf.undo()
    assert pdf.annots(0) == [] and pdf.can_redo
    pdf.redo()
    assert len(pdf.annots(0)) == 1


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_coordinates_on_rotated_pages(tmp_path, rot):
    """A highlight made from a word rectangle must land on that word, whatever /Rotate is."""
    pdf = PdfDoc.open(make_pdf(tmp_path / "r.pdf", pages=1, rotate=rot))
    w = next(x for x in pdf.words(0) if x[4] == "world")
    pdf.add_markup(0, "highlight", [tuple(w[:4])], (1, 1, 0))
    a = pdf.annots(0)[0]["rect"]
    cx, cy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    assert w[0] - 1 <= cx <= w[2] + 1 and w[1] - 1 <= cy <= w[3] + 1
    # and the word is still found at the same place after the edit
    again = next(x for x in pdf.words(0) if x[4] == "world")
    assert abs(again[0] - w[0]) < 1 and abs(again[1] - w[1]) < 1


def test_shapes_ink_note_delete(tmp_path):
    pdf = PdfDoc.open(make_pdf(tmp_path / "a.pdf"))
    pdf.add_shape(0, "rect", (10, 10), (100, 80), (1, 0, 0), 2, fill=True)
    pdf.add_shape(0, "ellipse", (10, 10), (100, 80), (0, 0, 1), 2)
    pdf.add_shape(0, "line", (10, 10), (100, 80), (0, 0, 1), 2)
    pdf.add_shape(0, "arrow", (10, 10), (100, 80), (0, 0, 1), 2)
    pdf.add_ink(0, [[(10, 10), (20, 30), (40, 20)]], (0, 0, 0), 3)
    pdf.add_note(0, 200, 200, "my comment")
    types = sorted(a["type"] for a in pdf.annots(0))
    assert types == sorted(["Square", "Circle", "Line", "Line", "Ink", "Text"])
    note = next(a for a in pdf.annots(0) if a["type"] == "Text")
    assert note["content"] == "my comment"
    pdf.set_annot_content(0, note["xref"], "changed")
    assert next(a for a in pdf.annots(0) if a["type"] == "Text")["content"] == "changed"
    pdf.delete_annot(0, note["xref"])
    assert all(a["type"] != "Text" for a in pdf.annots(0))


def test_add_and_replace_text(tmp_path):
    pdf = PdfDoc.open(make_pdf(tmp_path / "a.pdf"))
    pdf.add_text(0, (50, 200, 300, 240), "Added text", 14, (0, 0, 0))
    assert "Added" in "".join(w[4] for w in pdf.words(0))
    pdf.add_text(0, (50, 250, 300, 290), "نص عربي للاختبار", 14, (0, 0, 0))  # must not raise
    info = pdf.text_line_at(0, 60, 95)
    assert info and info["text"].startswith("Hello")
    pdf.replace_text(0, info["rect"], "Goodbye there", info["size"], info["color"])
    text = " ".join(w[4] for w in pdf.words(0))
    assert "Goodbye" in text and "Hello" not in text


def test_redact_removes_text(tmp_path):
    pdf = PdfDoc.open(make_pdf(tmp_path / "a.pdf"))
    w = next(x for x in pdf.words(0) if x[4] == "Hello")
    pdf.redact(0, tuple(w[:4]))
    assert "Hello" not in [x[4] for x in pdf.words(0)]


def test_page_management(tmp_path):
    pdf = PdfDoc.open(make_pdf(tmp_path / "a.pdf", pages=4))
    pdf.rotate_pages([0], 90)
    assert pdf.page_sizes()[0] == (500.0, 400.0)
    pdf.duplicate_pages([1])
    assert pdf.page_count == 5
    pdf.insert_blank(0)
    assert pdf.page_count == 6
    pdf.delete_pages([0, 1])
    assert pdf.page_count == 4
    pdf.reorder([3, 2, 1, 0])
    assert pdf.page_count == 4
    with pytest.raises(PdfError):
        pdf.reorder([0, 0, 1, 2])
    with pytest.raises(PdfError):
        pdf.delete_pages([0, 1, 2, 3])
    pdf.undo()
    assert pdf.page_count == 4


def test_failed_edit_rolls_back(tmp_path):
    pdf = PdfDoc.open(make_pdf(tmp_path / "a.pdf"))
    before = pdf.version
    with pytest.raises(Exception):
        pdf.add_image(0, (0, 0, 50, 50), str(tmp_path / "missing.png"))
    assert pdf.page_count == 3 and not pdf.can_undo and pdf.version == before


def test_save_roundtrip_and_password(tmp_path):
    src = make_pdf(tmp_path / "a.pdf")
    pdf = PdfDoc.open(src)
    pdf.add_markup(0, "highlight", [tuple(pdf.words(0)[0][:4])], (1, 1, 0))
    out = str(tmp_path / "out.pdf")
    pdf.save(out)
    assert not pdf.modified and pdf.path == out
    again = PdfDoc.open(out)
    assert len(again.annots(0)) == 1
    pdf.set_password("secret")
    enc = str(tmp_path / "enc.pdf")
    pdf.save(enc)
    with pytest.raises(PasswordRequired):
        PdfDoc.open(enc)
    with pytest.raises(PasswordRequired):
        PdfDoc.open(enc, "wrong")
    ok = PdfDoc.open(enc, "secret")
    assert ok.page_count == 3
    ok.set_password(None)
    plain = str(tmp_path / "plain.pdf")
    ok.save(plain)
    assert PdfDoc.open(plain).page_count == 3


def test_merge_extract_insert_export(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", 2)
    b = make_pdf(tmp_path / "b.pdf", 3)
    m = merge_files([a, b], str(tmp_path / "m.pdf"))
    pdf = PdfDoc.open(m)
    assert pdf.page_count == 5
    pdf.extract_to([0, 4], str(tmp_path / "e.pdf"))
    assert PdfDoc.open(str(tmp_path / "e.pdf")).page_count == 2
    pdf.insert_pdf(a, 1)
    assert pdf.page_count == 7
    files = pdf.export_images(str(tmp_path / "img"), [0, 1], dpi=50, fmt="png")
    assert len(files) == 2 and all(os.path.getsize(f) > 0 for f in files)


def test_metadata_and_blank():
    pdf = PdfDoc.blank(pages=2)
    assert pdf.page_count == 2 and pdf.modified and pdf.title == "Untitled.pdf"
    pdf.set_metadata({"title": "T", "author": "A"})
    assert pdf.metadata()["title"] == "T"
