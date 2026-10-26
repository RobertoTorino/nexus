# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared app fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP = Path(__file__).resolve().parents[1]
SUITE = APP.parents[2]                 # the repository: core/ is there
sys.path.insert(0, str(APP))
sys.path.insert(0, str(SUITE / "core"))


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
