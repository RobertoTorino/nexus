# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m gpu_governor [--backend auto|smu|tt] [--config PATH] [--profile NAME | --list-profiles]

One instance per user: a second launch tells the running one to show its window (or to apply --profile) and
exits, which is what makes `--profile` usable as a desktop hotkey command."""

from __future__ import annotations

import argparse
import signal
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from . import APP_ID, APP_NAME, DISPLAY_NAME, WINDOW_ICON_PATH, __version__
from .backends import BACKENDS, detect_backend
from . import instance
from .main_window import MainWindow
from .profiles import ProfileStore
from .theme import apply_theme
from .tray import TRAY_FLAG
from .widgets import RoundedToolTip

def main() -> int:
    parser = argparse.ArgumentParser(prog="gpu_governor", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--backend", choices=("auto", *BACKENDS), default="auto",
                        help="governor to manage: smu (cyan-skillfish-governor-smu, the default), tt "
                             "(cyan-skillfish-governor-tt) or auto: whichever systemd unit is loaded (default: auto)")
    parser.add_argument("--config", default=None,
                        help="path of the governor's config.toml (default: the backend's /etc/… path; "
                             "another path is useful for development)")
    parser.add_argument(TRAY_FLAG, action="store_true",
                        help="start hidden with only the tray icon (used by the login autostart entry)")
    parser.add_argument("--profile", metavar="NAME", default=None,
                        help="apply the saved profile NAME (in the running instance if there is one, otherwise "
                             "start and apply); meant for a desktop keyboard shortcut")
    parser.add_argument("--list-profiles", action="store_true", help="print the saved profile names and exit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args, qt_args = parser.parse_known_args()

    if args.list_profiles:
        print("\n".join(ProfileStore().names()))
        return 0

    app = QApplication([sys.argv[0], *qt_args])
    request = instance.PROFILE + args.profile if args.profile else instance.SHOW
    if instance.already_running(request):
        if args.profile:
            print(f"Profile '{args.profile}' handed to the running {APP_NAME}")
        return 0
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)
    app.setStyle("Fusion")
    apply_theme(app)                # the suite's theme
    RoundedToolTip.install(app)     # every tooltip: rounded corners, a thin border in the accent
    if WINDOW_ICON_PATH.is_file():
        app.setWindowIcon(QIcon(str(WINDOW_ICON_PATH)))

    window = MainWindow(detect_backend(args.backend, args.config))
    server = instance.InstanceServer(window)
    server.received.connect(window.handle_request)
    if server.listen():
        window.instance_server = server
    # Logout or SIGTERM/SIGINT end the app without a close event; let Python handle the signals.
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: app.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)      # lets Python handle signals while Qt's event loop runs
    tick.start(500)
    if args.start_in_tray and window.tray is not None:
        window.tray.sync_toggle()       # window stays hidden; the tray icon is the only sign of life
    else:
        window.show()
    if args.profile:
        QTimer.singleShot(0, lambda: window.apply_profile_by_name(args.profile))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
