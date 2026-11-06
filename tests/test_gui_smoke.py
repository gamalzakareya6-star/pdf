"""Headless smoke test of the whole GUI (Qt 'offscreen' platform). Saves screenshots for review."""
import os

import pytest

pytest.importorskip("pymupdf")
pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as fitz  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pdftool.i18n import set_language  # noqa: E402
from pdftool.mainwindow import MainWindow  # noqa: E402

SHOTS = os.environ.get("SCREENSHOT_DIR")


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def make_pdf(path, pages=4):
    d = fitz.open()
    for i in range(pages):
        p = d.new_page(width=595, height=842)
        p.insert_text((60, 90), f"Chapter {i + 1}: Hello world", fontsize=24)
        for k in range(12):
            p.insert_text((60, 150 + k * 22), "The quick brown fox jumps over the lazy dog. " * 2, fontsize=11)
    d.set_toc([[1, "Intro", 1], [1, "Middle", 2], [2, "Details", 3]])
    d.save(str(path))
    d.close()
    return str(path)


def shot(win, name):
    win.repaint()
    QApplication.processEvents()
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        assert win.grab().save(os.path.join(SHOTS, name + ".png"))


def pump(n=5):
    for _ in range(n):
        QApplication.processEvents()


def test_full_flow(app, tmp_path):
    set_language("en")
    s = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    win = MainWindow(app, s)
    win.resize(1280, 820)
    win.show()
    pump()
    shot(win, "01_start_light")

    path = make_pdf(tmp_path / "doc.pdf")
    win.open_path(path)
    pump(20)
    tab = win.cur()
    assert tab is not None and tab.pdf.page_count == 4
    assert tab.outline.topLevelItemCount() == 2
    assert tab.thumbs.count() == 4
    shot(win, "02_open_light")

    # select text + highlight through the real view code path
    view = tab.view
    view._sel = (0, 0, 2)
    view.apply_markup("highlight")
    assert [a["type"] for a in tab.pdf.annots(0)] == ["Highlight"]
    assert tab.annots.count() == 1
    assert win.A["undo"].isEnabled()
    win.undo()
    assert tab.pdf.annots(0) == []
    win.redo()

    # search
    tab.show_search()
    tab.search_edit.setText("Hello")
    tab.run_search()
    assert len(tab._flat) == 4
    tab.step(1)
    pump()
    shot(win, "03_search_light")
    tab.hide_search()

    # tools through the toolbar logic
    win._apply_tool("draw")
    assert view.tool == "draw"
    win._apply_tool("select")

    # zoom + fit + invert
    view.set_zoom(1.5)
    assert abs(view.zoom - 1.5) < 1e-6
    view.set_fit("page")
    win.A["invert"].setChecked(True)
    win.toggle_invert()
    pump()
    shot(win, "04_invert_fitpage")
    win.A["invert"].setChecked(False)
    win.toggle_invert()
    view.set_fit("width")

    # page operations from the window helpers
    tab.thumbs.setCurrentRow(1)
    win.rotate(90)
    assert tab.pdf.page_sizes()[1][0] > tab.pdf.page_sizes()[1][1]
    win.duplicate_pages()
    assert tab.pdf.page_count == 5
    win.insert_blank()
    assert tab.pdf.page_count == 6
    tab.pdf.undo()
    tab.pdf.undo()
    tab.pdf.undo()
    assert tab.pdf.page_count == 4

    # save
    assert win.save()
    assert not tab.pdf.modified

    # dark theme + arabic start page
    win.toggle_theme()
    pump()
    shot(win, "05_open_dark")
    view.go_to_page(3)
    pump()
    assert view.current_page == 3

    assert win.close_tab(0) is True
    pump()
    shot(win, "06_start_dark")
    win.toggle_theme()
    win.close()


def test_arabic_ui(app, tmp_path):
    """Arabic UI (right-to-left layout) with an Arabic text box on the page."""
    from PySide6.QtCore import Qt
    from pdftool.document import PdfDoc

    set_language("ar")
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    try:
        s = QSettings(str(tmp_path / "ar.ini"), QSettings.Format.IniFormat)
        win = MainWindow(app, s)
        win.resize(1280, 820)
        win.show()
        pump()
        shot(win, "07_start_arabic")
        path = make_pdf(tmp_path / "ar.pdf", pages=2)
        pdf = PdfDoc.open(path)
        pdf.add_text(0, (60, 300, 520, 360), "مرحبًا بكم في أداة PDF — هذا نص عربي للتجربة", 22, (0.1, 0.2, 0.6))
        pdf.save(str(tmp_path / "ar2.pdf"))
        pdf.close()
        win.open_path(str(tmp_path / "ar2.pdf"))
        pump(20)
        win._apply_tool("highlight")
        shot(win, "08_open_arabic")
        assert win.close_tab(0) is True
        win.close()
    finally:
        set_language("en")
        app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)


def _vp(view, page, x, y):
    from PySide6.QtCore import QPoint
    r = view._page_view_rect(page)
    return QPoint(int(r.x() + x * view.zoom), int(r.y() + y * view.zoom))


def _drag(view, a, b, steps=8):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    vp = view.viewport()
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, pos=a)
    for i in range(1, steps + 1):
        QTest.mouseMove(vp, QPoint(a.x() + (b.x() - a.x()) * i // steps, a.y() + (b.y() - a.y()) * i // steps))
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, pos=b)
    pump()


def test_tools_with_real_mouse_events(app, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    set_language("en")
    s = QSettings(str(tmp_path / "t.ini"), QSettings.Format.IniFormat)
    win = MainWindow(app, s)
    win.resize(1280, 900)
    win.show()
    win.open_path(make_pdf(tmp_path / "t.pdf", pages=2))
    pump(20)
    tab = win.cur()
    view, pdf = tab.view, tab.pdf
    view.go_to_page(0)
    view.verticalScrollBar().setValue(0)
    pump()

    def kinds():
        return sorted(a["type"] for a in pdf.annots(0))

    # free drawing
    win._apply_tool("draw")
    _drag(view, _vp(view, 0, 300, 600), _vp(view, 0, 400, 650))
    assert "Ink" in kinds(), kinds()

    # rectangle
    win._apply_tool("rect")
    _drag(view, _vp(view, 0, 100, 650), _vp(view, 0, 220, 720))
    assert "Square" in kinds(), kinds()

    # highlight by dragging over the first words
    win._apply_tool("highlight")
    w = pdf.words(0)
    a = w[0]
    b = w[2]
    _drag(view, _vp(view, 0, a[0] + 1, (a[1] + a[3]) / 2), _vp(view, 0, b[2] - 1, (b[1] + b[3]) / 2))
    assert "Highlight" in kinds(), kinds()

    # text box: drag, type, commit
    win._apply_tool("text")
    _drag(view, _vp(view, 0, 60, 740), _vp(view, 0, 300, 790))
    assert view._editor is not None
    view._editor.setPlainText("Typed with the text tool")
    view._commit_editor()
    pump()
    assert "Typed" in [x[4] for x in pdf.words(0)]

    # select the rectangle and delete it with the keyboard
    win._apply_tool("select")
    before = kinds().count("Square")
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=_vp(view, 0, 160, 685))
    pump()
    assert view._sel_annot is not None
    QTest.keyClick(view, Qt.Key.Key_Delete)
    pump()
    assert kinds().count("Square") == before - 1

    # undo everything that was drawn, one step at a time
    n = 0
    while pdf.can_undo:
        pdf.undo()
        n += 1
    assert n >= 4 and pdf.annots(0) == []
    shot(win, "09_tools")
    pdf.modified = False
    win.close()
