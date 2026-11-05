"""Vector icons (Feather-style, drawn from SVG strings) and the application logo."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtSvg import QSvgRenderer

_L = lambda x1, y1, x2, y2: f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>'  # noqa: E731

ICONS: dict[str, str] = {
    "open": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
    "save": '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>'
            '<polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>',
    "undo": '<polyline points="9 14 4 9 9 4"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "redo": '<polyline points="15 14 20 9 15 4"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
    "sidebar": '<rect x="3" y="3" width="18" height="18" rx="2"/>' + _L(9, 3, 9, 21),
    "prev": '<polyline points="18 15 12 9 6 15"/>',
    "next": '<polyline points="6 9 12 15 18 9"/>',
    "zoom_in": '<circle cx="11" cy="11" r="7"/>' + _L(21, 21, 16.65, 16.65) + _L(11, 8, 11, 14) + _L(8, 11, 14, 11),
    "zoom_out": '<circle cx="11" cy="11" r="7"/>' + _L(21, 21, 16.65, 16.65) + _L(8, 11, 14, 11),
    "search": '<circle cx="11" cy="11" r="7"/>' + _L(21, 21, 16.65, 16.65),
    "fit_width": '<polyline points="8 7 3 12 8 17"/><polyline points="16 7 21 12 16 17"/>' + _L(3, 12, 21, 12),
    "fit_page": '<path d="M4 9V5a1 1 0 0 1 1-1h4"/><path d="M15 4h4a1 1 0 0 1 1 1v4"/>'
                '<path d="M20 15v4a1 1 0 0 1-1 1h-4"/><path d="M9 20H5a1 1 0 0 1-1-1v-4"/>',
    "select": '<path d="M5 3l14 8-6.5 1.8L9.5 19z"/>',
    "hand": '<polyline points="5 9 2 12 5 15"/><polyline points="9 5 12 2 15 5"/><polyline points="15 19 12 22 9 19"/>'
            '<polyline points="19 9 22 12 19 15"/>' + _L(2, 12, 22, 12) + _L(12, 2, 12, 22),
    "highlight": '<path d="M15.5 4.5l4 4L11 17l-4-4z"/><path d="M7 13l-2.5 5.5L10 16"/>' + _L(12, 21, 21, 21),
    "underline": '<path d="M6 3v7a6 6 0 0 0 6 6 6 6 0 0 0 6-6V3"/>' + _L(4, 21, 20, 21),
    "strike": '<path d="M16 5.5A4 3 0 0 0 8 7c0 4 8 3 8 8a4 3 0 0 1-8 1.5"/>' + _L(4, 12, 20, 12),
    "text": '<polyline points="4 7 4 4 20 4 20 7"/>' + _L(9, 20, 15, 20) + _L(12, 4, 12, 20),
    "draw": '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>',
    "rect": '<rect x="4" y="5" width="16" height="14" rx="2"/>',
    "ellipse": '<ellipse cx="12" cy="12" rx="9" ry="6.5"/>',
    "line": _L(5, 19, 19, 5),
    "arrow": _L(5, 19, 19, 5) + '<polyline points="9 5 19 5 19 15"/>',
    "note": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/>'
             '<polyline points="21 15 16 10 5 21"/>',
    "signature": '<path d="M3 16c2.5-6 4-7 5-4s1 4 3 1 3-5 4-2 2 4 4 1"/>' + _L(3, 21, 21, 21),
    "redact": '<rect x="3" y="8" width="18" height="8" rx="1" fill="currentColor"/>',
    "edittext": '<path d="M4 7V5h12v2"/>' + _L(10, 5, 10, 16) + _L(8, 16, 12, 16) +
                '<path d="M14 20l2-.5 5-5a1.4 1.4 0 0 0-2-2l-5 5z"/>',
    "trash": '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>'
             + _L(10, 11, 10, 17) + _L(14, 11, 14, 17) + '<path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
    "rotate_cw": '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
    "rotate_ccw": '<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>',
    "sun": '<circle cx="12" cy="12" r="4"/>' + _L(12, 1, 12, 3) + _L(12, 21, 12, 23) + _L(4.22, 4.22, 5.64, 5.64)
           + _L(18.36, 18.36, 19.78, 19.78) + _L(1, 12, 3, 12) + _L(21, 12, 23, 12) + _L(4.22, 19.78, 5.64, 18.36)
           + _L(18.36, 5.64, 19.78, 4.22),
    "moon": '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
    "file_plus": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>'
                 + _L(12, 12, 12, 18) + _L(9, 15, 15, 15),
    "print": '<polyline points="6 9 6 2 18 2 18 9"/>'
             '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>'
             '<rect x="6" y="14" width="12" height="8"/>',
    "close": _L(18, 6, 6, 18) + _L(6, 6, 18, 18),
    "merge": '<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/>',
    "menu": _L(3, 6, 21, 6) + _L(3, 12, 21, 12) + _L(3, 18, 21, 18),
    "lock": '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "fullscreen": '<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>',
    "copy": '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "info": '<circle cx="12" cy="12" r="10"/>' + _L(12, 16, 12, 12) + _L(12, 8, 12.01, 8),
    "pages": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>'
             '<rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
    "list": _L(8, 6, 21, 6) + _L(8, 12, 21, 12) + _L(8, 18, 21, 18) + _L(3, 6, 3.01, 6) + _L(3, 12, 3.01, 12)
            + _L(3, 18, 3.01, 18),
    "invert": '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor"/>',
    "export": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/>' + _L(12, 15, 12, 3),
    "scissors": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/>' + _L(20, 4, 8.12, 15.88)
                + _L(14.47, 14.48, 20, 20) + _L(8.12, 8.12, 12, 12),
    "plus": _L(12, 5, 12, 19) + _L(5, 12, 19, 12),
    "chevron_left": '<polyline points="15 18 9 12 15 6"/>',
    "chevron_right": '<polyline points="9 18 15 12 9 6"/>',
}


@lru_cache(maxsize=2048)
def _pixmap(name: str, color: str, px: int) -> QPixmap:
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
           'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + ICONS[name] + "</svg>")
    svg = svg.replace("currentColor", color)
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, px, px))
    p.end()
    return pm


def make_icon(name: str, normal: str, disabled: str, active: str | None = None, px: int = 64) -> QIcon:
    ic = QIcon()
    on = active or normal
    ic.addPixmap(_pixmap(name, normal, px), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(_pixmap(name, normal, px), QIcon.Mode.Active, QIcon.State.Off)
    ic.addPixmap(_pixmap(name, disabled, px), QIcon.Mode.Disabled, QIcon.State.Off)
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
        ic.addPixmap(_pixmap(name, on, px), mode, QIcon.State.On)
    return ic


def pixmap(name: str, color: str, px: int = 24) -> QPixmap:
    return _pixmap(name, color, px)


def app_icon() -> QIcon:
    """Application logo drawn in code: indigo gradient tile with a folded page."""
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = float(size)
        g = QLinearGradient(0, 0, s, s)
        g.setColorAt(0, QColor("#5b7cfa"))
        g.setColorAt(1, QColor("#7c4dff"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(QRectF(s * 0.04, s * 0.04, s * 0.92, s * 0.92), s * 0.22, s * 0.22)
        # page with folded corner
        x0, y0, x1, y1 = s * 0.28, s * 0.18, s * 0.72, s * 0.82
        fold = s * 0.16
        path = QPainterPath()
        path.moveTo(x0, y0)
        path.lineTo(x1 - fold, y0)
        path.lineTo(x1, y0 + fold)
        path.lineTo(x1, y1)
        path.lineTo(x0, y1)
        path.closeSubpath()
        p.setBrush(QColor("white"))
        p.drawPath(path)
        p.setBrush(QColor(0, 0, 0, 40))
        tri = QPainterPath()
        tri.moveTo(x1 - fold, y0)
        tri.lineTo(x1 - fold, y0 + fold)
        tri.lineTo(x1, y0 + fold)
        tri.closeSubpath()
        p.drawPath(tri)
        # text lines
        p.setBrush(QColor("#5b7cfa"))
        for k in range(3):
            yy = s * (0.46 + k * 0.1)
            p.drawRoundedRect(QRectF(x0 + s * 0.06, yy, (x1 - x0) - s * 0.12 - (s * 0.08 if k == 2 else 0), s * 0.035),
                              s * 0.018, s * 0.018)
        p.end()
        ic.addPixmap(pm)
    return ic
