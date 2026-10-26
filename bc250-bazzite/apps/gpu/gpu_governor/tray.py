# SPDX-License-Identifier: GPL-3.0-or-later
"""System tray icon with live tooltip, and the ~/.config/autostart entry for starting at login."""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from . import APP_ID, APP_NAME

AUTOSTART_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / f"{APP_ID}.desktop"
TRAY_FLAG = "--start-in-tray"


class Tray(QSystemTrayIcon):
    """Tray icon: left click toggles the window, the menu offers show/hide, performance mode, profiles and quit."""

    profile_requested = pyqtSignal(str)

    def __init__(self, icon: QIcon, window: QWidget):
        super().__init__(icon, window)
        self.window = window
        menu = QMenu()
        self.toggle_action = QAction("Hide window", menu)
        self.toggle_action.triggered.connect(self.toggle_window)
        menu.addAction(self.toggle_action)
        menu.addSeparator()
        self.perf_action = QAction("Performance mode", menu)
        self.perf_action.setCheckable(True)
        self.perf_action.setEnabled(False)
        menu.addAction(self.perf_action)
        self.profiles_menu = menu.addMenu("Apply profile")
        self.profiles_menu.setEnabled(False)
        menu.addSeparator()
        self.quit_action = QAction("Quit", menu)
        menu.addAction(self.quit_action)
        self.setContextMenu(menu)
        self.activated.connect(self._activated)
        self.setToolTip(APP_NAME)

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_window()

    def toggle_window(self) -> None:
        if self.window.isVisible() and not self.window.isMinimized():
            self.window.hide()
        else:
            self.window.showNormal()
            self.window.raise_()
            self.window.activateWindow()
        self.sync_toggle()

    def sync_toggle(self) -> None:
        self.toggle_action.setText("Hide window" if self.window.isVisible() else "Show window")

    def set_profiles(self, names: list[str]) -> None:
        self.profiles_menu.clear()
        for name in names:
            action = self.profiles_menu.addAction(name)
            action.triggered.connect(lambda _checked=False, n=name: self.profile_requested.emit(n))
        self.profiles_menu.setEnabled(bool(names))

    def set_perf(self, available: bool, enabled: bool) -> None:
        self.perf_action.setEnabled(available)
        self.perf_action.blockSignals(True)
        self.perf_action.setChecked(available and enabled)
        self.perf_action.blockSignals(False)


# ---------------------------------------------------------------------- autostart
def launcher_command() -> str:
    """How to start this app again: the install.sh launcher if present, else this interpreter + module."""
    launcher = shutil.which(APP_ID) or str(Path.home() / ".local" / "bin" / APP_ID)
    if Path(launcher).is_file() and os.access(launcher, os.X_OK):
        return launcher
    return f'"{sys.executable}" -m gpu_governor'


def profile_command(name: str) -> str:
    """Shell line that applies `name` in the running app (or starts it and applies), for a desktop shortcut."""
    return f"{launcher_command()} --profile {shlex.quote(name)}"


def autostart_enabled() -> bool:
    return AUTOSTART_FILE.is_file()


def set_autostart(enabled: bool, *, start_in_tray: bool) -> None:
    if not enabled:
        AUTOSTART_FILE.unlink(missing_ok=True)
        return
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    exec_line = launcher_command() + (f" {TRAY_FLAG}" if start_in_tray else "")
    AUTOSTART_FILE.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        f"Exec={exec_line}\n"
        f"Icon={APP_ID}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-KDE-autostart-after=panel\n",
        encoding="utf-8")
