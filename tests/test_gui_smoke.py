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
