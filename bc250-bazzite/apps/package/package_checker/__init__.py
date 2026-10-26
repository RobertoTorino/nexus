# SPDX-License-Identifier: GPL-3.0-or-later
"""Check suite Python packages and external tools."""

APP_NAME = "Dependency Checker"
APP_ID = "bc250-portal-dependency-checker"
__version__ = "2.0.0"

from pathlib import Path

from bc250_core import AppInfo

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
CATALOG = PACKAGE / "dependencies.toml"
LOGO_PATH = ROOT / "images" / "bc250-dependency-checker.webp"
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH,
               tag_prefix="package-v", settings_app=APP_ID, settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "CATALOG", "INFO", "LOGO_PATH", "ROOT", "__version__"]
