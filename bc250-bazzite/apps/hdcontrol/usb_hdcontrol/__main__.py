# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m usb_hdcontrol [--info | --idle-watch]

Without options it opens the window. --info prints each controller's connection, battery, firmware and (on the
DualSense Edge) profiles, without a window and without the network. --idle-watch is the idle service (idle.py): it
switches a controller on Bluetooth off after the minutes chosen in the window without use."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bc250_core import __version__ as CORE_VERSION, instance

from . import APP_NAME, INFO, __version__, controller, firmware, hidraw, profiles


def describe(found: controller.Controller, dev: Path = controller.DEV, open_device=hidraw.Device) -> list[str]:
    battery = found.battery
    lines = [f"{found.name} on {found.connection} ({found.node})",
             f"  Battery: {battery.capacity if battery and battery.capacity is not None else '?'} %, "
             f"{battery.status if battery else 'not reported'}"]
    try:
        with open_device(found.path(dev), found.sizes()) as device:
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


def print_info(find=controller.find, dev: Path = controller.DEV, open_device=hidraw.Device) -> int:
    found = find()
    if not found:
        print(f"No controller found. {controller.NOT_FOUND}")
        return 1
    for each in found:
        print("\n".join(describe(each, dev, open_device)))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="usb_hdcontrol", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--info", action="store_true",
                        help="print each controller's battery, firmware and profiles, without a window")
    parser.add_argument("--idle-watch", action="store_true",
                        help="switch controllers on Bluetooth off after the minutes chosen in the window unused "
                             "(the user service install.sh adds runs this)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    args, qt_args = parser.parse_known_args()
    if args.info:
        return print_info()
    if args.idle_watch:
        from . import idle
        return idle.run()

    from bc250_core.app import create_app, exec_app

    from .main_window import MainWindow
    app = create_app(INFO, qt_args)
    if instance.already_running(INFO.app_id):
        return 0
    window = MainWindow()
    window.show()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    app.aboutToQuit.connect(window.shut_down)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
