# SPDX-License-Identifier: GPL-3.0-or-later
"""The programs the portal starts from its tabs' line (owner, 07-11-2026: "buttons in the top row to start Steam,
XBOX, Armoury Crate and Command Center"): Steam through the window's own Steam action (RT), the others as Windows
starts a Start-menu app, by its application ID (shell:AppsFolder), never by a window's or a device's name.

An app is there when Windows keeps its package's folder for this user (%LOCALAPPDATA%\\Packages\\<family name>), as
core's xbox.installed() reads the XBOX app. Armoury Crate is ASUS's: Armoury Crate SE on the ROG Ally and XBOX Ally,
Armoury Crate on ASUS's laptops; Command Center is Armoury Crate SE's overlay, a package of its own. Elsewhere the
button says it is not on this device. The IDs as Windows lists them on the owner's ROG XBOX Ally X (07-11-2026:
Get-StartApps, the packages' AppxManifest.xml).

Each button shows its program's own icon (owner, 07-11-2026: symbols, not text), read from the device when the portal
starts: an app's Start-menu logo from its package, Steam's from its steam.exe. None of it is in the suite; a program
that is not there shows its initials. Command Center has the suite's own symbol, as ASUS gives it Armoury Crate's
icon, and so does XBOX mode ↔ Desktop, Windows' Win + F11."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from bc250_core import xbox

STEAM, XBOX_MODE = "steam", "xboxmode"
REPOSITORY = r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages"


@dataclass(frozen=True)
class Launcher:
    key: str
    name: str                                   # on its button, on hover
    apps: tuple[tuple[str, str], ...] = ()      # (package family name, app ID in it), the first one there is started
    own_symbol: bool = False                    # the suite's drawn symbol, not the app's icon
    keys: tuple[str, ...] = ()                  # pressed as the keyboard would, instead of starting the app
    verb: str = "Start"                         # before the name in the row at the bottom: A Start XBOX

    def app_ids(self) -> list[str]:
        return [f"{family}!{app}" for family, app in self.apps]


LAUNCHERS = (
    Launcher(STEAM, "Steam"),
    Launcher("xbox", "XBOX", ((xbox.PACKAGE, "Microsoft.Xbox.App"),)),
    # Windows' switch between XBOX mode and the desktop, Win + F11, as the Settings page's row (owner, 07-11-2026)
    Launcher(XBOX_MODE, "XBOX mode ↔ Desktop", own_symbol=True, verb=""),
    Launcher("armoury", "Armoury Crate", (("B9ECED6F.ArmouryCrateSE_qmba6cd70vzyy", "App"),
                                          ("B9ECED6F.ArmouryCrate_qmba6cd70vzyy", "App"))),
    # ASUS gives Command Center Armoury Crate's icon: the suite's own symbol tells them apart (sliders). Its own app ID
    # opens Armoury Crate (owner, 07-11-2026), and nothing else of ASUS's opens it but its button and a keyboard
    # shortcut the user sets in Armoury Crate SE: the suite's is Ctrl + Alt + C, pressed here
    Launcher("command", "Command Center", (("B9ECED6F.ASUSCommandCenter_qmba6cd70vzyy", "App"),), own_symbol=True,
             keys=("Ctrl", "Alt", "C"), verb="Open"),
)
BY_KEY = {launcher.key: launcher for launcher in LAUNCHERS}


def packages(local: Path | None = None) -> Path:
    return (local or Path(os.environ.get("LOCALAPPDATA", ""))) / "Packages"


def find(launcher: Launcher, local: Path | None = None) -> str | None:
    """The application ID to start for *launcher*: its first app whose package Windows keeps for this user; None when
    none is here."""
    folder = packages(local)
    return next((f"{family}!{app}" for family, app in launcher.apps if (folder / family).is_dir()), None)


def package_root(family: str) -> Path | None:
    """The folder of the newest version of the package *family* installed for this user, as Windows' own list of
    packages has it (only read): HKCU\\...\\AppModel\\Repository\\Packages\\<full name>, PackageRootFolder. None off
    Windows or when it is not installed."""
    if os.name != "nt":
        return None
    import winreg
    name, _, publisher = family.rpartition("_")
    found: list[tuple[tuple[int, ...], str]] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REPOSITORY) as packages_key:
            for index in range(winreg.QueryInfoKey(packages_key)[0]):
                full = winreg.EnumKey(packages_key, index)
                if full.startswith(f"{name}_") and full.endswith(f"__{publisher}"):
                    found.append((_version(full.split("_")[1]), full))
            if not found:
                return None
            with winreg.OpenKey(packages_key, max(found)[1]) as key:
                return Path(str(winreg.QueryValueEx(key, "PackageRootFolder")[0]))
    except OSError:
        return None


def _version(text: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError:
        return ()


def logo(root: Path, app: str) -> Path | None:
    """The Start menu's icon of *app* in the package at *root*: its manifest's Square44x44Logo, in the largest size the
    package has, on no plate (transparent) where it has one. None when the manifest or the picture is not there."""
    try:
        tree = ElementTree.parse(root / "AppxManifest.xml")
    except (OSError, ElementTree.ParseError):
        return None
    named = ""
    for element in tree.iter():
        if element.tag.endswith("}Application") and element.get("Id") == app:
            named = next((child.get("Square44x44Logo", "") for child in element.iter()
                          if child.tag.endswith("}VisualElements")), "")
            break
    if not named:
        return None
    picture = root / Path(named.replace("\\", "/"))
    if picture.is_file():
        return picture
    best: tuple[int, int, Path] | None = None
    for candidate in (picture.parent.glob(f"{picture.stem}.*{picture.suffix}") if picture.parent.is_dir() else ()):
        qualifiers = candidate.name[len(picture.stem) + 1:-len(picture.suffix)].split("_")
        if any(q.startswith("contrast-") or q == "altform-lightunplated" for q in qualifiers):
            continue                                    # high contrast, or for a light background
        size = next((int(q.split("-")[1]) for q in qualifiers if q.startswith("targetsize-")
                     and q.split("-")[1].isdigit()), 88 if "scale-200" in qualifiers else 0)
        rank = (size, int("altform-unplated" in qualifiers), candidate)
        if best is None or rank[:2] > best[:2]:
            best = rank
    return best[2] if best is not None else None


def exe_icon(program: Path, size: int = 256):
    """*program*'s own icon (its first) at *size* pixels as a QImage, as Windows extracts it (SHDefExtractIconW); None
    off Windows or when it has none."""
    if os.name != "nt" or not program.is_file():
        return None
    import ctypes
    from ctypes import wintypes

    from PyQt6.QtGui import QImage
    handle = wintypes.HICON()
    shell32, user32 = ctypes.windll.shell32, ctypes.windll.user32
    if shell32.SHDefExtractIconW(str(program), 0, 0, ctypes.byref(handle), None, size) != 0 or not handle.value:
        return None
    try:
        image = QImage.fromHICON(ctypes.c_void_p(handle.value).value)
    finally:
        user32.DestroyIcon(handle)
    return None if image.isNull() else image


def icon_file(launcher: Launcher) -> Path | None:
    """The icon of *launcher*'s program as the device has it (its first app installed); None for Steam (its
    steam.exe's icon, read by the window) and when none is installed."""
    for family, app in launcher.apps:
        root = package_root(family)
        found = logo(root, app) if root is not None else None
        if found is not None:
            return found
    return None


VIRTUAL_KEYS = {"Ctrl": 0x11, "Alt": 0x12, "Shift": 0x10, "Win": 0x5B, "F11": 0x7A}


def virtual_keys(names: tuple[str, ...]) -> list[int]:
    """Windows' virtual-key codes of *names*: the modifiers and F11 by name, a letter or a digit as itself."""
    return [VIRTUAL_KEYS.get(name) or ord(name.upper()) for name in names]


def press_keys(names: tuple[str, ...]) -> None:
    """*names* pressed together as the keyboard would (keybd_event), released in reverse. OSError off Windows."""
    if os.name != "nt":
        raise OSError("the keys are pressed on Windows")
    import ctypes
    user32 = ctypes.windll.user32
    codes, up = virtual_keys(names), 0x0002         # KEYEVENTF_KEYUP
    for code in codes:
        user32.keybd_event(code, 0, 0, 0)
    for code in reversed(codes):
        user32.keybd_event(code, 0, up, 0)


def start(app_id: str) -> None:
    """The app started as the Start menu starts it. OSError off Windows, or when Explorer does not start."""
    if os.name != "nt":
        raise OSError("Windows starts its apps by their ID")
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"])
