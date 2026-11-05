"""Application entry point."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QCoreApplication, QSettings, Qt
from PySide6.QtWidgets import QApplication

from . import __version__
from .i18n import set_language
from .mainwindow import MainWindow
from .theme import setup_font


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    QCoreApplication.setOrganizationName("PDFToolkit")
    QCoreApplication.setApplicationName("PDFToolkit")
    QCoreApplication.setApplicationVersion(__version__)
    app = QApplication(argv)
    settings = QSettings()
    lang = str(settings.value("lang", "en"))
    set_language(lang)
    if lang == "ar":
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    setup_font(app)
    win = MainWindow(app, settings)
    win.show()
    for p in argv[1:]:
        if p.lower().endswith(".pdf") and os.path.isfile(p):
            win.open_path(p)
    return app.exec()
