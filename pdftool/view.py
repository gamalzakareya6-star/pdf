"""The page canvas: continuous scrolling, zoom, text selection, annotations and drawing tools."""
from __future__ import annotations

import math
from bisect import bisect_right
from collections import OrderedDict

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QImage, QPainter, QPainterPath, QPen, QPixmap,
                           QTextOption)
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QFrame, QInputDialog, QMenu, QPlainTextEdit

from .document import PdfDoc, available_fonts
from .i18n import tr

MARGIN = 28
GAP = 16
MIN_ZOOM = 0.1
MAX_ZOOM = 4.0
CACHE_LIMIT = 384 * 1024 * 1024

MARKUP = ("highlight", "underline", "strike")
RUBBER = ("rect", "ellipse", "line", "arrow", "text", "image", "signature", "redact")
MARKUP_DEFAULTS = {"highlight": (1.0, 0.84, 0.04), "underline": (0.2, 0.4, 1.0), "strike": (1.0, 0.2, 0.2)}


def _qcolor(c, alpha: int = 255) -> QColor:
    col = QColor.fromRgbF(float(c[0]), float(c[1]), float(c[2]))
    col.setAlpha(alpha)
    return col


class InlineEditor(QPlainTextEdit):
    committed = Signal()
    cancelled = Signal()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.committed.emit()
            return
        super().keyPressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.committed.emit()


class DocumentView(QAbstractScrollArea):
    pageChanged = Signal(int)
    zoomChanged = Signal(float)
    selectionChanged = Signal(bool)
    annotSelected = Signal(bool)
    message = Signal(str)
    needImage = Signal()

    def __init__(self, pdf: PdfDoc, opts: dict, parent=None):
        super().__init__(parent)
        self.pdf = pdf
        self.opts = opts
        self.zoom = 1.0
        self.fit_mode: str | None = "width"
        self.tool = "select"
        self.invert = False
        self.canvas_color = QColor("#d9dde5")
        self.accent = QColor("#4f6bed")
        self._sizes: list[tuple[float, float]] = []
        self._tops: list[float] = []
        self._cw = 0
        self._ch = 0
        self._cache: OrderedDict = OrderedDict()
        self._cache_bytes = 0
        self._sel: tuple[int, int, int] | None = None
        self._sel_annot: tuple[int, int] | None = None
        self._drag: dict | None = None
        self._pan = None
        self._space = False
        self._editor: InlineEditor | None = None
        self._editor_ctx = None
        self._search_hits: dict[int, list] = {}
        self._search_cur: tuple[int, int] | None = None
        self._current = 0
        self._fonts = None

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.viewport().setMouseTracking(True)
        self.verticalScrollBar().setSingleStep(48)
        self.horizontalScrollBar().setSingleStep(48)
        self._listener = self._on_doc_changed
        pdf.add_listener(self._listener)
        self.relayout()

    # ------------------------------------------------------------------
    # life cycle / theme
    # ------------------------------------------------------------------
    def close_view(self):
        self.pdf.remove_listener(self._listener)
        self._cache.clear()

    def set_colors(self, canvas: str, accent: str):
        self.canvas_color = QColor(canvas)
        self.accent = QColor(accent)
        self.viewport().update()

    def _on_doc_changed(self, kind: str):
        self._cache.clear()
        self._cache_bytes = 0
        if self._editor is not None:
            self._cancel_editor()
        self._sel = None
        if self._sel_annot is not None:
            i, xref = self._sel_annot
            alive = i < self.pdf.page_count and any(a["xref"] == xref for a in self.pdf.annots(i))
            if not alive:
                self._sel_annot = None
                self.annotSelected.emit(False)
        if kind in ("structure", "load", "saved"):
            self._search_hits = {}
            self._search_cur = None
            self.relayout()
        else:
            self.viewport().update()
        self.selectionChanged.emit(False)

    # ------------------------------------------------------------------
    # layout / zoom
    # ------------------------------------------------------------------
    def relayout(self):
        self._sizes = self.pdf.page_sizes()
        self._current = max(0, min(self._current, len(self._sizes) - 1))
        self._apply_fit()
        self._compute()
        self.viewport().update()

    def _compute(self):
        z = self.zoom
        y = float(MARGIN)
        tops = []
        maxw = 0.0
        for w, h in self._sizes:
            tops.append(y)
            y += h * z + GAP
            maxw = max(maxw, w * z)
        self._tops = tops
        self._cw = int(maxw + 2 * MARGIN)
        self._ch = int(y - GAP + MARGIN) if tops else 0
        self._update_bars()

    def _update_bars(self):
        vp = self.viewport().size()
        hb = self.horizontalScrollBar()
        vb = self.verticalScrollBar()
        hb.setRange(0, max(0, self._cw - vp.width()))
        hb.setPageStep(max(1, vp.width()))
        vb.setRange(0, max(0, self._ch - vp.height()))
        vb.setPageStep(max(1, vp.height()))

    def _apply_fit(self) -> bool:
        if not self.fit_mode or not self._sizes:
            return False
        vp = self.viewport()
        w, h = self._sizes[min(self._current, len(self._sizes) - 1)]
        availw = max(60, vp.width() - 2 * MARGIN)
        z = availw / w
        if self.fit_mode == "page":
            z = min(z, max(60, vp.height() - 2 * MARGIN) / h)
        z = max(MIN_ZOOM, min(MAX_ZOOM, z))
        if abs(z - self.zoom) > 1e-4:
            self.zoom = z
            return True
        return False

    def _anchor_ref(self, anchor: QPointF):
        if not self._tops:
            return None
        cy = self.verticalScrollBar().value() + anchor.y()
        i = max(0, bisect_right(self._tops, cy) - 1)
        oy = (cy - self._tops[i]) / self.zoom
        ox = (self.horizontalScrollBar().value() + anchor.x() - self._page_x(i)) / self.zoom
        return i, ox, oy

    def _restore_anchor(self, ref, anchor: QPointF):
        if ref is None:
            return
        i, ox, oy = ref
        z = self.zoom
        self.verticalScrollBar().setValue(int(self._tops[i] + oy * z - anchor.y()))
        self.horizontalScrollBar().setValue(int(self._page_x(i) + ox * z - anchor.x()))

    def set_zoom(self, z: float, anchor: QPointF | None = None):
        z = max(MIN_ZOOM, min(MAX_ZOOM, z))
        self.fit_mode = None
        self._set_zoom_value(z, anchor)

    def _set_zoom_value(self, z: float, anchor: QPointF | None = None):
        vp = self.viewport()
        if anchor is None:
            anchor = QPointF(vp.width() / 2, vp.height() / 2)
        ref = self._anchor_ref(anchor)
        self.zoom = z
        self._compute()
        self._restore_anchor(ref, anchor)
        self.viewport().update()
        self.zoomChanged.emit(self.zoom)

    def zoom_in(self):
        self.set_zoom(self.zoom * 1.2)

    def zoom_out(self):
        self.set_zoom(self.zoom / 1.2)

    def set_fit(self, mode: str | None):
        self.fit_mode = mode
        if mode:
            ref = self._anchor_ref(QPointF(0, 0))
            self._apply_fit()
            self._compute()
            self._restore_anchor(ref, QPointF(0, 0))
            self.go_to_page(self._current)
            self.zoomChanged.emit(self.zoom)
            self.viewport().update()

    def set_invert(self, on: bool):
        self.invert = on
        self._cache.clear()
        self._cache_bytes = 0
        self.viewport().update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        ref = self._anchor_ref(QPointF(0, 0))
        changed = self._apply_fit()
        self._compute()
        if changed:
            self._restore_anchor(ref, QPointF(0, 0))
            self.zoomChanged.emit(self.zoom)

    # ------------------------------------------------------------------
    # geometry helpers
    # ------------------------------------------------------------------
    def _page_x(self, i: int) -> float:
        w = self._sizes[i][0] * self.zoom
        total = max(self._cw, self.viewport().width())
        return (total - w) / 2

    def _page_view_rect(self, i: int) -> QRectF:
        w, h = self._sizes[i]
        z = self.zoom
        return QRectF(self._page_x(i) - self.horizontalScrollBar().value(),
                      self._tops[i] - self.verticalScrollBar().value(), w * z, h * z)

    def _page_at(self, pos: QPointF):
        if not self._tops:
            return None
        cy = self.verticalScrollBar().value() + pos.y()
        i = bisect_right(self._tops, cy) - 1
        if i < 0:
            return None
        z = self.zoom
        w, h = self._sizes[i]
        if cy > self._tops[i] + h * z:
            return None
        cx = self.horizontalScrollBar().value() + pos.x()
        px = self._page_x(i)
        if cx < px or cx > px + w * z:
            return None
        return i, (cx - px) / z, (cy - self._tops[i]) / z

    def _to_page(self, i: int, pos: QPointF) -> tuple[float, float]:
        z = self.zoom
        x = (self.horizontalScrollBar().value() + pos.x() - self._page_x(i)) / z
        y = (self.verticalScrollBar().value() + pos.y() - self._tops[i]) / z
        w, h = self._sizes[i]
        return max(0.0, min(w, x)), max(0.0, min(h, y))

    # ------------------------------------------------------------------
    # navigation
    # ------------------------------------------------------------------
    @property
    def current_page(self) -> int:
        return self._current

    def go_to_page(self, i: int):
        if not self._tops:
            return
        i = max(0, min(i, len(self._tops) - 1))
        self.verticalScrollBar().setValue(int(self._tops[i] - MARGIN * 0.6))
        self._set_current(i)

    def _set_current(self, i: int):
        if i != self._current:
            self._current = i
            self.pageChanged.emit(i)

    def scrollContentsBy(self, dx, dy):
        self.viewport().update()
        if not self._tops:
            return
        vb = self.verticalScrollBar()
        if vb.value() >= vb.maximum() - 2 and vb.maximum() > 0:
            i = len(self._tops) - 1
        else:
            y = vb.value() + self.viewport().height() * 0.3
            i = max(0, min(len(self._tops) - 1, bisect_right(self._tops, y) - 1))
        self._set_current(i)

    def ensure_visible_rect(self, pno: int, rect: tuple):
        if pno >= len(self._tops):
            return
        z = self.zoom
        y = self._tops[pno] + rect[1] * z
        vb = self.verticalScrollBar()
        vh = self.viewport().height()
        if not (vb.value() + 40 < y < vb.value() + vh - 80):
            vb.setValue(int(y - vh / 3))
        x = self._page_x(pno) + rect[0] * z
        hb = self.horizontalScrollBar()
        vw = self.viewport().width()
        if not (hb.value() < x < hb.value() + vw - 60):
            hb.setValue(int(x - vw / 3))

    # ------------------------------------------------------------------
    # search overlay
    # ------------------------------------------------------------------
    def set_search(self, hits: dict, current: tuple | None):
        self._search_hits = hits
        self._search_cur = current
        self.viewport().update()

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------
    def _page_pixmap(self, i: int) -> QPixmap:
        dpr = self.devicePixelRatioF()
        scale = round(self.zoom * dpr, 4)
        key = (i, scale, self.pdf.version, self.invert)
        pm = self._cache.get(key)
        if pm is not None:
            self._cache.move_to_end(key)
            return pm
        w, h, stride, data = self.pdf.render(i, scale)
        img = QImage(data, w, h, stride, QImage.Format.Format_RGB888).convertToFormat(QImage.Format.Format_RGB32)
        if self.invert:
            img.invertPixels()
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        self._cache[key] = pm
        self._cache_bytes += w * h * 4
        while self._cache_bytes > CACHE_LIMIT and len(self._cache) > 3:
            _, old = self._cache.popitem(last=False)
            self._cache_bytes -= old.width() * old.height() * 4
        return pm

    def paintEvent(self, ev):
        p = QPainter(self.viewport())
        p.fillRect(ev.rect(), self.canvas_color)
        if not self._tops:
            return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        vb = self.verticalScrollBar().value()
        top = vb + ev.rect().top()
        bottom = vb + ev.rect().bottom()
        first = max(0, bisect_right(self._tops, top) - 1)
        for i in range(first, len(self._tops)):
            if self._tops[i] > bottom:
                break
            self._paint_page(p, i)

    def _paint_page(self, p: QPainter, i: int):
        r = self._page_view_rect(i)
        z = self.zoom
        p.setPen(Qt.PenStyle.NoPen)
        for k, a in ((7, 10), (4, 16), (2, 24)):
            p.setBrush(QColor(0, 0, 0, a))
            p.drawRoundedRect(r.adjusted(-k, -k + 3, k, k + 3), 3, 3)
        p.fillRect(r, QColor("white"))
        try:
            pm = self._page_pixmap(i)
            p.drawPixmap(r, pm, QRectF(pm.rect()))
        except Exception as ex:  # a broken page must not take the whole view down
            p.setPen(QColor("#c00"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, f"{ex}")
        # search hits
        hits = self._search_hits.get(i)
        if hits:
            p.setPen(Qt.PenStyle.NoPen)
            for k, h in enumerate(hits):
                cur = self._search_cur == (i, k)
                p.setBrush(QColor(255, 140, 0, 150) if cur else QColor(255, 220, 0, 110))
                p.drawRect(QRectF(r.x() + h[0] * z, r.y() + h[1] * z, (h[2] - h[0]) * z, (h[3] - h[1]) * z))
        # text selection
        if self._sel and self._sel[0] == i:
            p.setPen(Qt.PenStyle.NoPen)
            sel = QColor(self.accent)
            sel.setAlpha(90)
            p.setBrush(sel)
            for h in self._selection_rects():
                p.drawRect(QRectF(r.x() + h[0] * z, r.y() + h[1] * z, (h[2] - h[0]) * z, (h[3] - h[1]) * z))
        # selected annotation
        if self._sel_annot and self._sel_annot[0] == i:
            for a in self.pdf.annots(i):
                if a["xref"] == self._sel_annot[1]:
                    h = a["rect"]
                    pen = QPen(self.accent, 1.6, Qt.PenStyle.DashLine)
                    p.setPen(pen)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(QRectF(r.x() + h[0] * z - 2, r.y() + h[1] * z - 2,
                                      (h[2] - h[0]) * z + 4, (h[3] - h[1]) * z + 4))
        # live drawing preview
        d = self._drag
        if d and d.get("page") == i and d["tool"] != "sel":
            self._paint_preview(p, r, d)

    def _paint_preview(self, p: QPainter, r: QRectF, d: dict):
        z = self.zoom
        t = d["tool"]
        color = self.opts.get("color", (1, 0, 0))
        width = max(1.0, float(self.opts.get("width", 2)) * z)
        if t == "draw":
            pts = d["pts"]
            if len(pts) < 2:
                return
            path = QPainterPath(QPointF(r.x() + pts[0][0] * z, r.y() + pts[0][1] * z))
            for x, y in pts[1:]:
                path.lineTo(r.x() + x * z, r.y() + y * z)
            pen = QPen(_qcolor(color, int(255 * float(self.opts.get("opacity", 1)))), width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            return
        sx, sy = d["start"]
        cx, cy = d["cur"]
        a = QPointF(r.x() + sx * z, r.y() + sy * z)
        b = QPointF(r.x() + cx * z, r.y() + cy * z)
        box = QRectF(a, b).normalized()
        if t in ("rect", "ellipse"):
            p.setPen(QPen(_qcolor(color), width))
            p.setBrush(_qcolor(color, 70) if self.opts.get("fill") else Qt.BrushStyle.NoBrush)
            p.drawRect(box) if t == "rect" else p.drawEllipse(box)
        elif t in ("line", "arrow"):
            p.setPen(QPen(_qcolor(color), width))
            p.drawLine(a, b)
        elif t == "redact":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRect(box)
        else:
            p.setPen(QPen(self.accent, 1.4, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(box)

    # ------------------------------------------------------------------
    # text selection
    # ------------------------------------------------------------------
    @staticmethod
    def _word_distance(w, x, y) -> float:
        dx = max(w[0] - x, 0, x - w[2])
        dy = max(w[1] - y, 0, y - w[3])
        return dx * dx + dy * dy * 4

    def _nearest_word(self, words, x, y) -> int:
        best, bi = 1e18, 0
        for k, w in enumerate(words):
            d = self._word_distance(w, x, y)
            if d < best:
                best, bi = d, k
                if d == 0:
                    break
        return bi

    def _over_word(self, i, x, y) -> bool:
        return any(w[0] <= x <= w[2] and w[1] <= y <= w[3] for w in self.pdf.words(i))

    def _selection_rects(self) -> list[tuple]:
        if not self._sel:
            return []
        i, a, b = self._sel
        groups: OrderedDict = OrderedDict()
        for w in self.pdf.words(i)[a:b + 1]:
            key = (w[5], w[6])
            g = groups.get(key)
            if g is None:
                groups[key] = [w[0], w[1], w[2], w[3]]
            else:
                g[0], g[1] = min(g[0], w[0]), min(g[1], w[1])
                g[2], g[3] = max(g[2], w[2]), max(g[3], w[3])
        return [tuple(v) for v in groups.values()]

    def selected_text(self) -> str:
        if not self._sel:
            return ""
        i, a, b = self._sel
        out, last = [], None
        for w in self.pdf.words(i)[a:b + 1]:
            key = (w[5], w[6])
            if last is not None:
                out.append("\n" if key != last else " ")
            out.append(w[4])
            last = key
        return "".join(out)

    @property
    def has_selection(self) -> bool:
        return self._sel is not None

    def copy_selection(self):
        text = self.selected_text()
        if text:
            QApplication.clipboard().setText(text)
            self.message.emit(tr("Copied"))

    def select_all_text(self):
        i = self._current
        words = self.pdf.words(i)
        if words:
            self._sel = (i, 0, len(words) - 1)
            self.selectionChanged.emit(True)
            self.viewport().update()

    def _color_for(self, kind: str):
        return self.opts.get("tool_colors", {}).get(kind) or MARKUP_DEFAULTS.get(kind, (1, 0, 0))

    def apply_markup(self, kind: str):
        rects = self._selection_rects()
        if not rects:
            self.message.emit(tr("Select some text first"))
            return
        i = self._sel[0]
        self._sel = None
        self.selectionChanged.emit(False)
        self.pdf.add_markup(i, kind, rects, self._color_for(kind), 1.0)

    # ------------------------------------------------------------------
    # annotations / links
    # ------------------------------------------------------------------
    def _annot_at(self, i, x, y):
        for a in reversed(self.pdf.annots(i)):
            r = a["rect"]
            if r[0] - 3 <= x <= r[2] + 3 and r[1] - 3 <= y <= r[3] + 3:
                return a
        return None

    def _link_at(self, i, x, y):
        for l in self.pdf.links(i):
            r = l["rect"]
            if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
                return l
        return None

    def _follow(self, link: dict):
        if link.get("uri"):
            QDesktopServices.openUrl(QUrl(link["uri"]))
        elif link.get("page") is not None and link["page"] >= 0:
            self.go_to_page(int(link["page"]))

    def select_annot(self, i: int | None, a: dict | None = None):
        self._sel_annot = (i, a["xref"]) if (i is not None and a is not None) else None
        if self._sel_annot:
            self._sel = None
        self.annotSelected.emit(self._sel_annot is not None)
        self.viewport().update()

    def delete_selected_annot(self):
        if self._sel_annot:
            i, xref = self._sel_annot
            self._sel_annot = None
            self.annotSelected.emit(False)
            self.pdf.delete_annot(i, xref)

    def edit_selected_annot(self):
        if not self._sel_annot:
            return
        i, xref = self._sel_annot
        a = next((a for a in self.pdf.annots(i) if a["xref"] == xref), None)
        if a is None:
            return
        text, ok = QInputDialog.getMultiLineText(self, tr("Edit comment"), tr("Comment:"), a["content"])
        if ok:
            self.pdf.set_annot_content(i, xref, text)

    # ------------------------------------------------------------------
    # tools
    # ------------------------------------------------------------------
    def set_tool(self, tool: str):
        self.tool = tool
        if self._editor is not None:
            self._commit_editor()
        self._drag = None
        if tool not in ("select",) + MARKUP:
            self._sel = None
            self.selectionChanged.emit(False)
        if tool != "select":
            self.select_annot(None)
        self.viewport().setCursor(Qt.CursorShape.OpenHandCursor if tool == "hand" else Qt.CursorShape.ArrowCursor)
        self.viewport().update()

    def _update_hover_cursor(self, pos: QPointF):
        cur = Qt.CursorShape.ArrowCursor
        if self.tool == "hand" or self._space:
            cur = Qt.CursorShape.OpenHandCursor
        else:
            hit = self._page_at(pos)
            if hit:
                i, x, y = hit
                t = self.tool
                if t in RUBBER or t in ("draw", "note", "edittext"):
                    cur = Qt.CursorShape.CrossCursor
                elif t == "select":
                    if self._annot_at(i, x, y) or self._link_at(i, x, y):
                        cur = Qt.CursorShape.PointingHandCursor
                    elif self._over_word(i, x, y):
                        cur = Qt.CursorShape.IBeamCursor
                elif t in MARKUP:
                    cur = Qt.CursorShape.IBeamCursor
        self.viewport().setCursor(cur)

    # ------------------------------------------------------------------
    # mouse
    # ------------------------------------------------------------------
    def mousePressEvent(self, e):
        self.setFocus()
        pos = e.position()
        btn = e.button()
        if self._editor is not None:
            self._commit_editor()
        if btn == Qt.MouseButton.MiddleButton or (
                btn == Qt.MouseButton.LeftButton and (self.tool == "hand" or self._space)):
            self._pan = (QPointF(pos), self.horizontalScrollBar().value(), self.verticalScrollBar().value())
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if btn != Qt.MouseButton.LeftButton:
            return
        hit = self._page_at(pos)
        if hit is None:
            self._sel = None
            self.select_annot(None)
            self.selectionChanged.emit(False)
            return
        i, x, y = hit
        t = self.tool
        if t == "select" or t in MARKUP:
            if t == "select":
                a = self._annot_at(i, x, y)
                if a is not None:
                    self.select_annot(i, a)
                    return
            self.select_annot(None)
            words = self.pdf.words(i)
            anchor = self._nearest_word(words, x, y) if words else -1
            self._sel = None
            self._drag = {"tool": "sel", "page": i, "anchor": anchor, "moved": False,
                          "pos": QPointF(pos), "click": (x, y)}
        elif t == "draw":
            self._drag = {"tool": "draw", "page": i, "pts": [(x, y)]}
        elif t in RUBBER or t in ("note", "edittext"):
            self._drag = {"tool": t, "page": i, "start": (x, y), "cur": (x, y)}
        self.viewport().update()

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._pan is not None:
            p0, hx, vy = self._pan
            self.horizontalScrollBar().setValue(int(hx - (pos.x() - p0.x())))
            self.verticalScrollBar().setValue(int(vy - (pos.y() - p0.y())))
            return
        d = self._drag
        if d is None:
            self._update_hover_cursor(pos)
            return
        i = d["page"]
        x, y = self._to_page(i, pos)
        if d["tool"] == "sel":
            if (pos - d["pos"]).manhattanLength() > 4:
                d["moved"] = True
            if d["moved"] and d["anchor"] >= 0:
                k = self._nearest_word(self.pdf.words(i), x, y)
                self._sel = (i, min(d["anchor"], k), max(d["anchor"], k))
                self.selectionChanged.emit(True)
        elif d["tool"] == "draw":
            lx, ly = d["pts"][-1]
            if math.hypot(x - lx, y - ly) * self.zoom >= 1.5:
                d["pts"].append((x, y))
        else:
            d["cur"] = (x, y)
        self.viewport().update()

    def mouseReleaseEvent(self, e):
        if self._pan is not None:
            self._pan = None
            self._update_hover_cursor(e.position())
            return
        d = self._drag
        if d is None or e.button() != Qt.MouseButton.LeftButton:
            return
        self._drag = None
        i = d["page"]
        t = d["tool"]
        self.viewport().update()
        if t == "sel":
            if not d["moved"]:
                self._sel = None
                self.selectionChanged.emit(False)
                if self.tool == "select":
                    link = self._link_at(i, *d["click"])
                    if link:
                        self._follow(link)
            elif self.tool in MARKUP:
                self.apply_markup(self.tool)
            return
        color = self.opts.get("color", (1, 0, 0))
        width = float(self.opts.get("width", 2))
        opacity = float(self.opts.get("opacity", 1.0))
        if t == "draw":
            self.pdf.add_ink(i, [d["pts"]], color, width, opacity)
            return
        sx, sy = d["start"]
        cx, cy = d["cur"]
        dist = math.hypot(cx - sx, cy - sy) * self.zoom
        box = (min(sx, cx), min(sy, cy), max(sx, cx), max(sy, cy))
        if t in ("rect", "ellipse", "line", "arrow"):
            if dist >= 4:
                self.pdf.add_shape(i, t, (sx, sy), (cx, cy), color, width, bool(self.opts.get("fill")), opacity)
        elif t == "redact":
            if dist >= 6:
                self.pdf.redact(i, box)
        elif t == "text":
            size = float(self.opts.get("fontsize", 14))
            rect = box if dist >= 8 else (sx, sy, sx + 220, sy + max(36.0, size * 2.2))
            self._open_editor(i, rect)
        elif t in ("image", "signature"):
            self._place_image(i, sx, sy, box if dist >= 8 else None)
        elif t == "note":
            text, ok = QInputDialog.getMultiLineText(self, tr("Add comment"), tr("Comment:"), "")
            if ok and text.strip():
                self.pdf.add_note(i, sx, sy, text, color)
        elif t == "edittext":
            self._edit_text_at(i, sx, sy)

    def mouseDoubleClickEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self.tool != "select":
            return
        hit = self._page_at(e.position())
        if hit is None:
            return
        i, x, y = hit
        a = self._annot_at(i, x, y)
        if a is not None:
            self.select_annot(i, a)
            self.edit_selected_annot()
            return
        words = self.pdf.words(i)
        if words and self._over_word(i, x, y):
            k = self._nearest_word(words, x, y)
            self._sel = (i, k, k)
            self.selectionChanged.emit(True)
            self.viewport().update()

    def wheelEvent(self, e):
        mods = e.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            dy = e.angleDelta().y()
            if dy:
                self.set_zoom(self.zoom * (1.1 ** (dy / 120.0)), e.position())
            e.accept()
            return
        if mods & Qt.KeyboardModifier.ShiftModifier:
            hb = self.horizontalScrollBar()
            hb.setValue(hb.value() - e.angleDelta().y() // 2)
            e.accept()
            return
        super().wheelEvent(e)

    # ------------------------------------------------------------------
    # keyboard
    # ------------------------------------------------------------------
    def keyPressEvent(self, e):
        k = e.key()
        mods = e.modifiers()
        vb = self.verticalScrollBar()
        hb = self.horizontalScrollBar()
        if k == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = True
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        elif k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self._sel_annot:
            self.delete_selected_annot()
        elif k == Qt.Key.Key_Escape:
            self._sel = None
            self._drag = None
            self.select_annot(None)
            self.selectionChanged.emit(False)
            self.viewport().update()
        elif k == Qt.Key.Key_C and mods & Qt.KeyboardModifier.ControlModifier:
            self.copy_selection()
        elif k == Qt.Key.Key_A and mods & Qt.KeyboardModifier.ControlModifier:
            self.select_all_text()
        elif k == Qt.Key.Key_Down:
            vb.setValue(vb.value() + 60)
        elif k == Qt.Key.Key_Up:
            vb.setValue(vb.value() - 60)
        elif k == Qt.Key.Key_Right:
            hb.setValue(hb.value() + 60)
        elif k == Qt.Key.Key_Left:
            hb.setValue(hb.value() - 60)
        elif k == Qt.Key.Key_PageDown:
            vb.setValue(vb.value() + vb.pageStep() - 40)
        elif k == Qt.Key.Key_PageUp:
            vb.setValue(vb.value() - vb.pageStep() + 40)
        elif k == Qt.Key.Key_Home:
            self.go_to_page(0)
        elif k == Qt.Key.Key_End:
            self.go_to_page(len(self._tops) - 1)
        else:
            super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = False
            self._update_hover_cursor(self.viewport().mapFromGlobal(self.cursor().pos()))
        super().keyReleaseEvent(e)

    # ------------------------------------------------------------------
    # context menu
    # ------------------------------------------------------------------
    def contextMenuEvent(self, e):
        pos = QPointF(e.pos())
        hit = self._page_at(pos)
        menu = QMenu(self)
        if self._sel:
            menu.addAction(tr("Copy"), self.copy_selection)
            menu.addSeparator()
            menu.addAction(tr("Highlight"), lambda: self.apply_markup("highlight"))
            menu.addAction(tr("Underline"), lambda: self.apply_markup("underline"))
            menu.addAction(tr("Strikeout"), lambda: self.apply_markup("strike"))
        elif hit:
            i, x, y = hit
            a = self._annot_at(i, x, y)
            if a is not None:
                self.select_annot(i, a)
                if a["type"] in ("Text", "FreeText", "Highlight", "Underline", "StrikeOut"):
                    menu.addAction(tr("Edit comment"), self.edit_selected_annot)
                menu.addAction(tr("Delete annotation"), self.delete_selected_annot)
        if menu.isEmpty():
            menu.addAction(tr("Fit width"), lambda: self.set_fit("width"))
            menu.addAction(tr("Fit page"), lambda: self.set_fit("page"))
            menu.addAction(tr("Actual size"), lambda: self.set_zoom(1.0))
        menu.exec(e.globalPos())

    # ------------------------------------------------------------------
    # inline text editor
    # ------------------------------------------------------------------
    def _open_editor(self, i: int, rect: tuple):
        x0, y0, x1, y1 = rect
        z = self.zoom
        r = self._page_view_rect(i)
        size = float(self.opts.get("fontsize", 14))
        color = self.opts.get("color", (0, 0, 0))
        ed = InlineEditor(self.viewport())
        f = ed.font()
        f.setPixelSize(max(8, int(size * z)))
        ed.setFont(f)
        opt = ed.document().defaultTextOption()
        opt.setTextDirection(Qt.LayoutDirection.LayoutDirectionAuto)
        ed.document().setDefaultTextOption(opt)
        ed.setStyleSheet(
            f"QPlainTextEdit {{ background: rgba(255,255,255,235); color: rgb({int(color[0]*255)},{int(color[1]*255)},"
            f"{int(color[2]*255)}); border: 1px dashed {self.accent.name()}; border-radius: 2px; padding: 0px; }}")
        ed.setGeometry(int(r.x() + x0 * z), int(r.y() + y0 * z), max(70, int((x1 - x0) * z)),
                       max(int(size * z * 1.7), int((y1 - y0) * z)))
        ed.committed.connect(self._commit_editor)
        ed.cancelled.connect(self._cancel_editor)
        self._editor = ed
        self._editor_ctx = (i, x0, y0)
        ed.show()
        ed.setFocus()

    def _commit_editor(self):
        ed = self._editor
        if ed is None:
            return
        self._editor = None
        text = ed.toPlainText()
        i, x0, y0 = self._editor_ctx
        z = self.zoom
        need_h = ed.document().size().height()
        w, h = ed.width() / z, max(ed.height(), need_h + 4) / z
        ed.hide()
        ed.deleteLater()
        if text.strip():
            self.pdf.add_text(i, (x0, y0, x0 + w, y0 + h), text, float(self.opts.get("fontsize", 14)),
                              self.opts.get("color", (0, 0, 0)), self.opts.get("fontfile"))
        self.setFocus()

    def _cancel_editor(self):
        ed = self._editor
        if ed is None:
            return
        self._editor = None
        ed.hide()
        ed.deleteLater()
        self.setFocus()

    # ------------------------------------------------------------------
    # image / signature / edit text
    # ------------------------------------------------------------------
    def _place_image(self, i: int, x: float, y: float, rect: tuple | None):
        path = self.opts.get("image_path")
        if not path:
            self.needImage.emit()
            return
        img = QImage(path)
        if img.isNull():
            self.message.emit(tr("Could not read the image"))
            return
        pw, ph = self._sizes[i]
        if rect is None:
            w = min(170.0, pw * 0.5)
            h = w * img.height() / max(1, img.width())
            if h > ph * 0.5:
                h = ph * 0.5
                w = h * img.width() / img.height()
            rect = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
            dx = max(0, -rect[0]) - max(0, rect[2] - pw)
            dy = max(0, -rect[1]) - max(0, rect[3] - ph)
            rect = (rect[0] + dx, rect[1] + dy, rect[2] + dx, rect[3] + dy)
        self.pdf.add_image(i, rect, path)

    def _font_for(self, name: str):
        if self._fonts is None:
            self._fonts = available_fonts()
        key = name.lower().replace(" ", "").replace("-", "")
        for disp, path in self._fonts:
            if path and disp.lower().replace(" ", "") in key:
                return path
        return self.opts.get("fontfile")

    def _edit_text_at(self, i: int, x: float, y: float):
        info = self.pdf.text_line_at(i, x, y)
        if info is None:
            self.message.emit(tr("No text found here"))
            return
        text, ok = QInputDialog.getMultiLineText(self, tr("Edit text"), tr("Text:"), info["text"])
        if ok and text != info["text"]:
            self.pdf.replace_text(i, info["rect"], text, info["size"], info["color"], self._font_for(info["font"]))
