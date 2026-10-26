# SPDX-License-Identifier: GPL-3.0-or-later
"""The BC250 Bazzite Suite portal: installs, opens and removes the suite's apps, one pill per app."""

APP_NAME = "BC250 Bazzite Suite"
APP_ID = "bc250-bazzite-suite"
__version__ = "9.1.0"
# The suite's stage, shown beside the version in the header and in a portal release's notes; "" when it leaves
# active development. The README's badge and the wiki's home page say the same (tools/tests/test_stage.py).
STAGE = "Beta"
STAGE_NOTE = "The suite is in active development: features and layout may still change between releases."

import re
from pathlib import Path

from bc250_core import AppInfo
from bc250_core.platform import data_home

ROOT = Path(__file__).resolve().parent.parent           # portal/ in the checkout, /opt/bc250-bazzite-suite installed
CHECKOUT_FILE = "suite-checkout"                        # in ROOT, written by install.sh when installed from a checkout
MANIFEST = ROOT / "apps.toml"
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"
INTRO_LOGO = ROOT / "images" / f"{APP_ID}-1024.webp"      # the same picture at 1024 px, for the intro of Big Picture Mode
APP_ICONS = ROOT / "images" / "apps"                    # <key>.webp: the small icon on each app's card
CATEGORY_ICONS = ROOT / "images" / "categories"         # <category>.webp: the 512 px icon, for Suite Big Picture Mode
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="portal-v",
               settings_app="bc250-bazzite-suite-portal")


def installed_copy() -> Path | None:
    """The link install.sh points at the installed portal (/opt/bc250-bazzite-suite), when this portal runs from an
    installed copy (/opt/bc250-bazzite-suite-v<version>); None from a checkout. A portal installed while this one
    runs shows up there."""
    return ROOT.parent / APP_ID if ROOT.name.startswith(f"{APP_ID}-v") else None


def state_dir() -> Path:
    """Per-user portal state: which tag of each app it installed, and the extracted releases it installed from
    (kept, so the matching uninstaller is at hand)."""
    return data_home() / APP_ID / "portal"


def is_suite(folder: Path) -> bool:
    """Whether *folder* is a BC250 Bazzite Suite repository (a checkout)."""
    return (folder / "apps").is_dir() and (folder / "tools" / "stage_app.py").is_file() and (folder / "core").is_dir()


def remembered_checkout() -> Path | None:
    """The suite checkout a portal installed from a release was shown, for the apps that run from a checkout
    ([checkout.<key>] in apps.toml); None when it was not shown one, or the folder is no longer a checkout."""
    try:
        recorded = (state_dir() / CHECKOUT_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return Path(recorded) if recorded and is_suite(Path(recorded)) else None


SEARCH_DEPTH = 3                        # ~/IdeaProjects/bc250-bazzite-suite is depth 2


def find_checkout(home: Path | None = None) -> Path | None:
    """A suite checkout on this machine, without asking: the one a checkout-only app's launcher in ~/.local/bin
    runs from, else the first one in the home folder, up to SEARCH_DEPTH folders deep (hidden folders skipped)."""
    home = home or Path.home()
    for launcher in sorted((home / ".local" / "bin").glob("bc250-*")):
        try:
            text = launcher.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for quoted in re.findall(r'"(/[^"$]+)"', text):
            for folder in Path(quoted).parents:
                if is_suite(folder):
                    return folder
    level = [home]
    for _depth in range(SEARCH_DEPTH):
        below = []
        for folder in level:
            try:
                children = sorted(c for c in folder.iterdir() if c.is_dir() and not c.name.startswith("."))
            except OSError:
                continue
            for child in children:
                if is_suite(child):
                    return child
            below += children
        level = below
    return None


def remember_checkout(folder: Path) -> None:
    state_dir().mkdir(parents=True, exist_ok=True)
    (state_dir() / CHECKOUT_FILE).write_text(f"{folder}\n", encoding="utf-8")


def suite_checkout() -> Path | None:
    """The suite repository when the portal runs from a checkout, or was installed from one (development): apps
    then install from the local source instead of a GitHub release."""
    candidates = [ROOT.parent]
    try:
        recorded = (ROOT / CHECKOUT_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        recorded = ""
    if recorded:
        candidates.append(Path(recorded))
    return next((suite for suite in candidates if is_suite(suite)), None)
