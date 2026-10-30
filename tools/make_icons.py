#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write ICONS.md: every icon of the suites, per suite, and where it is used:

    python3 tools/make_icons.py            # write ICONS.md and render the drawn icons to docs/design/icons/
    python3 tools/make_icons.py --check    # only say whether ICONS.md is up to date; exit 1 when it is not

Pictures are shown from their own files. The icons drawn in code (the portal's symbols, the desktop style's icons)
are rendered with PyQt6 to PNGs in docs/design/icons/, on Gunmetal's window color. The listing is the data below:
change it here and run the script, not ICONS.md itself. --check needs no Qt."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITE_DIR = "bc250-bazzite"                 # the BC250 Bazzite Suite's folder: its pictures are under it
OUT = f"{SUITE_DIR}/docs/design/icons"
MDI = "https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg"      # Material Design Icons, as MkDocs Material bundles them
# The names of icons/categories.toml's entries the portal's manifest does not list: launches of an app, and the
# suite's tool that runs from the checkout.
LAUNCHES = {"cu-unlock": "CU Unlock (the CU Bisect app's Unlock)",
            "cores-unlock": "Cores Unlock (the Cores Bisect app's Unlock)",
            "installer-tests": "BC-250 Installer Tests"}

SUITE_ICON = [
    ("bc250-bazzite/portal/images/bc250-bazzite-suite.webp", "`portal/images/bc250-bazzite-suite.webp` (512 px)",
     "The portal's window header (a click opens the wiki) and its window icon; Suite Big Picture Mode's header; the "
     "portal's release in Nexus Release Tool."),
    ("bc250-bazzite/portal/images/bc250-bazzite-suite-1024.webp", "`portal/images/bc250-bazzite-suite-1024.webp`",
     "The intro of Suite Big Picture Mode."),
    ("bc250-bazzite/portal/images/bc250-bazzite-suite-128.png", "`portal/images/bc250-bazzite-suite-128.png`",
     "The portal's menu entry and Desktop icon."),
    ("bc250-bazzite/portal/images/apps/portal.webp", "`portal/images/apps/portal.webp` (128 px)", "The portal's own tile."),
    ("bc250-bazzite/docs/images/wiki-icon.webp", "`docs/images/wiki-icon.webp`, `.png`",
     "The wiki's header logo, its home page's footer and its favicon."),
]

# name, the glyph function, its color ("ink" is the theme's text, "red" the update red), a red circle behind it
GLYPHS = [
    ("portal-install", "install", "ink", False, "Install", "An app's install button: an arrow down into a tray."),
    ("portal-install-update", "install", "red", False, "Install, update",
     "The same button in red when an update is waiting."),
    ("portal-reinstall", "reinstall", "red", False, "Reinstall",
     "The install button of an app whose version the portal does not know (red), a circular arrow."),
    ("portal-reinstall-badge", "reinstall", "white", True, "Reinstall badge",
     "On a tile, in the portal and in Suite Big Picture Mode: the app needs a reinstall."),
    ("portal-uninstall", "uninstall", "ink", False, "Uninstall", "An app's uninstall button: a waste bin."),
]

APP_ICONS = [
    ("bc250-bazzite/apps/ncgui/images/icons/connect.png", "`apps/ncgui/images/icons/connect.png`",
     "Bazzite NetcatGUI: Connect (the Silk icons of the original tool, CC-BY 2.5, Mark James)."),
    ("bc250-bazzite/apps/ncgui/images/icons/listen.png", "`apps/ncgui/images/icons/listen.png`", "Bazzite NetcatGUI: Listen."),
    ("bc250-bazzite/apps/ncgui/images/icons/save.png", "`apps/ncgui/images/icons/save.png`", "Bazzite NetcatGUI: Save."),
    ("bc250-bazzite/apps/pcsx2/pcsx2_manager/arrow-down.svg", "`apps/<app>/<package>/arrow-down.svg`",
     "The arrow of a choice box in PCSX2 Manager, RPCS3 Manager and shadPS4 Manager (a copy in each)."),
]

# name, the standard pixmap, the icon theme's name tried first (or ""), the name shown
STANDARD = [
    ("qt-warning", "SP_MessageBoxWarning", "", "`SP_MessageBoxWarning`",
     "BC-250 Bazzite Test: a warning in the results; the warning before a run."),
    ("qt-information", "SP_MessageBoxInformation", "", "`SP_MessageBoxInformation`",
     "BC-250 Bazzite Test: an info result. Dependency Checker: the About button."),
    ("qt-reload", "SP_BrowserReload", "view-refresh", "`view-refresh`, else `SP_BrowserReload`",
     "Dependency Checker: the Check button."),
]

MATERIAL = [
    ("stethoscope", "Home: the card \"Diagnostics\"."),
    ("speedometer", "Home: the card \"Tuning\"."),
    ("lock-open-variant", "Home: the card \"Unlocks\"."),
    ("gamepad-variant", "Home: the cards \"Gaming\" and \"PlayStation\"."),
    ("television", "Home: the card \"Living room\"."),
    ("download", "Home: the Download button."),
    ("tray-arrow-down", "The page icon of Install."),
    ("eye-off-outline", "The page icon of Privacy."),
    ("shield-lock-outline", "The page icon of Security."),
]

WINDOWS_PORTABLE_ICON = [
    ("windows-portable/icons/windows-portable-256.png",
     "`windows-portable/icons/windows-portable-<size>.png` (1024, 512, 256 and 128 px)",
     "The icon of the Windows Portable Suite, the owner's drawing (26-10-2026): the set its portal's and wiki's "
     "copies are made from."),
    ("windows-portable/icons/windows-portable-white.png", "`windows-portable/icons/windows-portable-white.png` "
     "(1024 x 514)", "The white handheld, the owner's picture (29-10-2026, cropped to the handheld): the hero of the "
     "suite's wiki home, as the "
     "board is the BC250 wiki's."),
    ("windows-portable/apps/test/images/windows-portable-test.webp",
     "`windows-portable/apps/test/images/windows-portable-test.webp` (512 px), `-128.png`",
     "Windows Portable Test, the suite's test app: the suite's icon (the test app is the suite's base, as BC-250 "
     "Bazzite Test is the BC250 suite's), its window header and window icon, and its Start-menu shortcut. Lossless "
     "copies of the drawing, written by this tool."),
    ("windows-portable/portal/images/windows-portable-suite.webp",
     "`windows-portable/portal/images/windows-portable-suite.webp` (512 px), `-128.png`",
     "The Windows Portable Suite's portal: its window icon and its Start-menu shortcut, and the portal's release in "
     "Nexus Release Tool. Lossless copies of the drawing, written by this tool."),
    ("windows-portable/docs/images/wiki-icon.webp", "`windows-portable/docs/images/wiki-icon.webp`, `.png` (256 px)",
     "The suite's wiki: the header logo (`.webp`) and the favicon (`.png`), written by this tool."),
    ("windows-portable/docs/images/home/device.webp", "`windows-portable/docs/images/home/device.webp` (1024 x 514)",
     "The suite's wiki home: the handheld under the headline, a WebP copy of the owner's white handheld."),
    ("windows-portable/docs/images/home/portal.webp", "`windows-portable/docs/images/home/portal.webp` (1280 x 720)",
     "The suite's wiki home, One portal for every app: the portal at the Ally's 1280 x 720, rendered offscreen with "
     "the suite's apps.toml (Windows Portable Test installed), as WebP."),
    ("windows-portable/docs/images/apps/test.webp", "`windows-portable/docs/images/apps/<key>.webp` (256 px)",
     "An app's chapter in the suite's wiki: its icon at the top, a WebP copy of the app's drawing."),
    ("windows-portable/portal/images/apps/test.webp", "`windows-portable/portal/images/apps/<key>.webp` (256 px)",
     "The icon on an app's tile in the portal: Windows Portable Test's is the suite's drawing, written by this tool; "
     "another app's is a copy of its own icon."),
]
WINDOWS_PORTABLE_COPIES = [
    ("windows-portable/icons/windows-portable-512.png", "windows-portable/apps/test/images/windows-portable-test.webp"),
    ("windows-portable/icons/windows-portable-128.png",
     "windows-portable/apps/test/images/windows-portable-test-128.png"),
    ("windows-portable/icons/windows-portable-512.png", "windows-portable/portal/images/windows-portable-suite.webp"),
    ("windows-portable/icons/windows-portable-128.png",
     "windows-portable/portal/images/windows-portable-suite-128.png"),
    ("windows-portable/icons/windows-portable-256.png", "windows-portable/portal/images/apps/test.webp"),
    ("windows-portable/icons/windows-portable-256.png", "windows-portable/docs/images/wiki-icon.png"),
]
NEXUS_ICON = [
    ("nexus/images/nexus-256.png", "`nexus/images/nexus-<size>.png` (1024, 512, 256 and 128 px)",
     "The icon of Nexus, the owner's drawing (25-10-2026): the set the copies are made from."),
    ("nexus/docs/images/nexus.webp", "`nexus/docs/images/nexus.webp`, `.png` (256 px)",
     "The Nexus page's header logo and its home page's footer (`.webp`), and its favicon (`.png`): the 256 px "
     "drawing, transparent (owner, 27-10-2026: no more dark tile), both written by this tool."),
    ("nexus/docs/images/nexus-hero.webp", "`nexus/docs/images/nexus-hero.webp` (1024 px)",
     "The Nexus page's home: the icon under the headline, a WebP copy of the 1024 px drawing."),
    ("dev/nrt/images/nexus-release-tool.webp", "`dev/nrt/images/nexus-release-tool.webp` (512 px), `-128.png`",
     "Nexus Release Tool, Nexus's app (owner, 26-10-2026: it takes Nexus's icon, not a category's): its window header "
     "and window icon, its menu entry and Desktop icon. Lossless copies of the drawing, written by this tool."),
]
# the Nexus Release Tool's icons: the drawing at each size, lossless (the pixels stay the drawing's), by this tool.
NEXUS_COPIES = [
    ("nexus/images/nexus-512.png", "dev/nrt/images/nexus-release-tool.webp"),
    ("nexus/images/nexus-128.png", "dev/nrt/images/nexus-release-tool-128.png"),
    ("nexus/images/nexus-256.png", "nexus/docs/images/nexus.png"),      # the Nexus page's favicon
]
# The Nexus page's logo and hero: pictures on a web page, so lossy WebP at this quality, by this tool since
# 27-10-2026 (the owner's new drawing had no WebP copies yet). The logo is the favicon's picture (the 256 px
# drawing, written first, in NEXUS_COPIES), the hero the 1024 px drawing.
NEXUS_PAGE_COPIES = [
    ("nexus/docs/images/nexus.png", "nexus/docs/images/nexus.webp"),
    ("nexus/images/nexus-1024.png", "nexus/docs/images/nexus-hero.webp"),
    # The Windows Portable Suite's wiki: its logo, the home's handheld and the apps' icons in their chapters.
    ("windows-portable/icons/windows-portable-256.png", "windows-portable/docs/images/wiki-icon.webp"),
    ("windows-portable/icons/windows-portable-white.png", "windows-portable/docs/images/home/device.webp"),
    ("windows-portable/icons/windows-portable-256.png", "windows-portable/docs/images/apps/test.webp"),
]
PAGE_QUALITY = 90
# The Windows Portable Suite's category icons: icons/<category>/<category>-<size>.png (1024, 512, 256 and 128 px),
# each made from a picture of the owner's. Every app of the suite but the test app (which has the suite's drawing)
# takes its category's: windows_portable_app_copies() names the copies from the portal's apps.toml.
WINDOWS_PORTABLE = "windows-portable"
WINDOWS_PORTABLE_CATEGORIES = {
    "gaming": "the owner's pictures of the handheld (29-10-2026), wide (2:1: 1024 x 512 down to 128 x 64): the tile and "
              "the wiki show them as they are, the window, program and Start-menu icons centered on a transparent "
              "square",
}


def windows_portable_apps(root: Path = ROOT) -> list[tuple[str, str, str, str]]:
    """The suite's apps that take their category's icon: (key, name, category, app id), the app id from the
    package's APP_ID (apps/<key>/<package>/__init__.py)."""
    suite = root / WINDOWS_PORTABLE
    apps = tomllib.loads((suite / "portal" / "apps.toml").read_text(encoding="utf-8")).get("apps", {})
    found = []
    for key, entry in apps.items():
        if entry.get("required"):
            continue                                    # the test app: the suite's own drawing
        inits = sorted((suite / "apps" / key).glob("*/__init__.py"))
        ids = [m[1] for init in inits for m in [re.search(r'^APP_ID = "([^"]+)"', init.read_text(encoding="utf-8"),
                                                          re.M)] if m]
        if ids:
            found.append((key, entry.get("name", key), entry["category"], ids[0]))
    return found


def windows_portable_app_copies(root: Path = ROOT) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """The icon copies of each app that takes its category's (lossless) and its chapter's icon in the wiki (a
    picture on a page, lossy): the 512 px icon for the window, the 128 px one for the Start menu and the tile, the
    256 px one for the wiki."""
    exact, page = [], []
    for key, _, category, app_id in windows_portable_apps(root):         # SQUARE: the window and program icons
        icons = f"{WINDOWS_PORTABLE}/icons/{category}/{category}"
        exact += [(f"{icons}-512.png", f"{WINDOWS_PORTABLE}/apps/{key}/images/{app_id}.webp"),
                  (f"{icons}-128.png", f"{WINDOWS_PORTABLE}/apps/{key}/images/{app_id}-128.png"),
                  (f"{icons}-256.png", f"{WINDOWS_PORTABLE}/portal/images/apps/{key}.webp")]   # sharp when wide
        page.append((f"{icons}-256.png", f"{WINDOWS_PORTABLE}/docs/images/apps/{key}.webp"))
    return exact, page


def nexus_copies(root: Path = ROOT) -> list[Path]:
    """Writes the Nexus Release Tool's icon copies and the Nexus page's favicon from the Nexus drawings (NEXUS_COPIES) and
    Windows Portable Test's and the Windows portal's from the suite's (WINDOWS_PORTABLE_COPIES), lossless, so a
    copy's pixels are the drawing's (tests compare them); and the Nexus page's logo and hero (NEXUS_PAGE_COPIES),
    lossy; and every Windows Portable Suite app's category icon (windows_portable_icons()). The paths written."""
    return write_copies(root, NEXUS_COPIES + WINDOWS_PORTABLE_COPIES, NEXUS_PAGE_COPIES) + windows_portable_icons(root)


def windows_portable_icons(root: Path = ROOT) -> list[Path]:
    """The copies of each Windows Portable Suite app's category icon (tools/new_app.py writes a new app's with
    this). The paths written."""
    exact, page = windows_portable_app_copies(root)
    return write_copies(root, exact, page)


def square_target(target: str) -> bool:
    """A Windows Portable Suite app's window and program icon (images/<app id>.webp, PyInstaller's --icon) and its
    Start-menu picture (-128.png): a Windows icon is square, so a wide category picture is centered on a transparent
    square there (owner, 28-10-2026: the Gaming pictures are 2:1)."""
    return target.startswith(f"{WINDOWS_PORTABLE}/apps/") and "/images/" in target


def write_copies(root: Path, exact: list[tuple[str, str]], page: list[tuple[str, str]]) -> list[Path]:
    """Each (source, target): *exact* lossless (a PNG, or WebP with the pixels under alpha 0 too), *page* as a
    picture on a web page (lossy WebP at PAGE_QUALITY). A wide picture for a square target (square_target()) is
    centered on a transparent square."""
    from PIL import Image
    written = []
    for (source, target), lossy in [*((pair, False) for pair in exact), *((pair, True) for pair in page)]:
        path = root / target
        path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(root / source) as image:
            image = image.convert("RGBA")
            if square_target(target) and image.width != image.height:
                side = max(image.size)
                canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
                image = canvas
            if lossy:
                image.save(path, "WEBP", quality=PAGE_QUALITY, method=6)
            elif path.suffix == ".png":
                image.save(path, "PNG", optimize=True)
            else:
                image.save(path, "WEBP", lossless=True, exact=True, method=6)
        written.append(path)
    return written


WINDOWS_PORTABLE_MATERIAL = [
    ("stethoscope", "Home: the card \"Sustainable\"."),
    ("gamepad-variant", "Home: the card \"Gaming\"."),
    ("download", "Home: the Download button."),
]

NEXUS_MATERIAL = [
    ("file-tree", "Home: the card \"Nexus\"."),
    ("view-grid", "Home: the card \"A suite\"."),
    ("application", "Home: the card \"An app\"."),
    ("chip", "Home: the card \"BC250 Bazzite Suite\"."),
    ("controller", "Home: the card \"Windows Portable Suite\"."),
    ("download", "Home: the Nexus index button."),
]

SYMBOLS = [
    ("✔ ⚠", "BC-250 Persistent ACPI", "The state: installed, incomplete."),
    ("▶", "BC-250 BIOS Reader", "The selected prompt."),
    ("→ ← ↑ ↓", "BC-250 BIOS Reader", "The keys in the legend."),
    ("▶ ■ ◀", "BC-250 Bazzite Test", "Run all tests, Stop, Back."),
    ("⚠", "BC-250 Bazzite Test", "The integrity banner, a score's warnings."),
    ("💡", "BC-250 Bazzite Test", "A hint in the findings."),
    ("✔ • ! ✖", "BC-250 Bazzite Test", "In-game: the checks' ok, info, warning, error."),
    ("↓ ↑", "BC-250 Bazzite Test", "Live status: download and upload."),
    ("🎮", "BC-250 Bazzite Test", "Live status: the game that runs."),
    ("✕", "BC-250 Bazzite Test", "The round close button (drawn, not a font glyph)."),
    ("✖ ⚠ ●", "BC-250 GPU Governor Manager", "Safe points: an error, a warning, a test that runs."),
    ("✓ ✗", "Console Link", "The controller test's checks."),
    ("△ ○ □ ◇ ◆ ★", "Bazzite DatStation", "The front page's features: Quiz, History, Region Codes, User Guides, "
                                            "PS News, Scores & Trophies."),
    ("★", "Bazzite DatStation", "Stars, a perfect round, trophies."),
    ("←", "Bazzite DatStation", "Back."),
    ("✓ !", "USB HD Cam", "A check found or missing."),
    ("✓ !", "USB HD Control", "A check known or not."),
    ("△ □ ✕ ○", "USB HD Control", "The face buttons."),
    ("↓ ↑", "USB IPS3.5", "The network tile: download and upload."),
    ("↓ ↑", "System Overlay", "Network: download and upload."),
    ("✓ ✗", "Dependency Checker", "CVE: none found, found."),
    ("⚠ ✓ ✗", "Bazzite SFTP Tools", "Password: a warning, requirements met, not met."),
    ("← ↑ ↓", "Bazzite SFTP Tools", "Download; uploads and downloads in the transfer queue."),
    ("↑ ↓", "Nexus Release Tool", "Earlier commands, in the command line's placeholder."),
    ("●", "Every app on core", "The dot of a status box (`bc250_core/widgets.py`)."),
    ("●", "Portal", "Outside the suite."),
    ("✓ ✗", "BC-250 Installer Tests", "A test passed, failed."),
]


def img(path: str, width: int = 48) -> str:
    return f'<img src="{path}" width="{width}" alt="">'


def table(header: str, rows) -> list[str]:
    return [f"| {' | '.join(header.split(','))} |", "| --- | --- | --- |",
            *(f"| {' | '.join(row)} |" for row in rows), ""]


def rendered(name: str) -> str:
    return f"{OUT}/{name}.png"


def build(root: Path = ROOT) -> str:
    """ICONS.md's text, from the data above, the portal's manifest and icons/categories.toml."""
    suite = root / SUITE_DIR
    apps = tomllib.loads((suite / "portal" / "apps.toml").read_text(encoding="utf-8"))
    names = {k: v["name"] for k, v in apps.get("apps", {}).items()} | LAUNCHES
    by_category: dict[str, list[str]] = {}
    for key, entry in tomllib.loads((suite / "icons" / "categories.toml").read_text(encoding="utf-8")).items():
        by_category.setdefault(entry["category"], []).append(key)

    out = ["# Icons", "",
           "The icons of the project, per suite, and where each is used. Pictures are shown from their own files; "
           "icons drawn\nin code are rendered to `bc250-bazzite/docs/design/icons/`. Written by `tools/make_icons.py`: "
           "change the listing\nthere and run it. The paths of the BC250 Bazzite Suite's section are relative to its "
           "folder, `bc250-bazzite/`.", "",
           "## BC250 Bazzite Suite", "", "### The suite's icon", ""]
    out += table("Icon,File,Used for", ((img(path), file, use) for path, file, use in SUITE_ICON))
    out += ["### The category icons", "",
            "Every app has the icon of its category: `icons/categories.toml` assigns them, `tools/sync_icons.py` "
            "copies each\ncategory's icon (`icons/<category>/`, at 1024, 512, 256 and 128 px) to these places:", "",
            "- `apps/<app>/images/<icon>.webp` (512 px): the app's window header (96 px), its window and tray icon, "
            "and the\n  logo at the top of its chapter in the wiki.",
            "- `apps/<app>/images/<icon>-128.png`: the app's menu entry and Desktop icon.",
            "- `portal/images/apps/<key>.webp` (256 px): the app's tile in the portal, and its icon in the wiki's app "
            "tables.",
            "- `portal/images/categories/<category>.webp` (512 px): the category in Suite Big Picture Mode.",
            "- In the wiki, the category's own icon (256 px) in the table of categories.", ""]
    out += table("Icon,Category,Apps", (
        (img(f"{SUITE_DIR}/icons/{category}/{category}-128.png", 64), category.title(),
         "<br>".join(f"{names.get(k, k)} (`{k}`)" for k in keys)) for category, keys in sorted(by_category.items())))
    out += ["### The portal's symbols", "",
            "Drawn with QPainter in `portal/bc250_portal/glyphs.py`, in the theme's text color (shown here on "
            "Gunmetal) or red.", ""]
    out += table("Icon,Name,Used for", ((img(rendered(name)), title, use) for name, *_, title, use in GLYPHS))
    out += ["### Icons in the apps", ""]
    out += table("Icon,File,Used for", ((img(path, 16), file, use) for path, file, use in APP_ICONS))
    out += ["### The desktop style's icons", "",
            "Icons the apps take from the desktop's style or icon theme, so they look different on every desktop; "
            "shown here as\nQt's Fusion style draws them.", ""]
    out += table("Icon,Name,Used for", ((img(rendered(name)), shown, use) for name, _, _, shown, use in STANDARD))
    out += ["### Material Design icons in the wiki", "", "Drawn by MkDocs Material in the wiki's colors.", ""]
    out += table("Icon,Name,Used for", ((img(f"{MDI}/{name}.svg", 24), f"`material-{name}`", use)
                                        for name, use in MATERIAL))
    out += ["### Symbols in text", "", "Characters of the font, used as icons in labels and buttons.", ""]
    out += table("Symbol,App,Used for", SYMBOLS)
    out += ["## Windows Portable Suite", "", "### The suite's icon", ""]
    out += table("Icon,File,Used for", ((img(path), file, use) for path, file, use in WINDOWS_PORTABLE_ICON))
    by_category: dict[str, list[str]] = {}
    for key, name, category, _ in windows_portable_apps(root):
        by_category.setdefault(category, []).append(f"{name} (`{key}`)")
    out += ["### The category icons", "",
            "Every app but Windows Portable Test has the icon of its category: `windows-portable/icons/<category>/` "
            "at 1024, 512,\n256 and 128 px (PNG), copied by this tool from the portal's `apps.toml` to the app's "
            "`images/<app id>.webp` (512 px)\nand `-128.png`, its tile `portal/images/apps/<key>.webp` (256 px) and its "
            "chapter's icon `docs/images/apps/<key>.webp`\n(256 px).", ""]
    out += table("Icon,Category,Apps", (
        (img(f"{WINDOWS_PORTABLE}/icons/{category}/{category}-128.png", 64),
         f"{category.title()}: {source}", "<br>".join(by_category.get(category, [])))
        for category, source in sorted(WINDOWS_PORTABLE_CATEGORIES.items())))
    out += ["### Material Design icons in the wiki", "", "Drawn by MkDocs Material in the wiki's colors.", ""]
    out += table("Icon,Name,Used for", ((img(f"{MDI}/{name}.svg", 24), f"`material-{name}`", use)
                                        for name, use in WINDOWS_PORTABLE_MATERIAL))
    out += ["## Nexus", "", "### The Nexus icon", ""]
    out += table("Icon,File,Used for", ((img(path), file, use) for path, file, use in NEXUS_ICON))
    out += ["### Material Design icons on the Nexus page", "", "Drawn by MkDocs Material in the page's colors.", ""]
    out += table("Icon,Name,Used for", ((img(f"{MDI}/{name}.svg", 24), f"`material-{name}`", use)
                                        for name, use in NEXUS_MATERIAL))
    return "\n".join(out).rstrip("\n") + "\n"


def render(root: Path = ROOT) -> list[Path]:
    """The drawn icons as PNGs in docs/design/icons/, each 48 px on a rounded square of Gunmetal's window color."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path[:0] = [str(root / SUITE_DIR / "portal"), str(root / "core")]
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QIcon, QImage, QPainter
    from PyQt6.QtWidgets import QApplication, QStyle

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    from bc250_core.theme import RED, THEMES
    from bc250_portal import glyphs

    gunmetal = THEMES["gunmetal"]
    colours = {"ink": gunmetal.text, "red": RED, "white": "white"}

    def save(name: str, icon: QIcon, circle: str | None = None, size: int = 48) -> Path:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(gunmetal.window))
        p.drawRoundedRect(QRectF(0, 0, size, size), 8, 8)
        inset = 8
        if circle:
            p.setBrush(QColor(circle))
            p.drawEllipse(QRectF(6, 6, size - 12, size - 12))
            inset = 14
        p.drawPixmap(inset, inset, icon.pixmap(size - 2 * inset, size - 2 * inset))
        p.end()
        path = root / rendered(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(path))
        return path

    written = [save(name, getattr(glyphs, glyph)(colours[colour]), RED if circle else None)
               for name, glyph, colour, circle, *_ in GLYPHS]
    style = app.style()
    for name, pixmap, theme_name, *_ in STANDARD:
        icon = style.standardIcon(getattr(QStyle.StandardPixmap, pixmap))
        written.append(save(name, QIcon.fromTheme(theme_name, icon) if theme_name else icon))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only say whether ICONS.md is up to date")
    args = parser.parse_args(argv)
    if not args.check:
        nexus_copies()
    text, path = build(), ROOT / "ICONS.md"
    if args.check:
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        if current != text:
            print("ICONS.md is out of date: run python3 tools/make_icons.py")
            return 1
        print("ICONS.md is up to date")
        return 0
    render()
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote ICONS.md and {len(GLYPHS) + len(STANDARD)} icons in {OUT}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
