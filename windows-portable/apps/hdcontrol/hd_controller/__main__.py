# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m hd_controller [--windowed | --info]

Without options it opens the window, full screen. --info prints each controller's connection, battery, firmware and
(on the DualSense Edge) profiles, without a window and without the network (the BC250 app's --info).

The window's own controller support (SDL, through pygame-ce) is kept from SDL's DualSense driver, which would open the
controller to set its light bar and player lights itself: SDL reads the DualSense as Windows' other game controllers
then, and the app alone talks to it (a firmware update wants nothing else to)."""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable

from bc250_core import __version__ as CORE_VERSION, applog, instance

from . import APP_ID, APP_NAME, INFO, SUITE, __version__, controller, firmware, inputs, profiles
from .hiddevice import Device

INFO_WAIT_S = 0.5                   # --info: how long it waits for an input report, for the battery


def describe(found: controller.Controller, open_device: Callable[..., Device] = Device,
             open_reader: Callable[[controller.Controller], inputs.Reader] | None = None,
             wait: float = INFO_WAIT_S, sleep: Callable[[float], None] = time.sleep) -> list[str]:
    """A controller's lines; never its path or its address."""
    open_reader = open_reader or (lambda each: inputs.Reader(each.path, each.bus, open_device))
    lines = [f"{found.name} on {found.connection}"]
    battery = None
    try:
        reader = open_reader(found)
        try:
            for _ in range(max(1, round(wait / 0.05))):
                reader.read()
                if reader.battery is not None:
                    break
                sleep(0.05)
            battery = reader.battery
        finally:
            reader.close()
    except OSError:
        pass
    lines.append(f"  Battery: {battery.capacity if battery and battery.capacity is not None else '?'} %, "
                 f"{battery.status if battery else 'not reported'}")
    try:
        with open_device(found.path, None) as device:
            info = controller.read_info(device)
            lines += [f"  Firmware: {firmware.version_text(info.update)} (built {info.build_date} {info.build_time}, "
                      f"target {info.target:04X}, hardware 0x{info.hardware:08x}, firmware 0x{info.firmware:08x})"]
            if found.edge:
                for profile in profiles.read(device):
                    lines.append(f"  {profile.label}: " + ("empty" if profile.empty else
                                 f"{profile.name}, sticks {profile.left_curve} and {profile.right_curve}"))
    except (OSError, ValueError) as exc:
        lines.append(f"  Could not be read: {getattr(exc, 'strerror', None) or exc}")
    return lines


def print_info(find: Callable[[], list[controller.Controller]] = controller.find,
               describe_one: Callable[[controller.Controller], list[str]] = describe) -> int:
    found = find()
    if not found:
        print(f"No controller found. {controller.NOT_FOUND}")
        return 1
    for each in found:
        print("\n".join(describe_one(each)))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="hd_controller", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    parser.add_argument("--windowed", action="store_true", help="a window instead of the full screen")
    parser.add_argument("--info", action="store_true",
                        help="print each controller's battery, firmware and profiles, without a window")
    args, qt_args = parser.parse_known_args()
    if args.info:
        return print_info()

    os.environ.setdefault("SDL_JOYSTICK_HIDAPI_PS5", "0")      # before pygame-ce starts (see above)
    from bc250_core.app import create_app, exec_app
    from bc250_core.portable import PORTABLE

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


if __name__ == "__main__":
    sys.exit(main())
