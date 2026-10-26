# SPDX-License-Identifier: GPL-3.0-or-later
"""Local GUI for the suite's installer tests."""

from pathlib import Path

APP_NAME = "BC-250 Installer Tests"
APP_ID = "bc250-installer-test-gui"
APP_DIR = Path(__file__).resolve().parent.parent
IMAGES_DIR = APP_DIR / "images"
APP_ICON_PATH = IMAGES_DIR / "bc250-installer-test-gui.webp"
DOC_ICON_PATH = IMAGES_DIR / "bc250-installer-test-gui-128.png"
SUITE_ROOT = APP_DIR.parents[2]
TESTS_DIR = SUITE_ROOT / "tools" / "installer-tests"
__version__ = (APP_DIR / "VERSION").read_text(encoding="utf-8").strip()
