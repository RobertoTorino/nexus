# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m datstation"""

from __future__ import annotations

import argparse
import sys

from bc250_core import __version__ as CORE_VERSION, instance
from bc250_core.app import create_app, exec_app

from . import APP_ID, APP_NAME, INFO, __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    return parser


def main() -> int:
    _, qt_args = build_parser().parse_known_args()

    app = create_app(INFO, qt_args)
    # A second launch (the menu entry, the Desktop icon, the Steam shortcut) shows the open window.
    if instance.already_running(INFO.app_id):
        return 0

    # DatStation's own PlayStation blue look (owner's decision), over core's start-up.
    from .style import apply_theme
    apply_theme(app)

    from .main_window import MainWindow
    window = MainWindow()
    window.show()
    server = instance.serve(INFO.app_id, window)  # noqa: F841  (kept alive while the app runs)
    # Logout or SIGTERM/SIGINT quit the app cleanly (settings saved) instead of killing it mid-event.
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
