# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m nexus_releases (run.sh starts it with the checkout's dev venv)."""

from __future__ import annotations

import argparse
import sys

from bc250_core import __version__ as CORE_VERSION, instance
from bc250_core.app import create_app, exec_app
from bc250_core.platform import data_home
from bc250_core.settings import open_settings

from . import APP_ID, APP_NAME, INFO, ROOT, __version__
from .style import NEXUS

# Windows names a notification's source after the process's app ID: without one it is Python's (owner, 28-10-2026).
# The ID is registered for the current user with the name and icon notifications show (HKCU, no administrator);
# install.ps1 --uninstall removes it.
WINDOWS_APP_ID = "Nexus.NexusReleases"
WINDOWS_APP_KEY = rf"Software\Classes\AppUserModelId\{WINDOWS_APP_ID}"


def windows_app_id() -> None:
    """On Windows: this process is Nexus Releases, for its notifications and its taskbar button. A failure only
    leaves Python's name, so it is ignored."""
    if sys.platform != "win32":
        return
    import ctypes
    import winreg
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WINDOWS_APP_KEY) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(ROOT / "images" / f"{APP_ID}-128.png"))
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except (OSError, AttributeError):
        pass


def main() -> int:
    parser = argparse.ArgumentParser(prog="nexus_releases", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    _args, qt_args = parser.parse_known_args()

    windows_app_id()                                # before the first window: Windows reads it then
    app = create_app(INFO, qt_args, theme=NEXUS)           # Nexus's design, not a suite's theme
    if instance.already_running(INFO.app_id):       # a double-click on the Desktop icon starts it twice
        return 0
    # With the menu entry of install.sh, the desktop file name gives the window its icon in the task bar. Without
    # it, no name: Qt would try to register it with the desktop portal, which only logs "App info not found".
    if not (data_home() / "applications" / f"{APP_ID}.desktop").is_file():
        app.setDesktopFileName("")
    from .main_window import ReleaseWindow
    window = ReleaseWindow(settings=open_settings(INFO))
    window.show()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
