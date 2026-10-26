# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m suite_releases (run.sh starts it with the checkout's dev venv)."""

from __future__ import annotations

import argparse
import sys

from bc250_core import __version__ as CORE_VERSION, instance
from bc250_core.app import create_app, exec_app
from bc250_core.platform import data_home
from bc250_core.settings import open_settings

from . import APP_ID, APP_NAME, INFO, __version__


def main() -> int:
    parser = argparse.ArgumentParser(prog="suite_releases", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    _args, qt_args = parser.parse_known_args()

    app = create_app(INFO, qt_args)
    if instance.already_running(INFO.app_id):       # a double-click on the Desktop icon starts it twice
        return 0
    # With the menu entry of install.sh, the desktop file name gives the window its icon in the task bar. Without
    # it, no name: Qt would try to register it with the desktop portal, which only logs "App info not found".
    if not (data_home() / "applications" / f"{APP_ID}.desktop").is_file():
        app.setDesktopFileName("")
    from .main_window import ReleaseWindow
    window = ReleaseWindow(settings=open_settings(INFO))
    window.show()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
