# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m bazzite_check [--script PATH] [--no-sudo]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtWidgets import QMessageBox

from bc250_core import __version__ as CORE_VERSION, instance
from bc250_core.app import create_app, exec_app

from . import APP_NAME, INFO, ROOT, __version__
from .main_window import MainWindow
from .runner import TestRunner

DEFAULT_SCRIPT = ROOT / "test-bazzite.sh"


def main() -> int:
    parser = argparse.ArgumentParser(prog="bazzite_check", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--script", default=str(DEFAULT_SCRIPT), help="path to test-bazzite.sh")
    parser.add_argument("--no-sudo", action="store_true",
                        help="run the script without sudo (development with development/tools/fake-test-bazzite.sh)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    args, qt_args = parser.parse_known_args()

    # Names, Fusion style, rounded tooltips and the window icon, as before the move to bc250_core.
    app = create_app(INFO, qt_args)

    script = Path(args.script).resolve()
    if not script.is_file():
        QMessageBox.critical(None, APP_NAME, f"Test engine not found:\n{script}\n\nReinstall the app to restore it.")
        return 1

    # One instance: a second launch brings the running window to the front and exits.
    if instance.already_running(INFO.app_id):
        return 0
    window = MainWindow(TestRunner(str(script), use_sudo=not args.no_sudo))
    # Logout or SIGTERM/SIGINT end the app without a close event: stop a running test cleanly first.
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
