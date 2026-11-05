"""Main window: tabs, toolbars, menus, start page."""
from __future__ import annotations

import os

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QActionGroup, QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap,
                           QShortcut)
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressDialog,
                               QPushButton, QSizePolicy, QSpinBox, QSplitter, QStackedWidget, QTabBar, QTabWidget, QToolBar,
                               QToolButton, QVBoxLayout, QWidget)

from . import __version__
from .dialogs import ExportDialog, MergeDialog, PropertiesDialog, SignatureDialog
from .document import PasswordRequired, PdfDoc, PdfError, available_fonts, merge_files, parse_ranges
from .i18n import language, tr
from .icons import app_icon, make_icon, pixmap
from .panels import AnnotationsPanel, OutlinePanel, ThumbnailPanel
from .theme import SWATCHES, THEMES, apply_theme
from .view import MARKUP, DocumentView

PDF_FILTER = "PDF files (*.pdf)"
ZOOM_STEPS = [25, 50, 75, 100, 125, 150, 200, 300, 400]

TOOLS = [  # key, icon, label, hint
    ("select", "select", "Select", "Select text, then use Highlight / Underline / Strikeout"),
    ("hand", "hand", "Pan", ""),
    ("highlight", "highlight", "Highlight", "Select text, then use Highlight / Underline / Strikeout"),
    ("underline", "underline", "Underline", "Select text, then use Highlight / Underline / Strikeout"),
    ("strike", "strike", "Strikeout", "Select text, then use Highlight / Underline / Strikeout"),
    ("text", "text", "Text", "Click and drag to write text. Ctrl+Enter to finish"),
    ("edittext", "edittext", "Edit text", "Click a line of text to edit it"),
    ("draw", "draw", "Draw", ""),
    ("rect", "rect", "Rectangle", ""),
    ("ellipse", "ellipse", "Ellipse", ""),
    ("line", "line", "Line", ""),
    ("arrow", "arrow", "Arrow", ""),
    ("note", "note", "Comment", ""),
    ("image", "image", "Image", ""),
    ("signature", "signature", "Signature", ""),
    ("redact", "redact", "Redact", "Black out an area permanently (the text underneath is removed)"),
]


def sig_path() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation) or os.path.expanduser("~")
    return os.path.join(base, "signature.png")


def _circle(color: str, px: int = 20) -> QIcon:
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(0, 0, 0, 70), 1))
    p.setBrush(QColor(color))
    p.drawEllipse(2, 2, px - 4, px - 4)
    p.end()
    return QIcon(pm)


# ----------------------------------------------------------------------------
class DocTab(QWidget):
    changed = Signal(str)

    def __init__(self, pdf: PdfDoc, opts: dict, parent=None):
        super().__init__(parent)
        self.pdf = pdf
        self.view = DocumentView(pdf, opts)
        self.thumbs = ThumbnailPanel()
        self.outline = OutlinePanel()
        self.annots = AnnotationsPanel()
        self._hits: dict = {}
        self._flat: list = []
        self._idx = -1

        self.side = QTabWidget()
        self.side.setDocumentMode(True)
        self.side.tabBar().setObjectName("side")
        for i, (w, name) in enumerate(((self.thumbs, "Thumbnails"), (self.outline, "Outline"),
                                       (self.annots, "Annotations"))):
            self.side.addTab(w, "")
            self.side.setTabToolTip(i, tr(name))
        self.side.tabBar().setUsesScrollButtons(False)
        self.side.tabBar().setExpanding(True)
        self.side.tabBar().setDrawBase(False)
        self.side.setMinimumWidth(190)
        self.side.setMaximumWidth(360)

        self.search_bar = QFrame()
        self.search_bar.setObjectName("searchBar")
        sl = QHBoxLayout(self.search_bar)
        sl.setContentsMargins(10, 6, 10, 6)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("Find in document"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_lbl = QLabel("")
        self.search_lbl.setObjectName("muted")
        self.btn_prev = QToolButton()
        self.btn_next = QToolButton()
        self.btn_close = QToolButton()
        sl.addWidget(self.search_edit, 1)
        sl.addWidget(self.search_lbl)
        for b in (self.btn_prev, self.btn_next, self.btn_close):
            sl.addWidget(b)
        self.search_bar.hide()

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.search_bar)
        rl.addWidget(self.view, 1)

        self.splitter = QSplitter()
        self.splitter.addWidget(self.side)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([230, 900])
        self.splitter.setChildrenCollapsible(False)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.splitter)

        self.thumbs.set_document(pdf)
        self.outline.set_document(pdf)
        self.annots.set_document(pdf)
        self.outline_present = bool(pdf.toc())

        self.thumbs.pageActivated.connect(self.view.go_to_page)
        self.thumbs.reordered.connect(self._reorder)
        self.outline.pageRequested.connect(self.view.go_to_page)
        self.annots.annotActivated.connect(self._goto_annot)
        self.view.pageChanged.connect(self.thumbs.set_current)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.run_search)
        self.search_edit.textChanged.connect(lambda _: self._timer.start())
        self.search_edit.returnPressed.connect(lambda: self.step(1))
        self.btn_next.clicked.connect(lambda: self.step(1))
        self.btn_prev.clicked.connect(lambda: self.step(-1))
        self.btn_close.clicked.connect(self.hide_search)
        sc = QShortcut(QKeySequence("Escape"), self.search_edit)
        sc.setContext(Qt.ShortcutContext.WidgetShortcut)
        sc.activated.connect(self.hide_search)

        pdf.add_listener(self._on_pdf)
        self.thumbs.set_current(0)

    # ---- plumbing -------------------------------------------------------
    def apply_icons(self, mk):
        self.btn_prev.setIcon(mk("prev"))
        self.btn_next.setIcon(mk("next"))
        self.btn_close.setIcon(mk("close"))
        self.side.setTabIcon(0, mk("pages"))
        self.side.setTabIcon(1, mk("list"))
        self.side.setTabIcon(2, mk("note"))

    def set_colors(self, canvas: str, accent: str):
        self.view.set_colors(canvas, accent)
        self.thumbs.set_colors(accent)
        self.thumbs.set_current(self.view.current_page)

    def shutdown(self):
        self.pdf.remove_listener(self._on_pdf)
        self.view.close_view()
        self.pdf.close()

    def _on_pdf(self, kind: str):
        if kind == "structure":
            self.thumbs.rebuild()
            self.outline.set_document(self.pdf)
            self.thumbs.set_current(self.view.current_page)
        elif kind != "meta":
            self.thumbs.content_changed()
        self.annots.set_document(self.pdf)
        self._hits, self._flat, self._idx = {}, [], -1
        if self.search_bar.isVisible() and self.search_edit.text().strip():
            QTimer.singleShot(0, self.run_search)
        self.changed.emit(kind)

    def _reorder(self, order: list):
        try:
            self.pdf.reorder(order)
        except PdfError:
            self.thumbs.rebuild()

    def _goto_annot(self, page: int, rect, xref: int):
        self.view.go_to_page(page)
        self.view.ensure_visible_rect(page, rect)
        a = next((a for a in self.pdf.annots(page) if a["xref"] == xref), None)
        if a is not None:
            self.view.select_annot(page, a)

    # ---- search -----------------------------------------------------------
    def show_search(self):
        self.search_bar.show()
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def hide_search(self):
        self.search_bar.hide()
        self._hits, self._flat, self._idx = {}, [], -1
        self.view.set_search({}, None)
        self.view.setFocus()

    def run_search(self):
        q = self.search_edit.text().strip()
        self._hits, self._flat = {}, []
        if q:
            for p in range(self.pdf.page_count):
                rs = self.pdf.search(p, q)
                if rs:
                    self._hits[p] = rs
                    self._flat += [(p, k) for k in range(len(rs))]
        self._idx = 0 if self._flat else -1
        self._show_hit(True)

    def step(self, d: int):
        if not self._flat:
            return
        self._idx = (self._idx + d) % len(self._flat)
        self._show_hit(True)

    def _show_hit(self, jump: bool):
        cur = self._flat[self._idx] if self._idx >= 0 else None
        self.view.set_search(self._hits, cur)
        if cur:
            self.search_lbl.setText(f"{self._idx + 1} {tr('of')} {len(self._flat)}")
            if jump:
                self.view.ensure_visible_rect(cur[0], self._hits[cur[0]][cur[1]])
        else:
            self.search_lbl.setText(tr("No results") if self.search_edit.text().strip() else "")


# ----------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, app: QApplication, settings: QSettings):
        super().__init__()
        self.app = app
        self.s = settings
        self.theme = self.s.value("theme", "light")
        if self.theme not in THEMES:
            self.theme = "light"
        self.tool = "select"
        self._syncing = False
        self.A: dict[str, QAction] = {}
        self._icon_of: dict[str, str] = {}
        self.opts: dict = {"color": (1.0, 0.23, 0.19), "width": 2, "opacity": 1.0, "fill": False, "fontsize": 14,
                           "fontfile": None, "image_path": None, "tool_colors": {}}
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        self.resize(1280, 820)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(False)  # we draw our own, theme-aware close buttons
        self.tabs.setMovable(True)
        self.tabs.tabBar().setObjectName("docs")
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(lambda _: self._sync())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_start())
        self.stack.addWidget(self.tabs)
        self.setCentralWidget(self.stack)

        self._make_actions()
        self._make_menus()
        self._make_toolbars()
        self.lbl_info = QLabel("")
        self.statusBar().addPermanentWidget(self.lbl_info)
        self._apply_theme(initial=True)
        self._refresh_recent()
        self._sync()
        g = self.s.value("geometry")
        if g:
            self.restoreGeometry(g)

    # ------------------------------------------------------------------
    # build
    # ------------------------------------------------------------------
    def cur(self) -> DocTab | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, DocTab) else None

    def _act(self, key, text, icon=None, shortcut=None, slot=None, checkable=False):
        a = QAction(text, self)
        a.setCheckable(checkable)
        if shortcut:
            seqs = [QKeySequence(s) for s in (shortcut if isinstance(shortcut, list) else [shortcut])]
            a.setShortcuts(seqs)
        if slot:
            a.triggered.connect(lambda *_: slot())
        self.A[key] = a
        if icon:
            self._icon_of[key] = icon
        return a

    def _make_actions(self):
        t = self._act
        t("open", tr("Open…"), "open", QKeySequence.StandardKey.Open, self.open_dialog)
        t("new", tr("New blank PDF"), "file_plus", "Ctrl+N", self.new_blank)
        t("save", tr("Save"), "save", QKeySequence.StandardKey.Save, self.save)
        t("save_as", tr("Save as…"), None, "Ctrl+Shift+S", self.save_as)
        t("save_opt", tr("Save optimized…"), None, None, lambda: self.save_as(optimize=True))
        t("export_img", tr("Export pages as images…"), "image", None, self.export_images)
        t("extract", tr("Extract pages…"), "scissors", None, self.extract_pages)
        t("merge", tr("Merge files…"), "merge", None, self.merge_dialog)
        t("insert_pdf", tr("Insert PDF…"), "plus", None, self.insert_pdf)
        t("props", tr("Document properties…"), "info", None, self.properties)
        t("password", tr("Set password…"), "lock", None, self.set_password)
        t("close_tab", tr("Close tab"), None, "Ctrl+W", lambda: self.close_tab(self.tabs.currentIndex()))
        t("quit", tr("Quit"), None, "Ctrl+Q", self.close)
        t("undo", tr("Undo"), "undo", QKeySequence.StandardKey.Undo, self.undo)
        t("redo", tr("Redo"), "redo", [QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")], self.redo)
        t("find", tr("Find"), "search", QKeySequence.StandardKey.Find, self.find)
        t("new_sig", tr("Draw signature…"), "signature", None, lambda: self._draw_signature())
        t("rot_cw", tr("Rotate right"), "rotate_cw", "Ctrl+]", lambda: self.rotate(90))
        t("rot_ccw", tr("Rotate left"), "rotate_ccw", "Ctrl+[", lambda: self.rotate(-90))
        t("del_pages", tr("Delete pages"), "trash", "Ctrl+Del", self.delete_pages)
        t("dup_pages", tr("Duplicate pages"), "copy", None, self.duplicate_pages)
        t("blank_page", tr("Insert blank page"), "file_plus", None, self.insert_blank)
        t("extract_sel", tr("Extract selected pages…"), "scissors", None, lambda: self.extract_pages(True))
        t("zoom_in", tr("Zoom in"), "zoom_in", [QKeySequence.StandardKey.ZoomIn, QKeySequence("Ctrl+=")], self.zoom_in)
        t("zoom_out", tr("Zoom out"), "zoom_out", QKeySequence.StandardKey.ZoomOut, self.zoom_out)
        t("fit_w", tr("Fit width"), "fit_width", "Ctrl+1", lambda: self._fit("width"))
        t("fit_p", tr("Fit page"), "fit_page", "Ctrl+2", lambda: self._fit("page"))
        t("actual", tr("Actual size"), None, "Ctrl+0", lambda: self._zoom_to(1.0))
        t("invert", tr("Dark reading mode (invert page)"), "invert", None, self.toggle_invert, True)
        t("sidebar", tr("Sidebar"), "sidebar", "F4", self.toggle_sidebar)
        t("theme", tr("Toggle theme"), "moon", None, self.toggle_theme)
        t("fullscreen", tr("Full screen"), "fullscreen", "F11", self.toggle_fullscreen)
        t("prev", tr("Previous page"), "prev", "Alt+Up", lambda: self._page_step(-1))
        t("next", tr("Next page"), "next", "Alt+Down", lambda: self._page_step(1))
        t("lang_en", "English", None, None, lambda: self.set_lang("en"))
        t("lang_ar", "العربية", None, None, lambda: self.set_lang("ar"))
        t("about", tr("About"), "info", None, self.about)
        self.A["invert"].setToolTip(tr("Dark reading mode (invert page)"))
        # tools
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        for key, icon, label, _hint in TOOLS:
            a = t("tool_" + key, tr(label), icon, None, lambda k=key: self._on_tool(k), True)
            a.setToolTip(tr(label))
            self.tool_group.addAction(a)
        self.A["tool_select"].setChecked(True)
        # colours
        self.swatch_group = QActionGroup(self)
        self.swatch_group.setExclusive(True)
        self.swatches: list[QAction] = []
        for i, col in enumerate(SWATCHES):
            a = QAction(_circle(col), tr("Colour"), self)
            a.setCheckable(True)
            a.setToolTip(tr("Colour"))
            a.triggered.connect(lambda *_, c=col: self._set_color(c))
            self.swatch_group.addAction(a)
            self.swatches.append(a)

    def _make_menus(self):
        A = self.A
        mb = self.menuBar()
        m = mb.addMenu(tr("&File"))
        for k in ("open", "new"):
            m.addAction(A[k])
        m.addSeparator()
        for k in ("save", "save_as", "save_opt"):
            m.addAction(A[k])
        m.addSeparator()
        for k in ("export_img", "extract", "merge", "insert_pdf"):
            m.addAction(A[k])
        m.addSeparator()
        for k in ("props", "password"):
            m.addAction(A[k])
        m.addSeparator()
        self.recent_menu = m.addMenu(tr("Recent files"))
        m.addSeparator()
        for k in ("close_tab", "quit"):
            m.addAction(A[k])
        m = mb.addMenu(tr("&Edit"))
        for k in ("undo", "redo"):
            m.addAction(A[k])
        m.addSeparator()
        m.addAction(A["find"])
        m.addAction(A["new_sig"])
        m = mb.addMenu(tr("&Pages"))
        for k in ("rot_cw", "rot_ccw", "del_pages", "dup_pages", "blank_page", "extract_sel"):
            m.addAction(A[k])
        m = mb.addMenu(tr("&View"))
        for k in ("zoom_in", "zoom_out", "fit_w", "fit_p", "actual"):
            m.addAction(A[k])
        m.addSeparator()
        for k in ("prev", "next", "invert", "sidebar", "theme", "fullscreen"):
            m.addAction(A[k])
        lm = m.addMenu(tr("Language"))
        lm.addAction(A["lang_en"])
        lm.addAction(A["lang_ar"])
        m = mb.addMenu(tr("&Help"))
        m.addAction(A["about"])

    def _make_toolbars(self):
        A = self.A
        tb = QToolBar("main")
        tb.setObjectName("main")
        tb.setMovable(False)
        tb.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        self.tb = tb
        for k in ("open", "save"):
            tb.addAction(A[k])
        tb.addSeparator()
        tb.addAction(A["undo"])
        tb.addAction(A["redo"])
        tb.addSeparator()
        tb.addAction(A["sidebar"])
        tb.addAction(A["prev"])
        self.spin = QSpinBox()
        self.spin.setMinimum(1)
        self.spin.setMaximum(1)
        self.spin.setFixedWidth(62)
        self.spin.setKeyboardTracking(False)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin.valueChanged.connect(self._on_spin)
        tb.addWidget(self.spin)
        self.lbl_total = QLabel(" / 1 ")
        tb.addWidget(self.lbl_total)
        tb.addAction(A["next"])
        tb.addSeparator()
        tb.addAction(A["zoom_out"])
        self.zoom_box = QComboBox()
        self.zoom_box.setEditable(True)
        self.zoom_box.setFixedWidth(92)
        self.zoom_box.addItems([f"{z}%" for z in ZOOM_STEPS])
        self.zoom_box.setCurrentText("100%")
        self.zoom_box.activated.connect(lambda _: self._zoom_from_box())
        self.zoom_box.lineEdit().returnPressed.connect(self._zoom_from_box)
        tb.addWidget(self.zoom_box)
        tb.addAction(A["zoom_in"])
        tb.addAction(A["fit_w"])
        tb.addAction(A["fit_p"])
        tb.addSeparator()
        tb.addAction(A["find"])
        tb.addAction(A["invert"])
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(A["theme"])

        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        tools = QToolBar("tools")
        tools.setObjectName("tools")
        tools.setMovable(False)
        tools.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tools)
        self.tools_tb = tools
        for key, *_ in TOOLS:
            tools.addAction(A["tool_" + key])
            if key in ("hand", "strike", "edittext", "arrow"):
                tools.addSeparator()
        for a in self.swatches:
            tools.addAction(a)
            w = tools.widgetForAction(a)
            w.setProperty("swatch", True)
        tools.addSeparator()
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 30)
        self.width_spin.setValue(2)
        self.width_spin.setPrefix("◦ ")
        self.width_spin.setToolTip(tr("Width"))
        self.width_spin.setFixedWidth(64)
        self.width_spin.valueChanged.connect(lambda v: self.opts.__setitem__("width", v))
        tools.addWidget(self.width_spin)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 144)
        self.size_spin.setValue(14)
        self.size_spin.setSuffix(" pt")
        self.size_spin.setToolTip(tr("Font size"))
        self.size_spin.setFixedWidth(76)
        self.size_spin.valueChanged.connect(lambda v: self.opts.__setitem__("fontsize", v))
        tools.addWidget(self.size_spin)
        self.font_box = QComboBox()
        self.font_box.setToolTip(tr("Font") + " — " + tr("Fonts that cover Arabic are used automatically"))
        for name, path in available_fonts():
            self.font_box.addItem(name, path)
        self.font_box.setFixedWidth(130)
        self.font_box.currentIndexChanged.connect(lambda _: self.opts.__setitem__("fontfile", self.font_box.currentData()))
        tools.addWidget(self.font_box)

    def _build_start(self) -> QWidget:
        w = QWidget()
        w.setObjectName("startPage")
        outer = QVBoxLayout(w)
        outer.addStretch(1)
        col = QWidget()
        col.setMaximumWidth(620)
        cl = QVBoxLayout(col)
        cl.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(84, 84))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel(tr("PDF Toolkit"))
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel(tr("Open, read and edit PDF files"))
        sub.setObjectName("subtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(logo)
        cl.addWidget(title)
        cl.addWidget(sub)
        cl.addSpacing(14)
        self.start_buttons = []
        for text, sub_t, slot, icon in (
                (tr("Open a PDF"), tr("Choose a file from your computer"), self.open_dialog, "open"),
                (tr("Merge PDFs"), tr("Combine several files into one"), self.merge_dialog, "merge"),
                (tr("New blank document"), tr("Start from an empty page"), self.new_blank, "file_plus")):
            b = QPushButton(f"{text}\n{sub_t}")
            b.setProperty("card", True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setIconSize(pixmap("open", "#000", 28).size())
            b.clicked.connect(lambda *_, s=slot: s())
            cl.addWidget(b)
            self.start_buttons.append((b, icon))
        cl.addSpacing(10)
        rl = QLabel(tr("Recent files"))
        rl.setObjectName("muted")
        cl.addWidget(rl)
        self.recent_list = QListWidget()
        self.recent_list.setObjectName("recent")
        self.recent_list.setMaximumHeight(210)
        self.recent_list.itemClicked.connect(lambda it: self.open_path(it.data(Qt.ItemDataRole.UserRole)))
        cl.addWidget(self.recent_list)
        hint = QLabel(tr("Drop a PDF here to open it"))
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(hint)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(col, 10)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(2)
        return w

    # ------------------------------------------------------------------
    # theme / icons
    # ------------------------------------------------------------------
    def mk(self, name: str) -> QIcon:
        c = THEMES[self.theme]
        return make_icon(name, c["icon"], c["icon_dis"], c["accent"])

    def _apply_theme(self, initial: bool = False):
        apply_theme(self.app, self.theme)
        c = THEMES[self.theme]
        for key, icon in self._icon_of.items():
            if key == "theme":
                icon = "sun" if self.theme == "dark" else "moon"
            self.A[key].setIcon(self.mk(icon))
        for b, icon in self.start_buttons:
            b.setIcon(self.mk(icon))
        for i, tab in enumerate(self._tabs()):
            tab.apply_icons(self.mk)
            tab.set_colors(c["canvas"], c["accent"])
            b = self.tabs.tabBar().tabButton(i, QTabBar.ButtonPosition.RightSide)
            if isinstance(b, QToolButton):
                b.setIcon(self.mk("close"))
        for w in (self.tools_tb, self.tb):
            w.style().unpolish(w)
            w.style().polish(w)
        for a in self.swatches:
            wd = self.tools_tb.widgetForAction(a)
            if wd is not None:
                wd.style().unpolish(wd)
                wd.style().polish(wd)
        self.A["theme"].setToolTip(tr("Light theme") if self.theme == "dark" else tr("Dark theme"))

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.s.setValue("theme", self.theme)
        self._apply_theme()

    def set_lang(self, lang: str):
        self.s.setValue("lang", lang)
        QMessageBox.information(self, "PDF Toolkit", tr("Restart the app to apply the language"))

    # ------------------------------------------------------------------
    # tabs / files
    # ------------------------------------------------------------------
    def _tabs(self) -> list[DocTab]:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def _add_tab(self, pdf: PdfDoc):
        tab = DocTab(pdf, self.opts)
        c = THEMES[self.theme]
        tab.apply_icons(self.mk)
        tab.set_colors(c["canvas"], c["accent"])
        tab.view.set_tool(self.tool)
        tab.view.invert = self.A["invert"].isChecked()
        tab.changed.connect(lambda kind, t=tab: self._on_changed(t, kind))
        tab.view.pageChanged.connect(lambda i, t=tab: self._on_page(t, i))
        tab.view.zoomChanged.connect(lambda z, t=tab: self._on_zoom(t, z))
        tab.view.message.connect(lambda m: self.statusBar().showMessage(m, 4000))
        tab.view.needImage.connect(lambda: self._on_tool(self.tool))
        if not pdf.toc():
            tab.side.setCurrentIndex(0)
        idx = self.tabs.addTab(tab, pdf.title)
        self.tabs.setTabToolTip(idx, pdf.path or "")
        btn = QToolButton()
        btn.setAutoRaise(True)
        btn.setIcon(self.mk("close"))
        btn.setToolTip(tr("Close tab"))
        btn.clicked.connect(lambda _=False, t=tab: self.close_tab(self.tabs.indexOf(t)))
        self.tabs.tabBar().setTabButton(idx, QTabBar.ButtonPosition.RightSide, btn)
        self.tabs.setCurrentIndex(idx)
        QTimer.singleShot(0, lambda: tab.view.set_fit("width"))
        self._sync()

    def open_dialog(self):
        start = self.s.value("last_dir", "") or ""
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Open…"), start, f"{tr(PDF_FILTER)};;{tr('All files (*)')}")
        for p in paths:
            self.open_path(p)

    def open_path(self, path: str, password: str | None = None):
        path = os.path.abspath(path)
        for i, t in enumerate(self._tabs()):
            if t.pdf.path and os.path.abspath(t.pdf.path) == path:
                self.tabs.setCurrentIndex(i)
                return
        if not os.path.isfile(path):
            QMessageBox.warning(self, tr("Error"), f"{tr('Could not open the file')}\n{path}")
            self._forget_recent(path)
            return
        pw = password
        while True:
            try:
                pdf = PdfDoc.open(path, pw)
                break
            except PasswordRequired:
                pw, ok = QInputDialog.getText(self, tr("This file is protected"), tr("Enter the password to open it:"),
                                              QLineEdit.EchoMode.Password)
                if not ok:
                    return
            except Exception as e:  # noqa: BLE001
                QMessageBox.critical(self, tr("Error"), f"{tr('Could not open the file')}\n{path}\n\n{e}")
                return
        self.s.setValue("last_dir", os.path.dirname(path))
        self._add_recent(path)
        self._add_tab(pdf)

    def new_blank(self):
        self._add_tab(PdfDoc.blank())

    def close_tab(self, idx: int):
        if idx < 0:
            return
        tab = self.tabs.widget(idx)
        if not isinstance(tab, DocTab):
            return
        if tab.pdf.modified:
            r = QMessageBox.question(self, tr("Unsaved changes"), tr("Save changes to {name} before closing?", name=tab.pdf.title),
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                                     QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                return False
            if r == QMessageBox.StandardButton.Save:
                self.tabs.setCurrentIndex(idx)
                if not self.save():
                    return False
        self.tabs.removeTab(idx)
        tab.shutdown()
        tab.deleteLater()
        self._sync()
        return True

    def closeEvent(self, e):
        while self.tabs.count():
            if self.close_tab(self.tabs.count() - 1) is False:
                e.ignore()
                return
        self.s.setValue("geometry", self.saveGeometry())
        e.accept()

    # ---- recent -----------------------------------------------------------
    def _recent(self) -> list[str]:
        v = self.s.value("recent", [])
        if isinstance(v, str):
            v = [v]
        return [p for p in (v or []) if p]

    def _add_recent(self, path: str):
        r = [p for p in self._recent() if p != path]
        r.insert(0, path)
        self.s.setValue("recent", r[:10])
        self._refresh_recent()

    def _forget_recent(self, path: str):
        self.s.setValue("recent", [p for p in self._recent() if p != path])
        self._refresh_recent()

    def _refresh_recent(self):
        self.recent_list.clear()
        self.recent_menu.clear()
        r = [p for p in self._recent() if os.path.isfile(p)]
        if not r:
            it = QListWidgetItem(tr("No recent files yet"))
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(it)
        for p in r:
            it = QListWidgetItem(f"{os.path.basename(p)}\n{os.path.dirname(p)}")
            it.setData(Qt.ItemDataRole.UserRole, p)
            it.setToolTip(p)
            self.recent_list.addItem(it)
            self.recent_menu.addAction(os.path.basename(p), lambda p=p: self.open_path(p))
        self.recent_menu.setEnabled(bool(r))

    # ---- drag and drop ------------------------------------------------------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith(".pdf") for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if p.lower().endswith(".pdf"):
                self.open_path(p)

    # ------------------------------------------------------------------
    # saving
    # ------------------------------------------------------------------
    def save(self) -> bool:
        tab = self.cur()
        if tab is None:
            return False
        if not tab.pdf.path:
            return self.save_as()
        try:
            tab.pdf.save()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, tr("Error"), str(e))
            return False
        self.statusBar().showMessage(tr("Saved to {path}", path=tab.pdf.path), 4000)
        return True

    def save_as(self, optimize: bool = False) -> bool:
        tab = self.cur()
        if tab is None:
            return False
        start = tab.pdf.path or os.path.join(self.s.value("last_dir", "") or "", tab.pdf.title)
        path, _ = QFileDialog.getSaveFileName(self, tr("Save as…"), start, tr(PDF_FILTER))
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            tab.pdf.save(path, optimize=optimize)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, tr("Error"), str(e))
            return False
        self.tabs.setTabToolTip(self.tabs.indexOf(tab), path)
        self._add_recent(path)
        self.statusBar().showMessage(tr("Saved to {path}", path=path), 4000)
        return True

    # ------------------------------------------------------------------
    # editing commands
    # ------------------------------------------------------------------
    def undo(self):
        t = self.cur()
        if t:
            t.pdf.undo()

    def redo(self):
        t = self.cur()
        if t:
            t.pdf.redo()

    def find(self):
        t = self.cur()
        if t:
            t.show_search()

    def _pages(self) -> list[int]:
        t = self.cur()
        if t is None:
            return []
        sel = t.thumbs.selected_pages()
        return sel or [t.view.current_page]

    def _guard(self, fn, *a):
        try:
            return fn(*a)
        except PdfError as e:
            QMessageBox.warning(self, tr("Error"), tr(str(e)))
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, tr("Error"), str(e))

    def rotate(self, d: int):
        t = self.cur()
        if t:
            self._guard(t.pdf.rotate_pages, self._pages(), d)

    def delete_pages(self):
        t = self.cur()
        if not t:
            return
        pages = self._pages()
        if QMessageBox.question(self, tr("Delete pages"), tr("Delete {n} page(s)?", n=len(pages))) == QMessageBox.StandardButton.Yes:
            self._guard(t.pdf.delete_pages, pages)

    def duplicate_pages(self):
        t = self.cur()
        if t:
            self._guard(t.pdf.duplicate_pages, self._pages())

    def insert_blank(self):
        t = self.cur()
        if t:
            self._guard(t.pdf.insert_blank, max(self._pages()))

    def extract_pages(self, selected: bool = False):
        t = self.cur()
        if not t:
            return
        if selected:
            idxs = self._pages()
        else:
            spec, ok = QInputDialog.getText(self, tr("Extract pages…"), tr("Pages to extract (e.g. 1-3,5,8-):"))
            if not ok:
                return
            try:
                idxs = parse_ranges(spec, t.pdf.page_count)
            except ValueError:
                QMessageBox.warning(self, tr("Error"), tr("Invalid page range"))
                return
        path, _ = QFileDialog.getSaveFileName(self, tr("Extract pages…"), "", tr(PDF_FILTER))
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        self._guard(t.pdf.extract_to, idxs, path)
        self.statusBar().showMessage(tr("Extracted {n} pages", n=len(idxs)), 4000)

    def export_images(self):
        t = self.cur()
        if not t:
            return
        dlg = ExportDialog(self, t.pdf.page_count)
        if not dlg.exec():
            return
        spec, dpi, fmt = dlg.values()
        try:
            idxs = parse_ranges(spec, t.pdf.page_count)
        except ValueError:
            QMessageBox.warning(self, tr("Error"), tr("Invalid page range"))
            return
        folder = QFileDialog.getExistingDirectory(self, tr("Export"), self.s.value("last_dir", "") or "")
        if not folder:
            return
        prog = QProgressDialog(tr("Saving…"), tr("Cancel"), 0, len(idxs), self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(0)

        def cb(k, n):
            prog.setValue(k)
            QApplication.processEvents()
            return not prog.wasCanceled()

        files = self._guard(t.pdf.export_images, folder, idxs, dpi, fmt, cb) or []
        prog.close()
        self.statusBar().showMessage(tr("Exported {n} images", n=len(files)), 5000)

    def merge_dialog(self):
        dlg = MergeDialog(self, self.s.value("last_dir", "") or "")
        if not dlg.exec():
            return
        files = dlg.files()
        if len(files) < 2:
            QMessageBox.information(self, tr("Merge PDFs"), tr("Choose at least two files"))
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("Merge PDFs"), "", tr(PDF_FILTER))
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            merge_files(files, path)
        except PasswordRequired as e:
            QMessageBox.warning(self, tr("Error"), f"{tr('This file is protected')}\n{e}")
            return
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, tr("Error"), str(e))
            return
        self.statusBar().showMessage(tr("Merged {n} files", n=len(files)), 5000)
        self.open_path(path)

    def insert_pdf(self):
        t = self.cur()
        if not t:
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("Insert PDF…"), self.s.value("last_dir", "") or "", tr(PDF_FILTER))
        if not path:
            return
        after, ok = QInputDialog.getInt(self, tr("Insert PDF…"), tr("Insert after page:"), t.view.current_page + 1,
                                        0, t.pdf.page_count)
        if not ok:
            return
        pw = None
        while True:
            try:
                t.pdf.insert_pdf(path, after, pw)
                break
            except PasswordRequired:
                pw, ok = QInputDialog.getText(self, tr("This file is protected"), tr("Enter the password to open it:"),
                                              QLineEdit.EchoMode.Password)
                if not ok:
                    return
            except Exception as e:  # noqa: BLE001
                QMessageBox.critical(self, tr("Error"), str(e))
                return

    def properties(self):
        t = self.cur()
        if t:
            d = PropertiesDialog(t.pdf, self)
            if d.exec():
                self._guard(t.pdf.set_metadata, d.values())

    def set_password(self):
        t = self.cur()
        if not t:
            return
        pw, ok = QInputDialog.getText(self, tr("Set password…"), tr("Leave empty to remove the password:"),
                                      QLineEdit.EchoMode.Password)
        if ok:
            t.pdf.set_password(pw)
            if pw:
                self.statusBar().showMessage(tr("The password will be applied when you save"), 5000)

    # ------------------------------------------------------------------
    # tools
    # ------------------------------------------------------------------
    def _on_tool(self, key: str):
        if key == "image":
            path, _ = QFileDialog.getOpenFileName(self, tr("Choose a picture"), "",
                                                  f"{tr('Images')} (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
            if not path:
                return self._revert_tool()
            self.opts["image_path"] = path
        elif key == "signature":
            if not os.path.isfile(sig_path()) and not self._draw_signature():
                return self._revert_tool()
            self.opts["image_path"] = sig_path()
        self._apply_tool(key)

    def _revert_tool(self):
        self.A["tool_" + self.tool].setChecked(True)
        self._apply_tool(self.tool)

    def _apply_tool(self, key: str):
        self.tool = key
        self.A["tool_" + key].setChecked(True)
        for t in self._tabs():
            t.view.set_tool(key)
        hint = next((h for k, _i, _l, h in TOOLS if k == key), "")
        self.statusBar().showMessage(tr(hint) if hint else "", 6000)

    def _draw_signature(self) -> bool:
        d = SignatureDialog(self)
        if d.exec() and d.pad.save_png(sig_path()):
            self.opts["image_path"] = sig_path()
            if self.tool == "signature":
                self._apply_tool("signature")
            return True
        return False

    def _set_color(self, hexcol: str):
        c = QColor(hexcol)
        rgb = (c.redF(), c.greenF(), c.blueF())
        self.opts["color"] = rgb
        for k in MARKUP:
            self.opts["tool_colors"][k] = rgb

    # ------------------------------------------------------------------
    # view commands
    # ------------------------------------------------------------------
    def _page_step(self, d: int):
        t = self.cur()
        if t:
            t.view.go_to_page(t.view.current_page + d)

    def _on_spin(self, v: int):
        t = self.cur()
        if t and not self._syncing:
            t.view.go_to_page(v - 1)

    def zoom_in(self):
        t = self.cur()
        if t:
            t.view.zoom_in()

    def zoom_out(self):
        t = self.cur()
        if t:
            t.view.zoom_out()

    def _zoom_to(self, z: float):
        t = self.cur()
        if t:
            t.view.set_zoom(z)

    def _fit(self, mode: str):
        t = self.cur()
        if t:
            t.view.set_fit(mode)

    def _zoom_from_box(self):
        txt = self.zoom_box.currentText().strip().rstrip("%").strip()
        try:
            self._zoom_to(float(txt) / 100.0)
        except ValueError:
            pass

    def toggle_invert(self):
        on = self.A["invert"].isChecked()
        for t in self._tabs():
            t.view.set_invert(on)

    def toggle_sidebar(self):
        t = self.cur()
        if t:
            t.side.setVisible(not t.side.isVisible())

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ------------------------------------------------------------------
    # state sync
    # ------------------------------------------------------------------
    def _on_changed(self, tab: DocTab, kind: str):
        self._update_tab_title(tab)
        if tab is self.cur():
            self._sync()

    def _on_page(self, tab: DocTab, i: int):
        if tab is self.cur():
            self._syncing = True
            self.spin.setValue(i + 1)
            self._syncing = False
            self._status(tab)

    def _on_zoom(self, tab: DocTab, z: float):
        if tab is self.cur():
            self.zoom_box.setEditText(f"{round(z * 100)}%")

    def _update_tab_title(self, tab: DocTab):
        i = self.tabs.indexOf(tab)
        if i >= 0:
            self.tabs.setTabText(i, ("● " if tab.pdf.modified else "") + tab.pdf.title)

    def _status(self, tab: DocTab):
        self.lbl_info.setText(tr("Page {n} of {total}", n=tab.view.current_page + 1, total=tab.pdf.page_count) + "   ")

    def _sync(self):
        tab = self.cur()
        has = tab is not None
        self.stack.setCurrentIndex(1 if has else 0)
        self.tools_tb.setVisible(has)
        for k, a in self.A.items():
            if k in ("open", "new", "merge", "quit", "theme", "fullscreen", "about", "lang_en", "lang_ar") or k.startswith("swatch"):
                continue
            a.setEnabled(has)
        for a in self.swatches:
            a.setEnabled(has)
        for w in (self.spin, self.zoom_box, self.width_spin, self.size_spin, self.font_box):
            w.setEnabled(has)
        if not has:
            self.setWindowTitle("PDF Toolkit")
            self.lbl_info.setText("")
            return
        pdf = tab.pdf
        self.A["undo"].setEnabled(pdf.can_undo)
        self.A["redo"].setEnabled(pdf.can_redo)
        self._syncing = True
        self.spin.setMaximum(max(1, pdf.page_count))
        self.spin.setValue(tab.view.current_page + 1)
        self.lbl_total.setText(f" / {pdf.page_count} ")
        self._syncing = False
        self.zoom_box.setEditText(f"{round(tab.view.zoom * 100)}%")
        self._update_tab_title(tab)
        self.setWindowTitle(f"{'● ' if pdf.modified else ''}{pdf.title} — PDF Toolkit")
        self._status(tab)

    def about(self):
        QMessageBox.about(
            self, tr("About"),
            f"<h3>PDF Toolkit {__version__}</h3><p>{tr('PDF Toolkit — a fast, modern PDF reader and editor.')}</p>"
            "<p><b>" + tr("Shortcuts") + "</b><br>Ctrl+O · Ctrl+S · Ctrl+F · Ctrl+Z / Ctrl+Y<br>"
            "Ctrl+1 / Ctrl+2 · Ctrl +/- · Ctrl+Wheel · Space+Drag · F4 · F11</p>")
