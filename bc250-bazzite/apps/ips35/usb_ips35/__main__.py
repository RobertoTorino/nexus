# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m usb_ips35 [--minimized]"""

from __future__ import annotations

import argparse
import sys

from bc250_core import __version__ as CORE_VERSION, instance
from bc250_core.app import create_app, exec_app

from . import APP_NAME, INFO, __version__
from .autostart import MINIMIZED_FLAG
from .main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(prog="usb_ips35", description=f"{APP_NAME} {__version__}")
    parser.add_argument(MINIMIZED_FLAG, action="store_true",
                        help="start with the window minimized (as at login): the screen is updated all the same")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    args, qt_args = parser.parse_known_args()

    app = create_app(INFO, qt_args)
    # One instance: the screen has one port, and a second launch brings the running window to the front.
    if instance.already_running(INFO.app_id):
        return 0
    window = MainWindow()
    window.showMinimized() if args.minimized else window.show()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    app.aboutToQuit.connect(window.shut_down)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
