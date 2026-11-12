# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m xenia_manager"""

from __future__ import annotations

import argparse
import sys

from bc250_core import __version__ as CORE_VERSION, applog, instance
from bc250_core.app import create_app, exec_app
from bc250_core import exit_keys

from . import APP_ID, APP_NAME, INFO, __version__


def main() -> int:
    parser = argparse.ArgumentParser(prog="xenia_manager", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    parser.add_argument("--gone", metavar="GAME", help="say that this game is no longer there, instead of starting "
                                                        "Xenia (the run wrapper, for a Steam shortcut)")
    args, qt_args = parser.parse_known_args()
    if args.gone:
        from pathlib import Path
        from bc250_core import gone
        return gone.show_dialog(INFO, APP_NAME, Path(args.gone), qt_args)

    app = create_app(INFO, qt_args)
    exit_keys.install(app)                  # Escape and a controller's B close the window
    if instance.already_running(INFO.app_id):
        return 0
    log_path = applog.setup(APP_ID, private=True)         # the user's folders as ~: no user name in the log
    applog.logger(APP_ID).info("%s %s started (core %s)", APP_NAME, __version__, CORE_VERSION)
    from .main_window import MainWindow
    window = MainWindow(log_path=log_path)
    window.show()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
