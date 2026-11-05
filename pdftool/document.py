"""PDF document model.

Pure PyMuPDF, no Qt.  Every coordinate that goes in or out of this module is in
*view space*: points on the page as it is displayed (i.e. after /Rotate), with
the origin at the top-left corner.  Internally edits are performed on the
un-rotated page so that PyMuPDF's different coordinate conventions never matter.
"""
from __future__ import annotations

import hashlib
import html as _html
import os
import re
import shutil
import tempfile
from contextlib import contextmanager

try:  # PyMuPDF >= 1.24.3 exposes the new name
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

RTL_RE = re.compile("[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufeff]")
MAX_UNDO = 25
MAX_UNDO_BYTES = 400 * 1024 * 1024


class PdfError(Exception):
    pass


class PasswordRequired(PdfError):
    pass


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def parse_ranges(spec: str, total: int) -> list[int]:
    """'1-3,5,8-' -> zero based page indexes (order kept, duplicates allowed)."""
    spec = (spec or "").strip().lower()
    if spec in ("", "all", "*"):
        return list(range(total))
    pages: list[int] = []
    for part in spec.replace(" ", "").replace("؛", ",").replace("،", ",").split(","):
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


def _fonts_dirs() -> list[str]:
    dirs = []
    if os.name == "nt":
        dirs.append(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    else:
        dirs += [
            "/System/Library/Fonts/Supplemental", "/System/Library/Fonts", "/Library/Fonts",
            "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/noto",
            "/usr/share/fonts/truetype/liberation", "/usr/share/fonts/TTF",
        ]
    return dirs


_FONT_CANDIDATES = [
    ("Arial", ["arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf"]),
    ("Tahoma", ["tahoma.ttf", "Tahoma.ttf"]),
    ("Segoe UI", ["segoeui.ttf"]),
    ("Times New Roman", ["times.ttf", "Times New Roman.ttf", "LiberationSerif-Regular.ttf"]),
    ("Courier New", ["cour.ttf", "Courier New.ttf", "LiberationMono-Regular.ttf"]),
    ("Verdana", ["verdana.ttf", "Verdana.ttf"]),
    ("Calibri", ["calibri.ttf"]),
    ("Sakkal Majalla", ["majalla.ttf"]),
    ("Traditional Arabic", ["trado.ttf"]),
    ("DejaVu Sans", ["DejaVuSans.ttf"]),
]


def available_fonts() -> list[tuple[str, str | None]]:
    """[(display name, file path or None)] - first entry is the built-in font."""
    out: list[tuple[str, str | None]] = [("Default", None)]
    seen = set()
    for name, files in _FONT_CANDIDATES:
        for d in _fonts_dirs():
            hit = next((os.path.join(d, f) for f in files if os.path.isfile(os.path.join(d, f))), None)
            if hit and name not in seen:
                out.append((name, hit))
                seen.add(name)
                break
    return out


def _arabic_capable_font() -> str | None:
    for name, path in available_fonts():
        if path and name in ("Arial", "Tahoma", "Segoe UI", "Times New Roman", "DejaVu Sans", "Verdana"):
            return path
    return None


def _hex(color) -> str:
    r, g, b = (max(0, min(255, int(round(c * 255)))) for c in color[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


_font_tmp: dict[str, tuple[str, str]] = {}


def _font_archive(fontfile: str):
    """Copy the font into a private temp dir (url() in CSS needs a plain relative name)."""
    if fontfile not in _font_tmp:
        tmp = tempfile.mkdtemp(prefix="pdftool_font_")
        name = "f" + hashlib.md5(fontfile.encode("utf8")).hexdigest()[:10] + os.path.splitext(fontfile)[1].lower()
        shutil.copyfile(fontfile, os.path.join(tmp, name))
        _font_tmp[fontfile] = (tmp, name)
    tmp, name = _font_tmp[fontfile]
    return fitz.Archive(tmp), name


def _open_stream(data: bytes, password: str | None):
    doc = fitz.open(stream=data, filetype="pdf")
    if doc.needs_pass:
        if not password or not doc.authenticate(password):
            doc.close()
            raise PasswordRequired()
    return doc


def _rect(r) -> "fitz.Rect":
    return fitz.Rect(r)


def _norm(a, b) -> "fitz.Rect":
    r = fitz.Rect(min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y))
    if r.width < 1:
        r.x1 = r.x0 + 1
    if r.height < 1:
        r.y1 = r.y0 + 1
    return r


# --------------------------------------------------------------------------
# document
# --------------------------------------------------------------------------
class PdfDoc:
    def __init__(self, data: bytes, path: str | None = None, password: str | None = None):
        self.doc = _open_stream(data, password)
        self.path = path
        self.password = password if self.doc.is_encrypted or password else None
        self.size = len(data)
        self.modified = False
        self.version = 0
        self._undo: list[bytes] = []
        self._redo: list[bytes] = []
        self._listeners: list = []
        self._clear_caches()

    # ---- construction -------------------------------------------------
    @classmethod
    def open(cls, path: str, password: str | None = None) -> "PdfDoc":
        with open(path, "rb") as f:
            data = f.read()
        return cls(data, path, password)

    @classmethod
    def blank(cls, width: float = 595, height: float = 842, pages: int = 1) -> "PdfDoc":
        d = fitz.open()
        for _ in range(pages):
            d.new_page(width=width, height=height)
        data = d.tobytes()
        d.close()
        obj = cls(data, None)
        obj.modified = True
        return obj

    def close(self):
        self._listeners.clear()
        try:
            self.doc.close()
        except Exception:
            pass

    # ---- listeners / caches ------------------------------------------
    def add_listener(self, cb):
        self._listeners.append(cb)

    def remove_listener(self, cb):
        if cb in self._listeners:
            self._listeners.remove(cb)

    def _clear_caches(self):
        self._sizes = None
        self._words: dict[int, list] = {}
        self._links: dict[int, list] = {}
        self._annots: dict[int, list] = {}

    def _changed(self, kind: str):
        self.version += 1
        self._clear_caches()
        for cb in list(self._listeners):
            cb(kind)

    # ---- state ---------------------------------------------------------
    @property
    def page_count(self) -> int:
        return self.doc.page_count

    @property
    def title(self) -> str:
        return os.path.basename(self.path) if self.path else "Untitled.pdf"

    def page_sizes(self) -> list[tuple[float, float]]:
        if self._sizes is None:
            out = []
            for i in range(self.doc.page_count):
                r = self.doc.load_page(i).rect
                out.append((float(r.width), float(r.height)))
            self._sizes = out
        return self._sizes

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def _dump(self) -> bytes:
        return self.doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE)

    def _load(self, data: bytes):
        old = self.doc
        self.doc = _open_stream(data, None)
        try:
            old.close()
        except Exception:
            pass

    def _trim(self, stack: list[bytes]):
        while len(stack) > MAX_UNDO or (len(stack) > 1 and sum(map(len, stack)) > MAX_UNDO_BYTES):
            stack.pop(0)

    @contextmanager
    def _edit(self, kind: str = "content"):
        """Snapshot -> mutate -> notify.  Restores the snapshot if the body raises."""
        snap = self._dump()
        try:
            yield
        except Exception:
            self._load(snap)
            self._clear_caches()
            raise
        self._undo.append(snap)
        self._trim(self._undo)
        self._redo.clear()
        self.modified = True
        self._changed(kind)

    @contextmanager
    def _unrot(self, pno: int):
        """Yield (page, derotation matrix, rotation matrix) with the page temporarily un-rotated."""
        page = self.doc.load_page(pno)
        rot = page.rotation
        if rot:
            dm = fitz.Matrix(page.derotation_matrix)
            rm = fitz.Matrix(page.rotation_matrix)
            page.set_rotation(0)
            try:
                yield page, dm, rm
            finally:
                page.set_rotation(rot)
        else:
            yield page, fitz.Matrix(1, 0, 0, 1, 0, 0), fitz.Matrix(1, 0, 0, 1, 0, 0)

    def undo(self):
        if not self._undo:
            return
        self._redo.append(self._dump())
        self._load(self._undo.pop())
        self.modified = True
        self._changed("structure")

    def redo(self):
        if not self._redo:
            return
        self._undo.append(self._dump())
        self._load(self._redo.pop())
        self.modified = True
        self._changed("structure")

    # ---- rendering ----------------------------------------------------
    def render(self, pno: int, scale: float):
        """-> (width, height, stride, rgb bytes)"""
        page = self.doc.load_page(pno)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pix.width, pix.height, pix.stride, pix.samples

    # ---- read helpers (view space) -------------------------------------
    def words(self, pno: int) -> list[tuple]:
        """[(x0, y0, x1, y1, text, block, line, word)] in reading order."""
        c = self._words.get(pno)
        if c is None:
            with self._unrot(pno) as (page, dm, rm):
                raw = page.get_text("words")
            c = []
            for w in raw:
                r = fitz.Rect(w[:4]) * rm
                c.append((r.x0, r.y0, r.x1, r.y1, w[4], w[5], w[6], w[7]))
            self._words[pno] = c
        return c

    def search(self, pno: int, needle: str) -> list[tuple]:
        with self._unrot(pno) as (page, dm, rm):
            rects = page.search_for(needle)
        out = []
        for r in rects:
            rr = fitz.Rect(r) * rm
            out.append((rr.x0, rr.y0, rr.x1, rr.y1))
        return out

    def links(self, pno: int) -> list[dict]:
        c = self._links.get(pno)
        if c is None:
            with self._unrot(pno) as (page, dm, rm):
                raw = page.get_links()
            c = []
            for l in raw:
                r = fitz.Rect(l["from"]) * rm
                c.append({"rect": (r.x0, r.y0, r.x1, r.y1), "kind": l.get("kind"),
                          "page": l.get("page"), "uri": l.get("uri")})
            self._links[pno] = c
        return c

    def annots(self, pno: int) -> list[dict]:
        c = self._annots.get(pno)
        if c is None:
            c = []
            with self._unrot(pno) as (page, dm, rm):
                for a in (page.annots() or []):
                    name = a.type[1]
                    if name in ("Link", "Widget", "Popup"):
                        continue
                    r = fitz.Rect(a.rect) * rm
                    c.append({"xref": a.xref, "type": name, "rect": (r.x0, r.y0, r.x1, r.y1),
                              "content": (a.info or {}).get("content", "") or ""})
            self._annots[pno] = c
        return c

    def all_annots(self) -> list[dict]:
        out = []
        for i in range(self.page_count):
            for a in self.annots(i):
                out.append({**a, "page": i})
        return out

    def toc(self) -> list[list]:
        try:
            return self.doc.get_toc(simple=True)
        except Exception:
            return []

    def metadata(self) -> dict:
        return dict(self.doc.metadata or {})

    def text_line_at(self, pno: int, x: float, y: float) -> dict | None:
        """The text line under a view-space point (for the basic text editor)."""
        with self._unrot(pno) as (page, dm, rm):
            pt = fitz.Point(x, y) * dm
            data = page.get_text("dict")
        for b in data.get("blocks", []):
            if b.get("type") != 0:
                continue
            for line in b.get("lines", []):
                r = fitz.Rect(line["bbox"])
                spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
                if spans and r.contains(pt):
                    c = spans[0].get("color", 0)
                    col = (((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255)
                    rr = r * rm
                    return {"text": "".join(s["text"] for s in spans), "size": float(spans[0]["size"]),
                            "color": col, "font": spans[0].get("font", ""),
                            "rect": (rr.x0, rr.y0, rr.x1, rr.y1)}
        return None

    # ---- annotations ---------------------------------------------------
    def add_markup(self, pno: int, kind: str, rects: list[tuple], color, opacity: float = 1.0):
        if not rects:
            return
        with self._edit(), self._unrot(pno) as (page, dm, rm):
            quads = [(fitz.Rect(r) * dm).quad for r in rects]
            fn = {"highlight": page.add_highlight_annot, "underline": page.add_underline_annot,
                  "strike": page.add_strikeout_annot}[kind]
            a = fn(quads=quads)
            a.set_colors(stroke=tuple(color[:3]))
            if opacity < 1:
                a.set_opacity(opacity)
            a.update()

    def add_ink(self, pno: int, strokes: list[list[tuple]], color, width: float, opacity: float = 1.0):
        strokes = [s for s in strokes if len(s) >= 2]
        if not strokes:
            return
        with self._edit(), self._unrot(pno) as (page, dm, rm):
            conv = [[tuple(fitz.Point(x, y) * dm) for x, y in s] for s in strokes]
            a = page.add_ink_annot(conv)
            a.set_border(width=width)
            a.set_colors(stroke=tuple(color[:3]))
            if opacity < 1:
                a.set_opacity(opacity)
            a.update()

    def add_shape(self, pno: int, kind: str, p1: tuple, p2: tuple, color, width: float,
                  fill: bool = False, opacity: float = 1.0):
        with self._edit(), self._unrot(pno) as (page, dm, rm):
            a1 = fitz.Point(*p1) * dm
            a2 = fitz.Point(*p2) * dm
            if kind in ("rect", "ellipse"):
                r = _norm(a1, a2)
                ann = page.add_rect_annot(r) if kind == "rect" else page.add_circle_annot(r)
            else:
                ann = page.add_line_annot(a1, a2)
                if kind == "arrow":
                    ann.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_CLOSED_ARROW)
            ann.set_border(width=width)
            col = tuple(color[:3])
            if fill and kind in ("rect", "ellipse"):
                ann.set_colors(stroke=col, fill=col)
            else:
                ann.set_colors(stroke=col)
            if opacity < 1:
                ann.set_opacity(opacity)
            ann.update()

    def add_note(self, pno: int, x: float, y: float, text: str, color=(1, 0.8, 0)):
        with self._edit(), self._unrot(pno) as (page, dm, rm):
            ann = page.add_text_annot(fitz.Point(x, y) * dm, text, icon="Note")
            ann.set_colors(stroke=tuple(color[:3]))
            ann.update()

    def set_annot_content(self, pno: int, xref: int, text: str):
        with self._edit(), self._unrot(pno) as (page, dm, rm):
            for a in (page.annots() or []):
                if a.xref == xref:
                    a.set_info(content=text)
                    a.update()
                    break

    def delete_annot(self, pno: int, xref: int):
        with self._edit(), self._unrot(pno) as (page, dm, rm):
            for a in (page.annots() or []):
                if a.xref == xref:
                    page.delete_annot(a)
                    break

    # ---- page content ----------------------------------------------------
    def _draw_text(self, page, rect, text: str, size: float, color, fontfile: str | None):
        """Write (possibly Arabic / mixed) text into rect of an un-rotated page."""
        rtl = bool(RTL_RE.search(text))
        if rtl and not fontfile:
            fontfile = _arabic_capable_font()
        body = _html.escape(text).replace("\r", "").replace("\n", "<br>")
        direction = "rtl" if rtl else "ltr"
        align = "right" if rtl else "left"
        html = f'<div dir="{direction}" style="direction:{direction}; text-align:{align};">{body}</div>'
        css = (f"* {{ font-size:{size:g}pt; color:{_hex(color)}; margin:0; padding:0; }}")
        archive = None
        if fontfile and os.path.isfile(fontfile):
            archive, fname = _font_archive(fontfile)
            css = (f'@font-face {{ font-family: ptfont; src: url("{fname}"); }}\n'
                   f'* {{ font-family: ptfont; font-size:{size:g}pt; color:{_hex(color)}; margin:0; padding:0; }}')
        r = fitz.Rect(rect)
        page_rect = page.rect
        r = r & page_rect if not (r & page_rect).is_empty else r
        try:
            for _ in range(7):
                spare, _scale = page.insert_htmlbox(r, html, css=css, archive=archive, scale_low=1)
                if spare >= 0:
                    return
                if r.y1 >= page_rect.y1 - 1:
                    break
                r.y1 = min(page_rect.y1, r.y1 + max(r.height, size * 2))
            page.insert_htmlbox(r, html, css=css, archive=archive)  # last resort: allow shrinking
        except Exception:
            page.insert_textbox(r, text, fontsize=size, fontname="helv", color=tuple(color[:3]))

    def add_text(self, pno: int, rect: tuple, text: str, size: float, color, fontfile: str | None = None):
        if not text.strip():
            return
        with self._edit(), self._unrot(pno) as (page, dm, rm):
            self._draw_text(page, fitz.Rect(rect) * dm, text, size, color, fontfile)

    def replace_text(self, pno: int, rect: tuple, text: str, size: float, color, fontfile: str | None = None):
        """Cover the old line (white box through a redaction) and write the new text."""
        with self._edit(), self._unrot(pno) as (page, dm, rm):
            raw = fitz.Rect(rect) * dm
            page.add_redact_annot(raw + (-0.5, -0.5, 0.5, 0.5), fill=(1, 1, 1))
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
            if text.strip():
                box = fitz.Rect(raw.x0, raw.y0 - 1, min(page.rect.x1, raw.x0 + max(raw.width * 1.35, 80)), raw.y1 + 2)
                self._draw_text(page, box, text, size, color, fontfile)

    def add_image(self, pno: int, rect: tuple, path: str):
        with self._edit(), self._unrot(pno) as (page, dm, rm):
            page.insert_image(fitz.Rect(rect) * dm, filename=path, keep_proportion=True, overlay=True)

    def redact(self, pno: int, rect: tuple):
        with self._edit(), self._unrot(pno) as (page, dm, rm):
            page.add_redact_annot(fitz.Rect(rect) * dm, fill=(0, 0, 0))
            page.apply_redactions()

    # ---- page management -------------------------------------------------
    def rotate_pages(self, idxs: list[int], delta: int):
        with self._edit("structure"):
            for i in idxs:
                p = self.doc.load_page(i)
                p.set_rotation((p.rotation + delta) % 360)

    def delete_pages(self, idxs: list[int]):
        idxs = sorted(set(idxs))
        if not idxs:
            return
        if len(idxs) >= self.page_count:
            raise PdfError("Cannot delete all pages")
        with self._edit("structure"):
            self.doc.delete_pages(idxs)

    def reorder(self, order: list[int]):
        if sorted(order) != list(range(self.page_count)):
            raise PdfError("Invalid page order")
        with self._edit("structure"):
            self.doc.select(order)

    def insert_blank(self, after: int, width: float | None = None, height: float | None = None):
        ref = self.doc.load_page(max(0, min(after, self.page_count - 1))).rect
        with self._edit("structure"):
            self.doc.new_page(pno=after + 1, width=width or ref.width, height=height or ref.height)

    def duplicate_pages(self, idxs: list[int]):
        with self._edit("structure"):
            for i in sorted(idxs, reverse=True):
                self.doc.fullcopy_page(i, i + 1)

    def insert_pdf(self, path: str, at: int, password: str | None = None, pages: list[int] | None = None):
        src = fitz.open(path)
        try:
            if src.needs_pass and not (password and src.authenticate(password)):
                raise PasswordRequired()
            with self._edit("structure"):
                if pages is None:
                    self.doc.insert_pdf(src, start_at=at)
                else:
                    for k, p in enumerate(pages):
                        self.doc.insert_pdf(src, from_page=p, to_page=p, start_at=at + k)
        finally:
            src.close()

    def set_metadata(self, meta: dict):
        with self._edit("meta"):
            cur = dict(self.doc.metadata or {})
            cur.update(meta)
            self.doc.set_metadata(cur)

    def set_password(self, pw: str | None):
        self.password = pw or None
        self.modified = True
        self._changed("meta")

    # ---- output --------------------------------------------------------
    def extract_to(self, idxs: list[int], out: str):
        new = fitz.open()
        try:
            for i in idxs:
                new.insert_pdf(self.doc, from_page=i, to_page=i)
            new.save(out, garbage=3, deflate=True)
        finally:
            new.close()

    def export_images(self, folder: str, idxs: list[int], dpi: int = 150, fmt: str = "png", progress=None) -> list[str]:
        os.makedirs(folder, exist_ok=True)
        stem = os.path.splitext(self.title)[0]
        out = []
        for n, i in enumerate(idxs):
            if progress and not progress(n, len(idxs)):
                break
            pix = self.doc.load_page(i).get_pixmap(dpi=dpi, alpha=False)
            target = os.path.join(folder, f"{stem}_page_{i + 1:03d}.{fmt}")
            pix.save(target)
            out.append(target)
        return out

    def save(self, path: str | None = None, optimize: bool = False) -> str:
        path = path or self.path
        if not path:
            raise PdfError("No path")
        kw = dict(garbage=4 if optimize else 3, deflate=True)
        if optimize:
            kw.update(deflate_images=True, deflate_fonts=True)
        if self.password:
            kw.update(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=self.password, owner_pw=self.password)
        else:
            kw.update(encryption=fitz.PDF_ENCRYPT_NONE)
        data = self.doc.tobytes(**kw)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        # saving with garbage collection may renumber objects: reload from the saved bytes
        old = self.doc
        self.doc = _open_stream(data, self.password)
        try:
            old.close()
        except Exception:
            pass
        self.path = path
        self.size = len(data)
        self.modified = False
        self._changed("saved")
        return path


def merge_files(paths: list[str], out: str, passwords: dict | None = None) -> str:
    new = fitz.open()
    try:
        for p in paths:
            src = fitz.open(p)
            try:
                if src.needs_pass and not src.authenticate((passwords or {}).get(p, "")):
                    raise PasswordRequired(p)
                new.insert_pdf(src)
            finally:
                src.close()
        new.save(out, garbage=3, deflate=True)
    finally:
        new.close()
    return out
