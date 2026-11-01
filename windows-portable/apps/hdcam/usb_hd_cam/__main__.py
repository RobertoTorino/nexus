# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m usb_hd_cam [--windowed]; --bind <instance ID> is the elevated copy that Allow access starts
(driver.py): it binds WinUSB to the camera's boot loader and ends, without a window."""

from __future__ import annotations

import argparse
import sys

from bc250_core import __version__ as CORE_VERSION, applog, instance
from bc250_core.app import create_app, exec_app
from bc250_core.portable import PORTABLE

from . import APP_ID, APP_NAME, INFO, SUITE, __version__, driver


def main() -> int:
    parser = argparse.ArgumentParser(prog="usb_hd_cam", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    parser.add_argument("--windowed", action="store_true", help="a window instead of the full screen")
    parser.add_argument("--bind", metavar="INSTANCE", help=argparse.SUPPRESS)
    args, qt_args = parser.parse_known_args()
    if args.bind:
        return bind(args.bind)

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


def bind(instance: str) -> int:
    """The elevated copy: WinUSB on the boot loader, its outcome in the app's log and as the exit code."""
    applog.setup(APP_ID, suite=SUITE, private=True)
    log = applog.logger(APP_ID)
    if not driver.BOOT_LOADER.fullmatch(instance):
        log.error(f"Allow access refused a device that is not the camera's boot loader: {instance}")
        return driver.NOT_A_BOOT_LOADER
    try:
        driver.bind(instance)
    except driver.DriverError as error:
        log.error(f"WinUSB was not installed on the camera's boot loader: {error}")
        return driver.FAILED
    log.info("WinUSB installed on the camera's boot loader.")
    return driver.BOUND


if __name__ == "__main__":
    sys.exit(main())
