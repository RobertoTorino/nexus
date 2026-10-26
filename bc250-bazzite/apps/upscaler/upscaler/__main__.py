# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m upscaler [--payload DIR] [--deployments FILE] [--work DIR]"""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from . import APP_ID, APP_NAME, DEPLOYMENTS_FILE, DISPLAY_NAME, PAYLOAD_DIR, WINDOW_ICON_PATH, __version__
from .acquire import WORK_DIR
from .main_window import MainWindow
from .style import set_link_colour
from .theme import apply_theme
from .widgets import RoundedToolTip
from . import instance


def main() -> int:
    parser = argparse.ArgumentParser(prog="upscaler", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--payload", metavar="DIR", default=None,
                        help=f"folder that holds the imported HelixSR release (default: {PAYLOAD_DIR})")
    parser.add_argument("--deployments", metavar="FILE", default=None,
                        help=f"JSON file that lists where HelixSR was deployed (default: {DEPLOYMENTS_FILE})")
    parser.add_argument("--work", metavar="DIR", default=None,
                        help=f"folder for downloaded HelixSR releases (default: {WORK_DIR})")
    parser.add_argument("--no-update-check", action="store_true",
                        help="do not ask GitHub for the latest releases at start (overrides the saved setting)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args, qt_args = parser.parse_known_args()

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)
    app.setStyle("Fusion")
    apply_theme(app)                # the suite's theme
    set_link_colour(app)
    RoundedToolTip.install(app)
    if WINDOW_ICON_PATH.is_file():
        app.setWindowIcon(QIcon(str(WINDOW_ICON_PATH)))

    # One instance: a second launch brings the running window to the front and exits.
    if instance.already_running(APP_ID):
        return 0
    window = MainWindow(Path(args.payload).expanduser() if args.payload else PAYLOAD_DIR,
                        Path(args.deployments).expanduser() if args.deployments else DEPLOYMENTS_FILE,
                        Path(args.work).expanduser() if args.work else WORK_DIR,
                        check_updates=False if args.no_update_check else None)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: app.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)      # lets Python handle signals while Qt's event loop runs
    tick.start(500)
    window.show()
    server = instance.serve(APP_ID, window)  # noqa: F841 (kept alive while the app runs)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
