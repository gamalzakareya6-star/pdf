import pytest
from pypdf import PdfReader, PdfWriter

from pdftool import core


def make_pdf(path, pages):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        w.write(f)
    return str(path)


def test_merge(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", 2)
    b = make_pdf(tmp_path / "b.pdf", 3)
    out = core.merge_pdfs([a, b], str(tmp_path / "m.pdf"))
    assert len(PdfReader(out).pages) == 5


def test_parse_ranges():
    assert core.parse_ranges("1-2,4", 5) == [0, 1, 3]
    assert core.parse_ranges("3-", 5) == [2, 3, 4]
    with pytest.raises(ValueError):
        core.parse_ranges("9", 5)


def test_extract_and_split(tmp_path):
    src = make_pdf(tmp_path / "s.pdf", 4)
    out = core.extract_pages(src, "2-3", str(tmp_path / "e.pdf"))
    assert len(PdfReader(out).pages) == 2
    files = core.split_pdf(src, str(tmp_path / "parts"))
    assert len(files) == 4


def test_rotate(tmp_path):
    src = make_pdf(tmp_path / "r.pdf", 1)
    out = core.rotate_pdf(src, 90, str(tmp_path / "rr.pdf"))
    assert PdfReader(out).pages[0].rotation == 90
