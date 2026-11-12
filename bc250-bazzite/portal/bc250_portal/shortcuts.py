# SPDX-License-Identifier: GPL-3.0-or-later
"""The header's shortcuts (owner, 12-11-2026): Steam, the file manager, YouTube, and the desktop's Bluetooth and
network settings, each a symbol that starts a program outside the suite. What to start is found here, from what the
machine has: Steam's own launcher, the desktop's file manager on the home folder (xdg-open, whichever desktop),
YouTube fullscreen in Brave Browser's kiosk mode (its Flatpak, which must be installed), and the settings of KDE
Plasma (System Settings, else the module alone) or of GNOME. A shortcut whose program is missing raises Missing
with the line the window shows."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

BRAVE_ID, BRAVE_NAME = "com.brave.Browser", "Brave Browser"
YOUTUBE_URL = "https://www.youtube.com/"
# The settings page of each desktop, the first whose program is there: (program, its arguments, its window's id).
SETTINGS = {
    "bluetooth": (("systemsettings", ("kcm_bluetooth",), "systemsettings"),
                  ("kcmshell6", ("kcm_bluetooth",), "kcmshell6"),
                  ("gnome-control-center", ("bluetooth",), "org.gnome.Settings")),
    "network": (("systemsettings", ("kcm_networkmanagement",), "systemsettings"),
                ("kcmshell6", ("kcm_networkmanagement",), "kcmshell6"),
                ("gnome-control-center", ("network",), "org.gnome.Settings")),
}

# Looked up when called, so a test can replace them.
Which = Callable[[str], str | None]
Run = Callable[..., subprocess.CompletedProcess]


class Missing(RuntimeError):
    """The shortcut's program is not on this machine; str() is what the window says."""


@dataclass(frozen=True)
class Start:
    argv: list[str]             # what to start
    app_ids: tuple[str, ...]    # its window, for KWin to bring to the front when it runs already


def steam(which: Which | None = None) -> Start:
    if (which or shutil.which)("steam") is None:
        raise Missing("Steam is not installed on this system.")
    return Start(["steam"], ("steam",))


def files(which: Which | None = None, home: Path | None = None) -> Start:
    """The desktop's own file manager, on the home folder."""
    if (which or shutil.which)("xdg-open") is None:
        raise Missing("No file manager could be opened: xdg-open is not on this system.")
    return Start(["xdg-open", str(home or Path.home())], ("org.kde.dolphin", "org.gnome.Nautilus"))


def flatpak_installed(app_id: str, run: Run | None = None) -> bool:
    """Whether the Flatpak is installed; Missing when Flatpak cannot say."""
    try:
        result = (run or subprocess.run)(["flatpak", "info", app_id], capture_output=True, text=True, timeout=5)
    except FileNotFoundError:
        raise Missing("Flatpak is not available on this system.") from None
    except (OSError, subprocess.SubprocessError) as exc:
        raise Missing(f"Flatpak could not be asked what is installed:\n\n{exc}") from None
    return result.returncode == 0


def youtube(run: Run | None = None) -> Start:
    """YouTube fullscreen in Brave Browser's kiosk mode (Alt+F4 closes it)."""
    if not flatpak_installed(BRAVE_ID, run):
        raise Missing(f"{BRAVE_NAME} is required. Install its Flatpak ({BRAVE_ID}) to open YouTube.")
    return Start(["flatpak", "run", BRAVE_ID, "--kiosk", YOUTUBE_URL], (BRAVE_ID, "brave-browser"))


def settings(page: str, which: Which | None = None) -> Start:
    """The desktop's settings on *page*: "bluetooth" or "network"."""
    for program, arguments, app_id in SETTINGS[page]:
        if (which or shutil.which)(program) is not None:
            return Start([program, *arguments], (app_id,))
    raise Missing(f"The {'Bluetooth' if page == 'bluetooth' else page} settings of this desktop could not be found "
                  "(KDE Plasma's System Settings or GNOME's Settings).")


def bluetooth_settings() -> Start:
    return settings("bluetooth")


def network_settings() -> Start:
    return settings("network")
