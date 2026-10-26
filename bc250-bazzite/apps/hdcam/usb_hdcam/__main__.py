# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m usb_hdcam [--load [--auto]]

Without options it opens the window. --load sends the firmware to every camera in boot mode and waits until each is
a camera, without a window; the load service runs it with --auto, which does nothing when Load automatically is off."""

from __future__ import annotations

import argparse
import sys

from bc250_core import __version__ as CORE_VERSION, instance

from . import APP_NAME, INFO, __version__, camera, controls, firmware, loader


def apply_controls(node: str, chosen: dict[str, int], open_controls=controls.Camera) -> str:
    """Sets the picture settings the user chose on a camera that just came back; what went wrong, if anything."""
    if not chosen:
        return ""
    try:
        device = open_controls(node)
        try:
            refused = controls.apply(device, chosen)
        finally:
            device.close()
    except OSError as exc:
        return f"its picture settings could not be set: {exc.strerror or exc}."
    return f"the camera refused {', '.join(refused)}." if refused else ""


def load_all(auto: bool, find=camera.find, load=loader.load, home=None, open_controls=controls.Camera) -> int:
    from .settings import CameraSettings
    settings = CameraSettings(INFO)
    if auto and not settings.get("autoload"):
        return 0
    bursts = loader.bursts(settings.get("bandwidth"))
    cameras = find()
    if not cameras:
        print(f"No camera found. {camera.NOT_FOUND}")
        return 0
    boots = [found for found in cameras if not found.booted]
    if not boots:
        print("No camera waits for its firmware.")
        return 0
    code = 0
    for boot in boots:
        data = firmware.read(boot.model, home)
        if data is None:
            print(f"{boot.name} on port {boot.port}: there is no firmware for it yet. Open {APP_NAME} to get it.")
            code = 1
            continue
        outcome = load(boot, loader.with_bandwidth(data, bursts))
        print(f"{boot.name} on port {boot.port}: {outcome.message}")
        if not outcome.ok:
            code = 1
        elif outcome.camera is not None and outcome.camera.videos:
            problem = apply_controls(outcome.camera.videos[0], settings.controls(), open_controls)
            if problem:
                print(f"{boot.name} on port {boot.port}: {problem}")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(prog="usb_hdcam", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--load", action="store_true",
                        help="send the firmware to every camera that waits for it, without a window")
    parser.add_argument("--auto", action="store_true",
                        help="with --load: only when Load automatically is on (the load service)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    args, qt_args = parser.parse_known_args()
    if args.auto and not args.load:
        parser.error("--auto only goes with --load")
    if args.load:
        return load_all(args.auto)

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
