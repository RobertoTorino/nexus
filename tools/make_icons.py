#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write ICONS.md: every icon of the suites, per suite, and where it is used:

    python3 tools/make_icons.py            # write ICONS.md and render the drawn icons to docs/design/icons/
    python3 tools/make_icons.py --check    # only say whether ICONS.md is up to date; exit 1 when it is not

Pictures are shown from their own files. The icons drawn in code (the portal's symbols, the desktop style's icons)
are rendered with PyQt6 to PNGs in docs/design/icons/, on Gunmetal's window colour. The listing is the data below:
change it here and run the script, not ICONS.md itself. --check needs no Qt."""

from __future__ import annotations

import argparse
import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = "docs/design/icons"
MDI = "https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg"      # Material Design Icons, as MkDocs Material bundles them
LAUNCHES = {"cu-unlock": "CU Unlock (the CU Bisect app's Unlock)",
            "cores-unlock": "Cores Unlock (the Cores Bisect app's Unlock)"}

SUITE_ICON = [
    ("portal/images/bc250-bazzite-suite.webp", "`portal/images/bc250-bazzite-suite.webp` (512 px)",
     "The portal's window header (a click opens the wiki) and its window icon; Suite Big Picture Mode's header; the "
     "portal's release in Suite Releases."),
    ("portal/images/bc250-bazzite-suite-1024.webp", "`portal/images/bc250-bazzite-suite-1024.webp`",
     "The intro of Suite Big Picture Mode."),
    ("portal/images/bc250-bazzite-suite-128.png", "`portal/images/bc250-bazzite-suite-128.png`",
     "The portal's menu entry and Desktop icon."),
    ("portal/images/apps/portal.webp", "`portal/images/apps/portal.webp` (128 px)", "The portal's own tile."),
    ("docs/images/wiki-icon.webp", "`docs/images/wiki-icon.webp`, `.png`",
     "The wiki's header logo, its home page's footer and its favicon."),
]

# name, the glyph function, its colour ("ink" is the theme's text, "red" the update red), a red circle behind it
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
    ("apps/ncgui/images/icons/connect.png", "`apps/ncgui/images/icons/connect.png`",
     "Bazzite NetcatGUI: Connect (the Silk icons of the original tool, CC-BY 2.5, Mark James)."),
    ("apps/ncgui/images/icons/listen.png", "`apps/ncgui/images/icons/listen.png`", "Bazzite NetcatGUI: Listen."),
    ("apps/ncgui/images/icons/save.png", "`apps/ncgui/images/icons/save.png`", "Bazzite NetcatGUI: Save."),
    ("apps/pcsx2/pcsx2_manager/arrow-down.svg", "`apps/<app>/<package>/arrow-down.svg`",
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
    ("github", "The page icon of GitHub settings."),
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
    ("↑ ↓", "BC250 Suite Releases", "Earlier commands, in the command line's placeholder."),
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
    apps = tomllib.loads((root / "portal" / "apps.toml").read_text(encoding="utf-8"))
    names = {k: v["name"] for section in ("apps", "checkout") for k, v in apps.get(section, {}).items()} | LAUNCHES
    by_category: dict[str, list[str]] = {}
    for key, entry in tomllib.loads((root / "icons" / "categories.toml").read_text(encoding="utf-8")).items():
        by_category.setdefault(entry["category"], []).append(key)

    out = ["# Icons", "",
           "The icons of the project, per suite, and where each is used. Pictures are shown from their own files; "
           "icons drawn\nin code are rendered to `docs/design/icons/`. Written by `tools/make_icons.py`: change the "
           "listing there and\nrun it.", "",
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
        (img(f"icons/{category}/{category}-128.png", 64), category.title(),
         "<br>".join(f"{names.get(k, k)} (`{k}`)" for k in keys)) for category, keys in sorted(by_category.items())))
    out += ["### The portal's symbols", "",
            "Drawn with QPainter in `portal/bc250_portal/glyphs.py`, in the theme's text colour (shown here on "
            "Gunmetal) or red.", ""]
    out += table("Icon,Name,Used for", ((img(rendered(name)), title, use) for name, *_, title, use in GLYPHS))
    out += ["### Icons in the apps", ""]
    out += table("Icon,File,Used for", ((img(path, 16), file, use) for path, file, use in APP_ICONS))
    out += ["### The desktop style's icons", "",
            "Icons the apps take from the desktop's style or icon theme, so they look different on every desktop; "
            "shown here as\nQt's Fusion style draws them.", ""]
    out += table("Icon,Name,Used for", ((img(rendered(name)), shown, use) for name, _, _, shown, use in STANDARD))
    out += ["### Material Design icons in the wiki", "", "Drawn by MkDocs Material in the wiki's colours.", ""]
    out += table("Icon,Name,Used for", ((img(f"{MDI}/{name}.svg", 24), f"`material-{name}`", use)
                                        for name, use in MATERIAL))
    out += ["### Symbols in text", "", "Characters of the font, used as icons in labels and buttons.", ""]
    out += table("Symbol,App,Used for", SYMBOLS)
    return "\n".join(out).rstrip("\n") + "\n"


def render(root: Path = ROOT) -> list[Path]:
    """The drawn icons as PNGs in docs/design/icons/, each 48 px on a rounded square of Gunmetal's window colour."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path[:0] = [str(root / "portal"), str(root / "core")]
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
