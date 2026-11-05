"""Side panels: page thumbnails (drag to reorder), outline (bookmarks) and annotations list."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QListView, QListWidget, QListWidgetItem, QTreeWidget,
                               QTreeWidgetItem)

from .document import PdfDoc
from .i18n import tr

ROLE_PAGE = Qt.ItemDataRole.UserRole
ROLE_VER = Qt.ItemDataRole.UserRole + 1


class ThumbnailPanel(QListWidget):
    pageActivated = Signal(int)
    reordered = Signal(list)
    contextRequested = Signal(object)

    W, H = 116, 150

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pdf: PdfDoc | None = None
        self.accent = QColor("#4f6bed")
        self._syncing = False
        self._cur_item: QListWidgetItem | None = None
        self._placeholder = self._make_placeholder()

        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.TopToBottom)
        self.setWrapping(False)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Snap)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setIconSize(QSize(self.W, self.H))
        self.setGridSize(QSize(self.W + 30, self.H + 40))
        self.setSpacing(2)
        self.setUniformItemSizes(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda pos: self.contextRequested.emit(self.mapToGlobal(pos)))
        self.itemClicked.connect(self._clicked)

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(25)
        self._render_timer.timeout.connect(self._render_visible)
        self.verticalScrollBar().valueChanged.connect(lambda _: self._render_timer.start())

        self._order_timer = QTimer(self)
        self._order_timer.setSingleShot(True)
        self._order_timer.setInterval(0)
        self._order_timer.timeout.connect(self._check_order)
        m = self.model()
        m.rowsMoved.connect(lambda *a: self._order_timer.start())
        m.rowsInserted.connect(lambda *a: self._order_timer.start())
        m.rowsRemoved.connect(lambda *a: self._order_timer.start())

    # ---- helpers -----------------------------------------------------
    def _make_placeholder(self) -> QIcon:
        pm = QPixmap(self.W, self.H)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setPen(QPen(QColor(0, 0, 0, 40)))
        p.setBrush(QColor("white"))
        p.drawRect(10, 6, self.W - 20, self.H - 12)
        p.end()
        return QIcon(pm)

    def set_colors(self, accent: str):
        self.accent = QColor(accent)

    def set_document(self, pdf: PdfDoc | None):
        self.pdf = pdf
        self.rebuild()

    def rebuild(self):
        self._syncing = True
        self.clear()
        self._cur_item = None
        if self.pdf is not None:
            for i in range(self.pdf.page_count):
                it = QListWidgetItem(self._placeholder, str(i + 1))
                it.setData(ROLE_PAGE, i)
                it.setData(ROLE_VER, -1)
                it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
                self.addItem(it)
        self._syncing = False
        self._render_timer.start()

    def content_changed(self):
        """Annotations / content changed: keep the items, just re-render the visible thumbnails."""
        if self.pdf is not None and self.count() == self.pdf.page_count:
            self._render_timer.start()
        else:
            self.rebuild()

    def selected_pages(self) -> list[int]:
        return sorted(int(it.data(ROLE_PAGE)) for it in self.selectedItems())

    def set_current(self, i: int):
        if self._cur_item is not None:
            f = self._cur_item.font()
            f.setBold(False)
            self._cur_item.setFont(f)
            self._cur_item.setForeground(self.palette().text())
        if 0 <= i < self.count():
            it = self.item(i)
            f = it.font()
            f.setBold(True)
            it.setFont(f)
            it.setForeground(self.accent)
            self._cur_item = it
            self.scrollToItem(it, QAbstractItemView.ScrollHint.EnsureVisible)
        self._render_timer.start()

    # ---- events --------------------------------------------------------
    def _clicked(self, it: QListWidgetItem):
        if not self._syncing:
            self.pageActivated.emit(int(it.data(ROLE_PAGE)))

    def _check_order(self):
        if self._syncing or self.pdf is None:
            return
        n = self.pdf.page_count
        if self.count() != n:
            return
        order = [int(self.item(r).data(ROLE_PAGE)) for r in range(n)]
        if order != list(range(n)) and sorted(order) == list(range(n)):
            self.reordered.emit(order)

    def _thumb(self, pno: int) -> QPixmap:
        pw, ph = self.pdf.page_sizes()[pno]
        dpr = self.devicePixelRatioF()
        scale = min((self.W - 20) / pw, (self.H - 12) / ph)
        w, h, stride, data = self.pdf.render(pno, scale * dpr)
        img = QImage(data, w, h, stride, QImage.Format.Format_RGB888).convertToFormat(QImage.Format.Format_RGB32)
        pm = QPixmap(int(self.W * dpr), int(self.H * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        lw, lh = w / dpr, h / dpr
        x, y = (self.W - lw) / 2, (self.H - lh) / 2
        p.drawImage(int(x), int(y), img.scaled(int(lw * dpr), int(lh * dpr)) if dpr != 1 else img)
        p.setPen(QPen(QColor(0, 0, 0, 50)))
        p.drawRect(int(x), int(y), int(lw) - 1, int(lh) - 1)
        p.end()
        return pm

    def _render_visible(self):
        if self.pdf is None or self.count() == 0:
            return
        vp = self.viewport()
        first = self.indexAt(vp.rect().topLeft() + vp.rect().center() * 0)
        last = self.indexAt(vp.rect().bottomLeft())
        r0 = first.row() if first.isValid() else 0
        r1 = last.row() if last.isValid() else min(self.count() - 1, r0 + 8)
        r0, r1 = max(0, r0 - 1), min(self.count() - 1, r1 + 2)
        ver = self.pdf.version
        done = 0
        pending = False
        for r in range(r0, r1 + 1):
            it = self.item(r)
            if it.data(ROLE_VER) == ver:
                continue
            if done >= 4:
                pending = True
                break
            try:
                it.setIcon(QIcon(self._thumb(int(it.data(ROLE_PAGE)))))
            except Exception:
                pass
            it.setData(ROLE_VER, ver)
            done += 1
        if pending:
            self._render_timer.start()


class OutlinePanel(QTreeWidget):
    pageRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(14)
        self.itemClicked.connect(self._clicked)

    def set_document(self, pdf: PdfDoc | None):
        self.clear()
        if pdf is None:
            return
        stack: list[tuple[int, QTreeWidgetItem]] = []
        for lvl, title, page in pdf.toc():
            it = QTreeWidgetItem([title])
            it.setData(0, Qt.ItemDataRole.UserRole, int(page) - 1)
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            if stack:
                stack[-1][1].addChild(it)
            else:
                self.addTopLevelItem(it)
            stack.append((lvl, it))
        self.expandToDepth(0)

    def _clicked(self, it: QTreeWidgetItem, _col: int):
        p = it.data(0, Qt.ItemDataRole.UserRole)
        if p is not None and p >= 0:
            self.pageRequested.emit(int(p))


class AnnotationsPanel(QListWidget):
    annotActivated = Signal(int, object, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.itemClicked.connect(self._clicked)

    def set_document(self, pdf: PdfDoc | None):
        self.clear()
        if pdf is None:
            return
        names = {"Highlight": tr("Highlight"), "Underline": tr("Underline"), "StrikeOut": tr("Strikeout"),
                 "Ink": tr("Drawing"), "Text": tr("Comment"), "FreeText": tr("Text"), "Square": tr("Rectangle"),
                 "Circle": tr("Ellipse"), "Line": tr("Line"), "Redact": tr("Redaction")}
        for a in pdf.all_annots():
            label = f"{names.get(a['type'], a['type'])} · {tr('Page')} {a['page'] + 1}"
            if a["content"].strip():
                label += "\n" + a["content"].strip()[:90]
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, (a["page"], a["rect"], a["xref"]))
            self.addItem(it)

    def _clicked(self, it: QListWidgetItem):
        page, rect, xref = it.data(Qt.ItemDataRole.UserRole)
        self.annotActivated.emit(int(page), rect, int(xref))
