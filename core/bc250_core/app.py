# SPDX-License-Identifier: GPL-3.0-or-later
"""App bootstrap shared by every GUI: QApplication names, Fusion style with the suite's theme, tooltip, icon, signals. The apps are in
English only, Qt's own dialog buttons included: nothing loads a translation.

    def main() -> int:
        app = create_app(INFO, qt_args)
        window = MainWindow()
        window.show()
        return exec_app(app)

or run_app(INFO, MainWindow) when the app has no arguments of its own."""

from __future__ import annotations

import signal
import sys
from collections.abc import Callable, Sequence

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QWidget

from . import appinfo
from .appinfo import AppInfo
from .theme import apply_theme
from .widgets import RoundedToolTip


def create_app(info: AppInfo, qt_args: Sequence[str] = (), stylesheet: str = "") -> QApplication:
    """The QApplication with the app's names, style and theme (*stylesheet* after the theme's), rounded tooltips
    and window icon. Also makes
    *info* the current AppInfo. The org/app names match open_settings(), so bare QSettings() find the same file.
    The organization is only set when the app declares one (the bisect/unlock GUIs), as before the move to core."""
    appinfo.set_current(info)
    app = QApplication.instance() or QApplication([sys.argv[0], *qt_args])
    if info.settings_org:
        app.setOrganizationName(info.settings_org)
    app.setApplicationName(info.settings_name)
    app.setApplicationDisplayName(info.display_name)
    app.setApplicationVersion(info.version)
    app.setDesktopFileName(info.app_id)
    app.setStyle("Fusion")
    apply_theme(app, stylesheet)
    RoundedToolTip.install(app)     # every tooltip: rounded corners, a thin border in the accent
    if info.logo is not None and info.logo.is_file():
        app.setWindowIcon(QIcon(str(info.logo)))
    return app


def exec_app(app: QApplication) -> int:
    """app.exec(), but logout or SIGTERM/SIGINT quit the app cleanly instead of killing it mid-event."""
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: app.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)      # lets Python handle signals while Qt's event loop runs
    tick.start(500)
    return app.exec()


def run_app(info: AppInfo, window_factory: Callable[[], QWidget], qt_args: Sequence[str] = (),
            stylesheet: str = "") -> int:
    app = create_app(info, qt_args, stylesheet)
    window = window_factory()
    window.show()
    return exec_app(app)
