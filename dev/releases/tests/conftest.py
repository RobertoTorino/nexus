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
def nexus_theme():
    """The widgets draw with Nexus's theme, as create_app() sets it for this app (style.py)."""
    from bc250_core import widgets
    from nexus_releases.style import NEXUS
    widgets.set_theme(NEXUS)
