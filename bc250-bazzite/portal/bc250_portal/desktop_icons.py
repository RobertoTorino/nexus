# SPDX-License-Identifier: GPL-3.0-or-later
"""The apps' icons on the Desktop, which the user switches on or off in the portal (the "Icons on Desktop" pill).

Every app's installer writes an app menu entry, ~/.local/share/applications/bc250-*.desktop (or one of OTHERS), and
by default the same file on the Desktop. The portal starts every app, so the Desktop icons are optional: switched off, the portal removes
the Desktop copies of the suite's menu entries; switched on, it copies every installed app's menu entry there. Only
files named like a suite menu entry are touched, and never the portal's own icon. The menu entries always stay: the
app menu, KDE's search and Steam's "Add a Non-Steam Game" list find the apps through them."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from bc250_core.platform import data_home

PORTAL = "bc250-bazzite-suite.desktop"
PATTERN = "bc250-*.desktop"
OTHERS = ("media-tool.desktop", "bazzite-netcatgui.desktop", "bazzite-datstation.desktop")  # apps not bc250-*


def desktop_dir() -> Path:
    """The user's Desktop folder (xdg-user-dir: it may be translated or moved), else ~/Desktop."""
    try:
        done = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=5)
        found = done.stdout.strip()
        if done.returncode == 0 and found and Path(found) != Path.home():
            return Path(found)
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.home() / "Desktop"


def menu_dir() -> Path:
    return data_home() / "applications"


def launchers(menu: Path) -> list[Path]:
    """The installed apps' menu entries, the portal's own left out."""
    if not menu.is_dir():
        return []
    found = set(menu.glob(PATTERN)) | {menu / name for name in OTHERS}
    return sorted(p for p in found if p.name != PORTAL and p.is_file())


def on_desktop(desktop: Path, menu: Path) -> list[Path]:
    """The apps' icons on the Desktop now."""
    return [desktop / p.name for p in launchers(menu) if (desktop / p.name).is_file()]


def remove(desktop: Path, menu: Path) -> list[str]:
    removed = []
    for icon in on_desktop(desktop, menu):
        icon.unlink(missing_ok=True)
        removed.append(icon.name)
    return removed


def add(desktop: Path, menu: Path) -> list[str]:
    """Copies every app's menu entry to the Desktop, as the installers do: executable, and trusted for GNOME."""
    if not desktop.is_dir():
        return []
    gio = shutil.which("gio")
    added = []
    for entry in launchers(menu):
        icon = desktop / entry.name
        if icon.is_file():
            continue
        shutil.copyfile(entry, icon)
        icon.chmod(0o755)                       # KDE and GNOME only start Desktop launchers that are executable
        if gio:
            subprocess.run([gio, "set", str(icon), "metadata::trusted", "true"], capture_output=True, check=False)
        added.append(icon.name)
    return added


def apply(show: bool, desktop: Path, menu: Path) -> list[str]:
    return add(desktop, menu) if show else remove(desktop, menu)
