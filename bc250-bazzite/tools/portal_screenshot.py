#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal's picture on the wiki's home page, taken from the portal itself:

    python3 tools/portal_screenshot.py [--out FILE]

It opens the portal's window offscreen on the apps.toml and the icons of this checkout, in a home folder of its
own (nothing is installed or changed on this computer), with a fixed demo state: every app installed but two, one
update (the notice and the red count on its tab) and the Sustainable tab open. Then it saves the window as WebP,
by default over docs/images/home/portal.webp. The wiki's workflow runs it before every build, so the published
picture always shows the portal as it is on main; run it by hand to see the same picture locally."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

SUITE = Path(__file__).resolve().parent.parent      # the suite: bc250-bazzite/
ROOT = SUITE.parent
OUT = SUITE / "docs" / "images" / "home" / "portal.webp"
SIZE = (1000, 780)              # the window, in logical pixels
SCALE = 1.6                     # the picture is this much larger, for sharp text on high-DPI screens
TAB = "sustainable"             # the tab that is open
UPDATED = "gpu"                 # the app with an update
NOT_INSTALLED = {"oc", "acpi"}  # gray on the open tab, as an app that is not installed looks
WEBP_QUALITY = 85

sys.path[:0] = [str(SUITE / "portal"), str(ROOT / "core")]


def older(version: str) -> str:
    """A version just before *version*: the installed one of the app with an update."""
    major, minor, patch = (int(p) for p in version.split("."))
    return (f"{major}.{minor}.{patch - 1}" if patch else f"{major}.{minor - 1}.0" if minor
            else f"{major - 1}.0.0")


def dark_palette():
    """Breeze Dark's colors, as Bazzite's desktop shows the portal; offscreen Qt has no desktop theme."""
    from PyQt6.QtGui import QColor, QPalette
    roles = QPalette.ColorRole
    palette = QPalette()
    for role, colour in ((roles.Window, "#202326"), (roles.WindowText, "#fcfcfc"), (roles.Base, "#141618"),
                         (roles.AlternateBase, "#1d1f22"), (roles.Text, "#fcfcfc"), (roles.Button, "#292c30"),
                         (roles.ButtonText, "#fcfcfc"), (roles.Highlight, "#3daee9"),
                         (roles.HighlightedText, "#fcfcfc"), (roles.Link, "#1d99f3"), (roles.Mid, "#43474d"),
                         (roles.Midlight, "#33373b"), (roles.Dark, "#101113"), (roles.Light, "#3d4146"),
                         (roles.PlaceholderText, "#a1a9b1"), (roles.ToolTipBase, "#292c30"),
                         (roles.ToolTipText, "#fcfcfc")):
        palette.setColor(role, QColor(colour))
    return palette


def render(home: Path):
    """The portal's window in the demo state, as a QImage SCALE times SIZE. Needs a QApplication; *home* is the home
    folder the portal sees (HOME and XDG_* must point into it already)."""
    from PyQt6.QtCore import QCoreApplication
    from PyQt6.QtGui import QImage

    from bc250_core.platform import expand
    from bc250_portal import MANIFEST
    from bc250_portal import main_window as mw
    from bc250_portal.manifest import load
    from bc250_portal.sources import Records, Sources

    entries = load(MANIFEST)
    records = Records(home / "installed.json")
    for entry in entries:
        if entry.key in NOT_INSTALLED:
            continue
        launcher = expand(entry.detect[0])
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text("#!/bin/sh\n", encoding="utf-8")
        records.set(entry.key, f"{entry.key}-v{older(entry.version)}" if entry.key == UPDATED
                    else entry.tag or "local")
    window = mw.MainWindow(entries, Sources(home / "work"), records, desktop=home / "Desktop", menu=home / "menu")
    window.tabs.setCurrentWidget(window.pages[TAB])
    window.resize(*SIZE)
    window.show()
    for _ in range(3):                                  # the layout, the reflow it starts, the start-up timers
        QCoreApplication.processEvents()
    image = QImage(round(SIZE[0] * SCALE), round(SIZE[1] * SCALE), QImage.Format.Format_ARGB32)
    image.setDevicePixelRatio(SCALE)
    image.fill(window.palette().window().color())
    window.render(image)
    window.close()
    return image


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT, help=f"the picture (default: {OUT.relative_to(SUITE)})")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="bc250-portal-picture-") as tmp:
        home = Path(tmp) / "home"
        for var in ("HOME", "USERPROFILE"):
            os.environ[var] = str(home)
        os.environ["XDG_DATA_HOME"] = str(home / ".local" / "share")
        os.environ["XDG_CONFIG_HOME"] = str(home / ".config")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from bc250_core.app import create_app
        from bc250_portal import INFO
        app = create_app(INFO)
        app.setPalette(dark_palette())
        image = render(home)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(args.out), "WEBP", WEBP_QUALITY):
        print(f"{args.out}: could not be saved (no WebP support in this Qt?)", file=sys.stderr)
        return 1
    print(f"{args.out}: {image.width()} x {image.height()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
