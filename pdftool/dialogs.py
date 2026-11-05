"""Dialogs: signature pad, merge, export, properties."""
from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from .document import PdfDoc
from .i18n import tr

INK = QColor(22, 32, 120)


def _buttons(dlg: QDialog, ok_text: str | None = None) -> QDialogButtonBox:
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    ok = bb.button(QDialogButtonBox.StandardButton.Ok)
    ok.setText(ok_text or tr("OK"))
    ok.setProperty("primary", True)
    bb.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    return bb


class SignaturePad(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.strokes: list[list[QPointF]] = []
        self._cur: list[QPointF] | None = None
        self.setMinimumSize(520, 220)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def clear(self):
        self.strokes = []
        self._cur = None
        self.update()

    def is_empty(self) -> bool:
        return not any(len(s) > 1 for s in self.strokes)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._cur = [QPointF(e.position())]
            self.strokes.append(self._cur)

    def mouseMoveEvent(self, e):
        if self._cur is not None:
            self._cur.append(QPointF(e.position()))
            self.update()

    def mouseReleaseEvent(self, e):
        self._cur = None

    @staticmethod
    def _path(stroke: list[QPointF]) -> QPainterPath:
        path = QPainterPath(stroke[0])
        if len(stroke) == 1:
            path.lineTo(stroke[0] + QPointF(0.1, 0.1))
        for a, b in zip(stroke, stroke[1:]):
            mid = (a + b) / 2
            path.quadTo(a, mid)
        path.lineTo(stroke[-1])
        return path

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        p.setPen(QPen(QColor("#c9ccd6"), 1, Qt.PenStyle.DashLine))
        y = self.height() * 0.72
        p.drawLine(20, int(y), self.width() - 20, int(y))
        pen = QPen(INK, 2.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        for s in self.strokes:
            p.drawPath(self._path(s))

    def save_png(self, path: str) -> bool:
        pts = [pt for s in self.strokes for pt in s]
        if not pts or self.is_empty():
            return False
        xs = [pt.x() for pt in pts]
        ys = [pt.y() for pt in pts]
        m = 8.0
        x0, y0 = min(xs) - m, min(ys) - m
        w, h = max(xs) - x0 + m, max(ys) - y0 + m
        k = 3.0
        img = QImage(int(w * k) + 1, int(h * k) + 1, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(k, k)
        p.translate(-x0, -y0)
        pen = QPen(INK, 2.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        for s in self.strokes:
            p.drawPath(self._path(s))
        p.end()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return img.save(path, "PNG")


class SignatureDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Sign here"))
        lay = QVBoxLayout(self)
        self.pad = SignaturePad()
        lay.addWidget(self.pad)
        row = QHBoxLayout()
        clear = QPushButton(tr("Clear"))
        clear.clicked.connect(self.pad.clear)
        row.addWidget(clear)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(_buttons(self, tr("Use signature")))


class MergeDialog(QDialog):
    def __init__(self, parent=None, start_dir: str = ""):
        super().__init__(parent)
        self.setWindowTitle(tr("Merge PDFs"))
        self.resize(560, 380)
        self._dir = start_dir
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Order of the files:")))
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, fn in ((tr("Add files…"), self._add), (tr("Remove"), self._remove),
                         (tr("Up"), lambda: self._move(-1)), (tr("Down"), lambda: self._move(1))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.bb = _buttons(self, tr("Merge"))
        lay.addWidget(self.bb)

    def _add(self):
        from PySide6.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Add files…"), self._dir, tr("PDF files (*.pdf)"))
        for p in paths:
            self.list.addItem(p)
            self._dir = os.path.dirname(p)

    def _remove(self):
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))

    def _move(self, d: int):
        rows = sorted(self.list.row(i) for i in self.list.selectedItems())
        if len(rows) != 1:
            return
        r = rows[0]
        n = r + d
        if 0 <= n < self.list.count():
            it = self.list.takeItem(r)
            self.list.insertItem(n, it)
            self.list.setCurrentRow(n)

    def files(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]


class ExportDialog(QDialog):
    def __init__(self, parent=None, total: int = 1):
        super().__init__(parent)
        self.setWindowTitle(tr("Export pages as images…"))
        form = QFormLayout(self)
        self.pages = QLineEdit("all")
        self.pages.setPlaceholderText(f"all / 1-{total}")
        self.dpi = QSpinBox()
        self.dpi.setRange(36, 600)
        self.dpi.setValue(150)
        self.fmt = QComboBox()
        self.fmt.addItems(["png", "jpg"])
        form.addRow(tr("Pages to export (e.g. 1-3,5 or all):"), self.pages)
        form.addRow(tr("Resolution (DPI):"), self.dpi)
        form.addRow(tr("Format:"), self.fmt)
        form.addRow(_buttons(self, tr("Export")))

    def values(self):
        return self.pages.text(), self.dpi.value(), self.fmt.currentText()


class PropertiesDialog(QDialog):
    def __init__(self, pdf: PdfDoc, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Properties"))
        self.setMinimumWidth(460)
        meta = pdf.metadata()
        form = QFormLayout(self)
        self.fields = {}
        for key, label in (("title", tr("Title")), ("author", tr("Author")), ("subject", tr("Subject")),
                           ("keywords", tr("Keywords"))):
            e = QLineEdit(meta.get(key) or "")
            self.fields[key] = e
            form.addRow(label, e)
        size = pdf.size
        kb = f"{size / 1024:,.0f} KB" if size < 1024 * 1024 else f"{size / 1048576:,.1f} MB"
        form.addRow(tr("Pages count"), QLabel(str(pdf.page_count)))
        form.addRow(tr("File size"), QLabel(kb))
        if pdf.path:
            lbl = QLabel(pdf.path)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow("", lbl)
        form.addRow(_buttons(self, tr("Apply")))

    def values(self) -> dict:
        return {k: e.text() for k, e in self.fields.items()}
