# SPDX-License-Identifier: GPL-3.0-or-later
"""bc250_core from the checkout, as run.sh puts it on the path, and the app's package."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP = Path(__file__).resolve().parents[1]
CORE = APP.parents[1] / "core"
for path in (CORE, APP):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture(scope="session")
def qapp():
    """The application with Nexus's theme, as create_app() sets it for this app."""
    from bc250_core import widgets
    from bc250_core.nexus import NEXUS
    from PyQt6.QtWidgets import QApplication
    widgets.set_theme(NEXUS)
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def settings_in_a_temp_folder(tmp_path):
    """The .ini settings in a temp folder: no test reads the user's own."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "config"))


CHECKOUT = APP.parents[1]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def bazzite_checkout(tmp_path) -> Path:
    """A checkout with this one's Nexus apps (dev/), tools and Nexus page, and a small Bazzite suite, bz/ ("Bz Suite":
    a portal, two apps with category icons, a wiki and its tours' scripts). Nexus holds no suite of its own since the
    BC250 Bazzite Suite moved to a repository of its own (14-11-2026); the dashboard's work on one is tested here."""
    import shutil
    from PIL import Image
    root = tmp_path / "checkout"
    ignore = shutil.ignore_patterns("tests", "__pycache__", ".pytest_cache", "site", ".cache")
    shutil.copytree(CHECKOUT / "dev", root / "dev", ignore=ignore)
    shutil.copytree(CHECKOUT / "tools", root / "tools", ignore=ignore)
    shutil.copytree(CHECKOUT / "nexus", root / "nexus", ignore=ignore)
    suite = root / "bz"
    _write(suite / "SYSTEM", "bazzite\n")
    _write(suite / "mkdocs.yml", "site_name: Bz Suite\nsite_url: https://example.invalid/bz/\n")
    _write(suite / "docs" / "index.md", "# Bz\n")
    _write(suite / "portal" / "VERSION", "1.0.0\n")
    _write(suite / "portal" / "bz_portal" / "__init__.py", 'APP_NAME = "Bz Suite"\nAPP_ID = "bz-portal"\n')
    _write(suite / "portal" / "bz_portal" / "__main__.py", "")
    apps = {"rpcs3": "gaming", "sftp": "utilities"}
    _write(suite / "portal" / "apps.toml", "".join(
        f'[apps.{key}]\nname = "Bz {key}"\nsummary = "s"\ntag = "{key}-v0.1.0"\nsha256 = ""\nrequired = false\n'
        f'changes_board = false\ncategory = "{category}"\ninstall = ["i"]\nuninstall = ["u"]\ndetect = ["d"]\n\n'
        for key, category in apps.items()))
    _write(suite / "icons" / "categories.toml", "".join(
        f'[{key}]\ncategory = "{category}"\nicons = ["apps/{key}/images/bz-{key}"]\n'
        f'tile = "portal/images/apps/{key}.webp"\n\n' for key, category in apps.items()))
    for key, category in apps.items():
        _write(suite / "apps" / key / "VERSION", "0.1.0\n")
        _write(suite / "apps" / key / f"bz_{key}" / "__init__.py", f'APP_NAME = "Bz {key}"\nAPP_ID = "bz-{key}"\n')
        _write(suite / "apps" / key / f"bz_{key}" / "__main__.py", "")
        for size in (1024, 512, 256, 128):
            path = suite / "icons" / category / f"{category}-{size}.{'png' if size == 128 else 'webp'}"
            if not path.is_file():
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGBA", (size, size), "green").save(path)
    for script in ("record-tour.sh", "record-app-tour.sh"):
        _write(suite / "tools" / script, "#!/usr/bin/env bash\n")
    return root
