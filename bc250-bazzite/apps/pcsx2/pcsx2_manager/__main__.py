# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m pcsx2_manager"""

from __future__ import annotations

import argparse
import sys

from bc250_core import __version__ as CORE_VERSION, applog, instance
from bc250_core.app import create_app, exec_app

from . import APP_ID, APP_NAME, INFO, __version__


def main() -> int:
    parser = argparse.ArgumentParser(prog="pcsx2_manager", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    _args, qt_args = parser.parse_known_args()

    app = create_app(INFO, qt_args)
    if instance.already_running(INFO.app_id):
        return 0
    log_path = applog.setup(APP_ID)
    applog.logger(APP_ID).info("%s %s started (core %s)", APP_NAME, __version__, CORE_VERSION)
    from .main_window import MainWindow
    window = MainWindow(log_path=log_path)
    window.show()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
