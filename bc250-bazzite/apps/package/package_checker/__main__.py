# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m package_checker [--bazzite-reminder].

--bazzite-reminder shows no window: it reads Bazzite's update state and, when an update waits for a reboot or
Bazzite's updater failed or stopped running, says so in a desktop notification. The weekly systemd user timer that
install.sh writes runs it."""

from __future__ import annotations

import sys
from bc250_core import __version__ as CORE_VERSION, instance
from bc250_core.app import create_app, exec_app
from PyQt6.QtWidgets import QMessageBox

from . import APP_NAME, CATALOG, INFO, LOGO_PATH, __version__
from .bazzite import notify, read_state, reminder
from .dependencies import DependencyCatalogError, load_apps, load_catalog, load_tools
from .main_window import DependencyWindow


def bazzite_reminder() -> int:
    text = reminder(read_state())
    if text:
        notify(text, str(LOGO_PATH))
        print(text)
    return 0


def main() -> int:
    if "--bazzite-reminder" in sys.argv:
        return bazzite_reminder()
    app = create_app(INFO, sys.argv[1:])
    try:
        apps = load_apps(CATALOG)
        dependencies = load_catalog(CATALOG)
        tools = load_tools(CATALOG)
    except DependencyCatalogError as exc:
        QMessageBox.critical(None, APP_NAME, f"The dependency catalog could not be read:\n\n{exc}")
        return 1
    if instance.already_running(INFO.app_id):
        return 0
    window = DependencyWindow(dependencies, tools, apps)
    window.show()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    return exec_app(app)


if __name__ == "__main__":
    if "--version" in sys.argv:
        print(f"portal-dependency-checker {__version__} (core {CORE_VERSION})")
        sys.exit(0)
    sys.exit(main())
