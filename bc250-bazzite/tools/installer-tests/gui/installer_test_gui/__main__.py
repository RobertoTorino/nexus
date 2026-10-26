# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from . import APP_ICON_PATH, APP_ID, APP_NAME, __version__, instance
from .main_window import MainWindow
from .theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    apply_theme(app)                # the suite's theme
    if APP_ICON_PATH.is_file():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    # One instance: a second launch (a double-click on the Desktop icon) brings the running window to the front.
    if instance.already_running(APP_ID):
        return 0
    window = MainWindow()
    window.show()
    server = instance.serve(APP_ID, window)  # noqa: F841 (kept alive while the app runs)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
