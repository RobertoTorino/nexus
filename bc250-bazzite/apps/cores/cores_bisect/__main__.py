# SPDX-License-Identifier: GPL-3.0-or-later

"""Entry point: python -m cores_bisect [--script PATH]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from . import APP_ID, APP_NAME, ROOT, WINDOW_ICON_PATH, __version__
from .main_window import MainWindow
from . import instance
from .theme import HOVER_STYLESHEET, apply_theme

DEFAULT_SCRIPT = ROOT / "bc250-cores-bisect.sh"


def main() -> int:
    parser = argparse.ArgumentParser(prog="cores_bisect", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--script", default=str(DEFAULT_SCRIPT), help="path to bc250-cores-bisect.sh")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args, qt_args = parser.parse_known_args()

    app = QApplication([sys.argv[0], *qt_args])
    app.setOrganizationName("bc250-cores-bisect")
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(f"{APP_NAME} {__version__}")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)
    app.setStyle("Fusion")
    apply_theme(app, HOVER_STYLESHEET)     # the suite's theme, the accent outline on hover
    if WINDOW_ICON_PATH.is_file():
        app.setWindowIcon(QIcon(str(WINDOW_ICON_PATH)))

    script = Path(args.script).resolve()
    if not script.is_file():
        QMessageBox.critical(None, APP_NAME, f"bc250-cores-bisect.sh not found:\n{script}")
        return 1

    # One instance: a second launch brings the running window to the front and exits.
    if instance.already_running(APP_ID):
        return 0
    window = MainWindow(str(script))
    window.show()
    server = instance.serve(APP_ID, window)  # noqa: F841 (kept alive while the app runs)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
