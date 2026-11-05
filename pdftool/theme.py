"""Light / dark themes: palette + stylesheet."""
from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

THEMES = {
    "light": dict(
        bg="#f4f5f8", surface="#ffffff", surface2="#eef0f5", border="#dcdfe7", text="#1f2430",
        muted="#7a8194", accent="#4f6bed", accent_soft="#e3e8fd", canvas="#d9dde5", hover="#e8ebf2",
        danger="#e5484d", icon="#4b5266", icon_dis="#b4b9c6",
    ),
    "dark": dict(
        bg="#17191e", surface="#20232a", surface2="#292d36", border="#363b47", text="#e7e9ef",
        muted="#9aa1b3", accent="#7f95ff", accent_soft="#2c3556", canvas="#121317", hover="#303541",
        danger="#ff6b70", icon="#c3c8d6", icon_dis="#5d6372",
    ),
}

SWATCHES = ["#ffd60a", "#34c759", "#ff6bb5", "#4f9dff", "#ff9f0a", "#ff3b30", "#1c1c1e", "#ffffff"]


def build_qss(c: dict) -> str:
    return f"""
    QMainWindow, QDialog {{ background: {c['bg']}; }}
    QWidget {{ color: {c['text']}; }}
    QWidget#startPage {{ background: {c['bg']}; }}
    QToolTip {{ background: {c['surface2']}; color: {c['text']}; border: 1px solid {c['border']};
                padding: 4px 8px; border-radius: 6px; }}

    QMenuBar {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; padding: 2px 6px; }}
    QMenuBar::item {{ padding: 6px 12px; background: transparent; border-radius: 6px; }}
    QMenuBar::item:selected {{ background: {c['hover']}; }}
    QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; padding: 6px; }}
    QMenu::item {{ padding: 7px 26px 7px 26px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {c['accent_soft']}; color: {c['text']}; }}
    QMenu::item:disabled {{ color: {c['muted']}; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 6px 8px; }}

    QToolBar {{ background: {c['surface']}; border: none; border-bottom: 1px solid {c['border']};
                padding: 4px 8px; spacing: 3px; }}
    QToolBar#tools {{ background: {c['surface2']}; }}
    QToolBar::separator {{ background: {c['border']}; width: 1px; margin: 6px 6px; }}
    QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
    QToolButton:hover {{ background: {c['hover']}; }}
    QToolButton:pressed {{ background: {c['accent_soft']}; }}
    QToolButton:checked {{ background: {c['accent_soft']}; }}
    QToolButton::menu-indicator {{ image: none; }}
    QToolButton[swatch="true"] {{ border: 2px solid transparent; border-radius: 11px; padding: 0px; }}
    QToolButton[swatch="true"]:hover {{ border: 2px solid {c['border']}; }}
    QToolButton[swatch="true"]:checked {{ border: 2px solid {c['accent']}; background: transparent; }}

    QPushButton {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px;
                   padding: 7px 16px; }}
    QPushButton:hover {{ background: {c['hover']}; }}
    QPushButton:pressed {{ background: {c['accent_soft']}; }}
    QPushButton:disabled {{ color: {c['muted']}; }}
    QPushButton[primary="true"] {{ background: {c['accent']}; color: white; border: 1px solid {c['accent']};
                                   font-weight: 600; }}
    QPushButton[primary="true"]:hover {{ background: {c['accent']}; border: 1px solid {c['text']}; }}
    QPushButton[card="true"] {{ text-align: left; padding: 16px 20px; border-radius: 12px; font-size: 11pt; }}

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
        background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 5px 8px;
        selection-background-color: {c['accent']}; selection-color: white; }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 1px solid {c['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border']};
                                   selection-background-color: {c['accent_soft']}; selection-color: {c['text']};
                                   outline: none; padding: 4px; }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 0px; border: none; }}

    QTabWidget::pane {{ border: none; background: {c['bg']}; }}
    QTabBar {{ background: transparent; }}
    QTabBar#docs {{ background: {c['bg']}; }}
    QTabBar#docs::tab {{ background: transparent; color: {c['muted']}; padding: 8px 8px 8px 14px; margin: 6px 2px 0 2px;
                         border-top-left-radius: 9px; border-top-right-radius: 9px; min-width: 90px; max-width: 240px; }}
    QTabBar#docs::tab:selected {{ background: {c['surface']}; color: {c['text']}; }}
    QTabBar#docs::tab:hover:!selected {{ background: {c['hover']}; }}
    QTabBar#side::tab {{ padding: 8px 12px; margin: 4px 2px; border-radius: 8px; color: {c['muted']}; }}
    QTabBar#side::tab:selected {{ background: {c['accent_soft']}; color: {c['text']}; }}
    QTabBar#side::tab:hover:!selected {{ background: {c['hover']}; }}

    QListWidget, QTreeWidget {{ background: {c['surface']}; border: none; outline: none; padding: 4px; }}
    QListWidget::item, QTreeWidget::item {{ border-radius: 8px; padding: 4px; }}
    QListWidget::item:hover, QTreeWidget::item:hover {{ background: {c['hover']}; }}
    QListWidget::item:selected, QTreeWidget::item:selected {{ background: {c['accent_soft']}; color: {c['text']}; }}
    QListWidget#recent {{ background: transparent; }}
    QListWidget#recent::item {{ padding: 9px 12px; }}
    QHeaderView::section {{ background: {c['surface']}; border: none; padding: 4px; }}

    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 36px; margin: 0 2px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 4px; min-width: 36px; margin: 2px 0; }}
    QScrollBar::handle:horizontal:hover {{ background: {c['muted']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QSplitter::handle {{ background: {c['border']}; width: 1px; }}
    QStatusBar {{ background: {c['surface']}; border-top: 1px solid {c['border']}; color: {c['muted']}; }}
    QStatusBar::item {{ border: none; }}
    QLabel#muted {{ color: {c['muted']}; }}
    QLabel#title {{ font-size: 26pt; font-weight: 700; }}
    QLabel#subtitle {{ color: {c['muted']}; font-size: 11pt; }}
    QFrame#searchBar {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; }}
    QProgressBar {{ border: 1px solid {c['border']}; border-radius: 6px; text-align: center; background: {c['surface']}; }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 5px; }}
    QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {c['accent']}; width: 14px; margin: -6px 0; border-radius: 7px; }}
    QCheckBox {{ spacing: 6px; }}
    """


def apply_theme(app: QApplication, name: str):
    c = THEMES[name]
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(c["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(c["surface"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(c["surface2"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(c["surface2"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(c["surface2"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(c["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["muted"]))
    pal.setColor(QPalette.ColorRole.Link, QColor(c["accent"]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(c["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(build_qss(c))


def setup_font(app: QApplication):
    f = QFont(app.font())
    if sys.platform == "win32":
        f = QFont("Segoe UI")
    f.setPointSize(10)
    app.setFont(f)
