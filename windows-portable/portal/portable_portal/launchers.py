# SPDX-License-Identifier: GPL-3.0-or-later
"""The programs the portal starts from its tabs' line (owner, 07-11-2026: "buttons in the top row to start Steam,
XBOX, Armoury Crate and Command Center"): Steam through the window's own Steam action (RT), the others as Windows
starts a Start-menu app, by its application ID (shell:AppsFolder), never by a window's or a device's name.

An app is there when Windows keeps its package's folder for this user (%LOCALAPPDATA%\\Packages\\<family name>), as
core's xbox.installed() reads the XBOX app. Armoury Crate is ASUS's: Armoury Crate SE on the ROG Ally and XBOX Ally,
Armoury Crate on ASUS's laptops; Command Center is Armoury Crate SE's overlay, a package of its own. Elsewhere the
button says it is not on this device. The IDs as Windows lists them on the owner's ROG XBOX Ally X (07-11-2026:
Get-StartApps, the packages' AppxManifest.xml)."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from bc250_core import xbox

STEAM = "steam"


@dataclass(frozen=True)
class Launcher:
    key: str
    name: str                                   # on its button
    apps: tuple[tuple[str, str], ...] = ()      # (package family name, app ID in it), the first one there is started

    def app_ids(self) -> list[str]:
        return [f"{family}!{app}" for family, app in self.apps]


LAUNCHERS = (
    Launcher(STEAM, "Steam"),
    Launcher("xbox", "XBOX", ((xbox.PACKAGE, "Microsoft.Xbox.App"),)),
    Launcher("armoury", "Armoury Crate", (("B9ECED6F.ArmouryCrateSE_qmba6cd70vzyy", "App"),
                                          ("B9ECED6F.ArmouryCrate_qmba6cd70vzyy", "App"))),
    Launcher("command", "Command Center", (("B9ECED6F.ASUSCommandCenter_qmba6cd70vzyy", "App"),)),
)
BY_KEY = {launcher.key: launcher for launcher in LAUNCHERS}


def packages(local: Path | None = None) -> Path:
    return (local or Path(os.environ.get("LOCALAPPDATA", ""))) / "Packages"


def find(launcher: Launcher, local: Path | None = None) -> str | None:
    """The application ID to start for *launcher*: its first app whose package Windows keeps for this user; None when
    none is here."""
    folder = packages(local)
    return next((f"{family}!{app}" for family, app in launcher.apps if (folder / family).is_dir()), None)


def start(app_id: str) -> None:
    """The app started as the Start menu starts it. OSError off Windows, or when Explorer does not start."""
    if os.name != "nt":
        raise OSError("Windows starts its apps by their ID")
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"])
