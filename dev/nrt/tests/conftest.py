# SPDX-License-Identifier: GPL-3.0-or-later
"""bc250_core from the checkout, as run.sh puts it on the path, and the app's package."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# No Claude Code for the windows the tests open: the Claude pill reads nothing of this machine.
os.environ["CLAUDE_CONFIG_DIR"] = str(Path(__file__).resolve().parent / "no-claude")
APP = Path(__file__).resolve().parents[1]
CORE = APP.parents[1] / "core"
for path in (CORE, APP):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture(scope="session", autouse=True)
def plain_suites_manifest_tools():
    """A suite without a tag prefix and without its own tools/check_manifest.py (the test repositories) is read by
    the BC250 Bazzite Suite's check_manifest.py as it was when the suite left Nexus (tests/fixtures/bc250-suite/):
    the parser and bump rules of a plain-tag suite, which Nexus no longer holds."""
    import importlib.util
    from nexus_release_tool import plan
    path = Path(__file__).resolve().parent / "fixtures" / "bc250-suite" / "tools" / "check_manifest.py"
    spec = importlib.util.spec_from_file_location("check_manifest", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    plan.check_manifest = module
    yield
    plan.check_manifest = None


@pytest.fixture(scope="session", autouse=True)
def nexus_theme():
    """The widgets draw with Nexus's theme, as create_app() sets it for this app (style.py)."""
    from bc250_core import widgets
    from nexus_release_tool.style import NEXUS
    widgets.set_theme(NEXUS)


@pytest.fixture(autouse=True)
def settings_in_a_temp_folder(tmp_path):
    """The .ini settings in a temp folder: no test reads or moves the user's own (those of the earlier name too)."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "config"))
