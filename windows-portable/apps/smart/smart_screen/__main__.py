# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m smart_screen [--windowed] [--minimized]"""

from __future__ import annotations

import argparse
import sys

from PyQt6.QtCore import Qt

from bc250_core import __version__ as CORE_VERSION, applog, instance
from bc250_core.app import create_app, exec_app
from bc250_core.portable import PORTABLE

from . import APP_ID, APP_NAME, INFO, SUITE, __version__
from .autostart import MINIMIZED_FLAG


def main() -> int:
    parser = argparse.ArgumentParser(prog="smart_screen", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    parser.add_argument("--windowed", action="store_true", help="a window instead of the full screen")
    parser.add_argument(MINIMIZED_FLAG, action="store_true",
                        help="start minimized (as at sign-in): the screen is updated all the same")
    args, qt_args = parser.parse_known_args()

    app = create_app(INFO, qt_args, theme=PORTABLE)
    # One instance: the screen has one port, and a second launch brings the running window to the front.
    if instance.already_running(INFO.app_id):
        return 0
    log_path = applog.setup(APP_ID, suite=SUITE, private=True)   # no user name in a line
    applog.logger(APP_ID).info(f"{APP_NAME} {__version__} started{' minimized' if args.minimized else ''}.")
    from .main_window import MainWindow
    window = MainWindow(log_path=log_path)
    if args.windowed:
        window.resize(1280, 720)
        window.showMinimized() if args.minimized else window.show()
    elif args.minimized:
        # Full screen once it is brought back from the taskbar, without showing it first
        window.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        window.setWindowState(Qt.WindowState.WindowFullScreen | Qt.WindowState.WindowMinimized)
        window.show()
    else:
        window.showFullScreen()
    window.start()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    app.aboutToQuit.connect(window.shut_down)       # also at sign-out, when Windows ends the app
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
