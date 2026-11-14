#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal's picture on the wiki's home page, taken from the portal itself:

    python3 tools/portal_screenshot.py [--out FILE]

It opens the portal's view offscreen on the apps.toml and the icons of this checkout, in a home folder of its
own (nothing is installed or changed on this computer), with a fixed demo state: every app installed but two, one
update (the notice and the red count on its category), a fixed status (the loads, the clock and the weather of a
place) and Sustainable open. Then it saves the
window as WebP, by default over docs/images/home/portal.webp. The wiki's workflow runs it before every build, so the published
picture always shows the portal as it is on main; run it by hand to see the same picture locally.

The window and the application are deleted here, in that order, once the picture is saved: left to the
interpreter's exit, Qt's multimedia backend (the portal's sound asks it for an audio output) and SDL (its controller
reader) went down in whatever order came, and on a runner without an audio device that crashed the process now and
then after the picture was written (03-11-2026, the wiki's workflow)."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

SUITE = Path(__file__).resolve().parent.parent      # the suite: bc250-bazzite/
ROOT = SUITE.parent
OUT = SUITE / "docs" / "images" / "home" / "portal.webp"
SIZE = (1280, 800)              # the window, in logical pixels: a handheld's screen
SCALE = 1.5                     # the picture is this much larger, for sharp text on high-DPI screens
CATEGORY = "sustainable"        # the category that is open
UPDATED = "gpu"                 # the app with an update
NOT_INSTALLED = {"oc", "acpi"}  # gray on the open tab, as an app that is not installed looks
LOADS, CLOCK = "CPU 12% 54°C | GPU 3% 61°C", "Thursday 11/5/26 | 07:44 PM CEST"   # not the runner's own
PLACE, WEATHER, SKY = "Amsterdam", "8°C  Partly cloudy", "partly"     # the status' third line: nothing is asked
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
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication
    from PyQt6.QtGui import QImage

    from bc250_core.platform import expand
    from bc250_portal import MANIFEST, glyphs
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
    window = mw.MainWindow(entries, Sources(home / "work"), records, desktop=home / "Desktop", menu=home / "menu",
                           music_player=mw.music.Silent())
    window.big.bar.setCurrentIndex(window.big.categories.index(CATEGORY))
    window.status_timer.stop()
    window.big.set_status(LOADS, CLOCK)
    window.big.set_weather(PLACE, WEATHER, glyphs.weather(SKY), True, "")
    window.resize(*SIZE)
    window.show()
    for _ in range(3):                                  # the layout, the reflow it starts, the start-up timers
        QCoreApplication.processEvents()
    window.big.focus_first()                            # as after the intro: the focus on the first tile
    QCoreApplication.processEvents()
    image = QImage(round(SIZE[0] * SCALE), round(SIZE[1] * SCALE), QImage.Format.Format_ARGB32)
    image.setDevicePixelRatio(SCALE)
    image.fill(window.palette().window().color())
    window.render(image)
    window.close()                                      # stops the intro, the sound, the controller and the workers
    sip.delete(window)                                  # and the window goes now, with the application still up
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
        from PyQt6 import sip
        from bc250_core.app import create_app
        from bc250_portal import INFO
        app = create_app(INFO)
        app.setPalette(dark_palette())
        image = render(home)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    saved = image.save(str(args.out), "WEBP", WEBP_QUALITY)
    if saved:
        print(f"{args.out}: {image.width()} x {image.height()}")
    else:
        print(f"{args.out}: could not be saved (no WebP support in this Qt?)", file=sys.stderr)
    del image
    app.processEvents()
    sip.delete(app)                                     # Qt goes down here, in order, not while Python exits
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
