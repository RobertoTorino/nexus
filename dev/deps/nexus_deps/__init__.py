# SPDX-License-Identifier: GPL-3.0-or-later
"""Nexus Deps: a suite's Python packages and external tools on this machine, what is missing or outdated, and a
fix for it; and Bazzite's update state. A Nexus app (dev/), run from the checkout and never released (owner,
07-11-2026: it was the BC250 Bazzite Suite's Dependency Checker, apps/package, until then)."""

from pathlib import Path

from bc250_core import AppInfo

APP_NAME = "Nexus Deps"
APP_ID = "nexus-deps"
__version__ = "3.4.0"

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
CHECKOUT = ROOT.parents[1]                  # the repository (Nexus), dev/deps/ in it
CATALOGS = PACKAGE / "catalogs"             # one catalog per suite: <suite folder>.toml
DEFAULT_SUITE = "bc250-bazzite"             # the only suite with a catalog so far (owner, 07-11-2026)
CATALOG = CATALOGS / f"{DEFAULT_SUITE}.toml"
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/nexus-deps/nexus-deps.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, settings_ini=True)


def suites() -> list[str]:
    """The suites with a catalog: the names --suite takes."""
    return sorted(path.stem for path in CATALOGS.glob("*.toml"))


def catalog(suite: str = DEFAULT_SUITE) -> Path:
    """The catalog of *suite* (a folder of the checkout, such as bc250-bazzite)."""
    if suite not in suites():
        raise ValueError(f"no catalog for {suite!r}: {', '.join(suites())}")
    return CATALOGS / f"{suite}.toml"


__all__ = ["APP_ID", "APP_NAME", "CATALOG", "CATALOGS", "CHECKOUT", "DEFAULT_SUITE", "INFO", "LOGO_PATH", "ROOT",
           "__version__", "catalog", "suites"]
