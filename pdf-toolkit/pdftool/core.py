"""Core PDF operations (no GUI code here, so it is easy to test)."""
from pathlib import Path
from typing import Iterable, List

from pypdf import PdfReader, PdfWriter


def merge_pdfs(inputs: Iterable[str], output: str) -> str:
    writer = PdfWriter()
    for path in inputs:
        writer.append(PdfReader(path))
    with open(output, "wb") as f:
        writer.write(f)
    return output


def parse_ranges(spec: str, total: int) -> List[int]:
    """'1-3,5,8-' -> zero-based page indexes."""
    pages: List[int] = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start = int(a) if a else 1
            end = int(b) if b else total
        else:
            start = end = int(part)
        if start < 1 or end > total or start > end:
            raise ValueError(f"Invalid range: {part} (document has {total} pages)")
        pages.extend(range(start - 1, end))
    if not pages:
        raise ValueError("No pages selected")
    return pages


def extract_pages(input_path: str, spec: str, output: str) -> str:
    reader = PdfReader(input_path)
    writer = PdfWriter()
    for i in parse_ranges(spec, len(reader.pages)):
        writer.add_page(reader.pages[i])
    with open(output, "wb") as f:
        writer.write(f)
    return output


def split_pdf(input_path: str, out_dir: str) -> List[str]:
    reader = PdfReader(input_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(input_path).stem
    files = []
    for i, page in enumerate(reader.pages, 1):
        w = PdfWriter()
        w.add_page(page)
        target = out / f"{stem}_page_{i}.pdf"
        with open(target, "wb") as f:
            w.write(f)
        files.append(str(target))
    return files


def rotate_pdf(input_path: str, degrees: int, output: str) -> str:
    if degrees % 90:
        raise ValueError("Rotation must be a multiple of 90")
    reader = PdfReader(input_path)
    writer = PdfWriter()
    for page in reader.pages:
        page.rotate(degrees)
        writer.add_page(page)
    with open(output, "wb") as f:
        writer.write(f)
    return output


def extract_text(input_path: str) -> str:
    reader = PdfReader(input_path)
    return "\n\n".join((p.extract_text() or "") for p in reader.pages)
