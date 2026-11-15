#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write ICONS.md: every icon of Nexus, and where it is used, and the Nexus apps' icon copies:

    python3 tools/make_icons.py            # write ICONS.md and the icon copies
    python3 tools/make_icons.py --check    # only say whether ICONS.md is up to date; exit 1 when it is not

The Windows Portable Suite has a repository of its own (owner, 13-11-2026), cloned into this checkout as
windows-portable/: its icons are listed in its own windows-portable/ICONS.md, written and checked here while the
suite is in the checkout, and its icon copies are written then too. Without it, only Nexus's ICONS.md.

The BC250 Bazzite Suite has a repository of its own with its own copy of this tool and its ICONS.md (14-11-2026).
Pictures are shown from their own files. The listing is the data below: change it here and run the script, not
ICONS.md itself."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MDI = "https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg"      # Material Design Icons, as MkDocs Material bundles them
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
    ("dev/nrt/images/nexus-release-tool.webp", "`dev/<name>/images/<app id>.webp` (512 px), `-128.png`",
     "The Nexus apps (owner, 26-10-2026: a Nexus app takes Nexus's icon, not a category's): Nexus Dashboard "
     "(`dev/dash`), Nexus Release Tool (`dev/nrt`), Nexus Demo Recorder (`dev/demo`), Nexus Installer Tests "
     "(`dev/itests`), Nexus Sound Lab (`dev/sounds`) and Nexus Deps (`dev/deps`), each its window header and window icon, its menu entry and Desktop icon. Lossless copies of "
     "the drawing, written by this tool."),
]
# the Nexus apps' icons (dev/<name>/images/<app id>): the drawing at each size, lossless (the pixels stay the
# drawing's), by this tool.
NEXUS_APPS = {"dash": "nexus-dashboard", "nrt": "nexus-release-tool", "demo": "nexus-demo-recorder",
              "itests": "nexus-installer-tests", "sounds": "nexus-sound-lab", "deps": "nexus-deps"}
NEXUS_COPIES = [
    *((f"nexus/images/nexus-{size}.png", f"dev/{folder}/images/{app_id}{'-128' if size == 128 else ''}.{kind}")
      for folder, app_id in NEXUS_APPS.items() for size, kind in ((512, "webp"), (128, "png"))),
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


def windows_portable_here(root: Path = ROOT) -> bool:
    """Whether the Windows Portable Suite, a repository of its own, is in this checkout as its folder."""
    return (root / WINDOWS_PORTABLE / "portal" / "apps.toml").is_file()

WINDOWS_PORTABLE_CATEGORIES = {
    "gaming": "the owner's pictures of the handheld (29-10-2026), wide (2:1: 1024 x 512 down to 128 x 64): the tile and "
              "the wiki show them as they are, the window, program and Start-menu icons centered on a transparent "
              "square",
    "utilities": "the owner's picture of a circuit board (01-11-2026), square (1024 x 1024 down to 128 x 128)",
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
    """Writes the Nexus apps' icon copies and the Nexus page's favicon from the Nexus drawings (NEXUS_COPIES) and
    Windows Portable Test's and the Windows portal's from the suite's (WINDOWS_PORTABLE_COPIES), lossless, so a
    copy's pixels are the drawing's (tests compare them); and the Nexus page's logo and hero (NEXUS_PAGE_COPIES),
    lossy; and every Windows Portable Suite app's category icon (windows_portable_icons()). The paths written."""
    if not windows_portable_here(root):
        return write_copies(root, NEXUS_COPIES, [pair for pair in NEXUS_PAGE_COPIES
                                                 if not pair[1].startswith(f"{WINDOWS_PORTABLE}/")])
    return (write_copies(root, NEXUS_COPIES + WINDOWS_PORTABLE_COPIES, NEXUS_PAGE_COPIES)
            + windows_portable_icons(root))


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
    ("toolbox", "Home: the card \"Utilities\"."),
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
    ("✓ ✗", "Nexus Deps", "CVE: none found, found."),
    ("↑ ↓", "Nexus Release Tool", "Earlier commands, in the command line's placeholder."),
    ("●", "Every app on core", "The dot of a status box (`bc250_core/widgets.py`)."),
    ("✓ ✗", "Nexus Installer Tests", "A test passed, failed."),
]


def img(path: str, width: int = 48) -> str:
    return f'<img src="{path}" width="{width}" alt="">'


def table(header: str, rows) -> list[str]:
    return [f"| {' | '.join(header.split(','))} |", "| --- | --- | --- |",
            *(f"| {' | '.join(row)} |" for row in rows), ""]



def build(root: Path = ROOT) -> str:
    """ICONS.md's text, from the data above."""
    out = ["# Icons", "",
           "The icons of Nexus, and where each is used. Written by `tools/make_icons.py`: change the listing there and "
           "run it.\nEach suite lists its own icons in its own repository's `ICONS.md`.", "",
           "## Nexus", "", "### The Nexus icon", ""]
    out += table("Icon,File,Used for", ((img(path), file, use) for path, file, use in NEXUS_ICON))
    out += ["### Material Design icons on the Nexus page", "", "Drawn by MkDocs Material in the page's colors.", ""]
    out += table("Icon,Name,Used for", ((img(f"{MDI}/{name}.svg", 24), f"`material-{name}`", use)
                                        for name, use in NEXUS_MATERIAL))
    out += ["### Symbols in text", "", "Characters of the font, used as icons in the Nexus apps' labels and buttons.", ""]
    out += table("Symbol,App,Used for", SYMBOLS)
    return "\n".join(out).rstrip("\n") + "\n"


def build_windows_portable(root: Path = ROOT) -> str:
    """The Windows Portable Suite's own ICONS.md (windows-portable/ICONS.md), its paths from the suite's folder."""
    out = ["# Icons", "",
           "The icons of the Windows Portable Suite, and where each is used. Written by the Nexus tools' "
           "`make_icons.py`\n(`../tools/` in the Nexus checkout the suite is in): change the listing there and run "
           "it. The paths are relative to\nthis repository's root.", "",
           "## The suite's icon", ""]
    out += table("Icon,File,Used for", ((img(path), file, use) for path, file, use in WINDOWS_PORTABLE_ICON))
    by_category: dict[str, list[str]] = {}
    for key, name, category, _ in windows_portable_apps(root):
        by_category.setdefault(category, []).append(f"{name} (`{key}`)")
    out += ["## The category icons", "",
            "Every app but Windows Portable Test has the icon of its category: `windows-portable/icons/<category>/` "
            "at 1024, 512,\n256 and 128 px (PNG), copied by this tool from the portal's `apps.toml` to the app's "
            "`images/<app id>.webp` (512 px)\nand `-128.png`, its tile `portal/images/apps/<key>.webp` (256 px) and its "
            "chapter's icon `docs/images/apps/<key>.webp`\n(256 px). A new picture for a category is converted by "
            "`tools/sync_icons.py --suite windows-portable` (the\ndashboard's Convert icons), as "
            "`windows-portable/icons/categories.toml` says: PNG, the Gaming pictures 2:1.", ""]
    out += table("Icon,Category,Apps", (
        (img(f"{WINDOWS_PORTABLE}/icons/{category}/{category}-128.png", 64),
         f"{category.title()}: {source}", "<br>".join(by_category.get(category, [])))
        for category, source in sorted(WINDOWS_PORTABLE_CATEGORIES.items())))
    out += ["## Material Design icons in the wiki", "", "Drawn by MkDocs Material in the wiki's colors.", ""]
    out += table("Icon,Name,Used for", ((img(f"{MDI}/{name}.svg", 24), f"`material-{name}`", use)
                                        for name, use in WINDOWS_PORTABLE_MATERIAL))
    return "\n".join(out).rstrip("\n").replace(f"{WINDOWS_PORTABLE}/", "") + "\n"



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only say whether ICONS.md is up to date")
    args = parser.parse_args(argv)
    if not args.check:
        nexus_copies()
    files = [("ICONS.md", build())]
    if windows_portable_here():             # the suite's own listing, in its repository
        files.append((f"{WINDOWS_PORTABLE}/ICONS.md", build_windows_portable()))
    if args.check:
        stale = [name for name, text in files
                 if not (ROOT / name).is_file() or (ROOT / name).read_text(encoding="utf-8") != text]
        for name in stale:
            print(f"{name} is out of date: run python3 tools/make_icons.py")
        if not stale:
            print(f"{' and '.join(name for name, _ in files)} {'are' if len(files) > 1 else 'is'} up to date")
        return 1 if stale else 0
    for name, text in files:
        (ROOT / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {' and '.join(name for name, _ in files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
