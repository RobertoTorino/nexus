# SPDX-License-Identifier: AGPL-3.0-or-later
"""Entry point: python -m remote_play [--windowed], or python -m remote_play --stream <console> (the direct start a
console's Steam entry runs: the stream alone, full screen; beside an open main window too)."""

from __future__ import annotations

import argparse
import sys

from bc250_core import __version__ as CORE_VERSION, applog, instance
from bc250_core.app import create_app, exec_app
from bc250_core.portable import PORTABLE

from . import APP_ID, APP_NAME, INFO, SUITE, __version__


def main() -> int:
    parser = argparse.ArgumentParser(prog="remote_play", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    parser.add_argument("--windowed", action="store_true", help="a window instead of the full screen")
    parser.add_argument("--stream", metavar="CONSOLE", help="stream the registered CONSOLE (its key, host id, name or "
                        "address) full screen, without the main window")
    args, qt_args = parser.parse_known_args()

    app = create_app(INFO, qt_args, theme=PORTABLE)
    if args.stream:
        applog.setup(APP_ID, suite=SUITE, private=True)
        applog.logger(APP_ID).info(f"{APP_NAME} {__version__} started for a stream.")
        from . import direct
        return direct.run(args.stream, app)
    if instance.already_running(INFO.app_id):       # a second launch brings the open window to the front
        return 0
    log_path = applog.setup(APP_ID, suite=SUITE, private=True)   # no user name in a line
    applog.logger(APP_ID).info(f"{APP_NAME} {__version__} started.")
    from .main_window import MainWindow
    window = MainWindow(log_path=log_path)
    if args.windowed:
        window.resize(1280, 720)
        window.show()
    else:
        window.showFullScreen()
    window.start()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
