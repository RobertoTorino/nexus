# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m shadps4_manager [file.pkg]"""

from __future__ import annotations

import argparse
import os
import sys

from PyQt6.QtCore import QTimer

from bc250_core import __version__ as CORE_VERSION, applog, instance
from bc250_core.app import create_app, exec_app

from . import APP_ID, APP_NAME, INFO, __version__


def main() -> int:
    parser = argparse.ArgumentParser(prog="shadps4_manager", description=f"{APP_NAME} {__version__}")
    parser.add_argument("pkg_file", nargs="?", help="a package (.pkg) to open in Extract PKG")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    args, qt_args = parser.parse_known_args()
    if args.pkg_file:
        # Absolute, as the folder it was given in: the open window of a second launch runs elsewhere.
        args.pkg_file = os.path.abspath(args.pkg_file)

    app = create_app(INFO, qt_args)
    # A second launch (opening a package with the app from the file manager) hands its package to the open window.
    if instance.already_running(INFO.app_id, [args.pkg_file] if args.pkg_file else []):
        return 0
    log_path = applog.setup(APP_ID)
    applog.logger(APP_ID).info("%s %s started (core %s)", APP_NAME, __version__, CORE_VERSION)
    from .main_window import MainWindow
    window = MainWindow(log_path=log_path)
    window.show()
    if args.pkg_file:
        QTimer.singleShot(0, lambda: window.open_extract(args.pkg_file))
    server = instance.serve(INFO.app_id, window,  # noqa: F841 (kept alive while the app runs)
                            on_args=lambda forwarded: window.open_extract(forwarded[0]))
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
