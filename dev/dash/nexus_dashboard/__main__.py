# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m nexus_dashboard [--suite NAME] (run.sh and run.ps1 start it with the checkout's dev venv)."""

from __future__ import annotations

import argparse
import sys

from bc250_core import __version__ as CORE_VERSION, instance
from bc250_core.app import create_app, exec_app
from bc250_core.nexus import NEXUS
from bc250_core.platform import data_home
from bc250_core.settings import open_settings

from . import APP_ID, APP_NAME, INFO, __version__, replace


def main() -> int:
    parser = argparse.ArgumentParser(prog="nexus_dashboard", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    parser.add_argument("--suite", metavar="NAME", help="the suite to open with (a folder of the checkout, such "
                                                        "as bc250-bazzite); default: the one chosen last")
    args, qt_args = parser.parse_known_args()

    app = create_app(INFO, qt_args, theme=NEXUS)           # Nexus's design, not a suite's theme
    # One instance, and the newest: a launch closes the open dashboard and takes its place. Two launches at the same
    # moment (a double-click on the Desktop icon) still give one window: the second shows the first's.
    if not replace.close_running(INFO.app_id) or instance.already_running(INFO.app_id):
        return 0
    if not (data_home() / "applications" / f"{APP_ID}.desktop").is_file():
        app.setDesktopFileName("")              # no menu entry: no desktop file name for Qt to look up
    from .main_window import MainWindow
    window = MainWindow(settings=open_settings(INFO), suite=args.suite)
    window.show()
    server = instance.serve(INFO.app_id, window)
    replace.serve(server, window)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
