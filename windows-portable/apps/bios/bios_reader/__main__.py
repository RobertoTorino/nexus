# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m bios_reader [--windowed]; --read-variables <request> <result> is the elevated copy that This
device's Read the settings starts (device.py): it reads the device's UEFI variables the request names, writes them to
the result and ends, without a window. It never writes a variable."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bc250_core import __version__ as CORE_VERSION, applog, instance
from bc250_core.app import create_app, exec_app
from bc250_core.portable import PORTABLE

from . import APP_ID, APP_NAME, INFO, SUITE, __version__, device


def main() -> int:
    parser = argparse.ArgumentParser(prog="bios_reader", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    parser.add_argument("--windowed", action="store_true", help="a window instead of the full screen")
    parser.add_argument("--read-variables", nargs=2, metavar=("REQUEST", "RESULT"), help=argparse.SUPPRESS)
    args, qt_args = parser.parse_known_args()
    if args.read_variables:
        return read_variables(Path(args.read_variables[0]), Path(args.read_variables[1]))

    app = create_app(INFO, qt_args, theme=PORTABLE)
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


def read_variables(request: Path, result: Path) -> int:
    """The elevated copy: the device's variables read, the count (never a value) in the app's log, the outcome as
    the exit code."""
    applog.setup(APP_ID, suite=SUITE, private=True)
    log = applog.logger(APP_ID)
    code = device.run_request(request, result)
    log.info({device.READ: "The device's settings were read.",
              device.BAD_REQUEST: "The read refused a request it did not make sense of.",
              device.NO_PRIVILEGE: "The read had no administrator's rights.",
              device.FAILED: "The read's result could not be written."}[code])
    return code


if __name__ == "__main__":
    sys.exit(main())
