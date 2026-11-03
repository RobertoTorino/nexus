# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/portal_screenshot.py: the portal's picture, from a run of the tool; it needs the portal's PyQt6."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
pytest.importorskip("PyQt6.QtWidgets", reason="the portal's PyQt6 is not installed here")


def test_the_picture_is_written_and_the_tool_exits_cleanly(tmp_path):
    """The tool deletes the window and the application itself, in order, once the picture is saved (03-11-2026: left
    to the interpreter's exit, the process crashed now and then on the wiki's runner after the picture was written)."""
    out = tmp_path / "portal.webp"
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run([sys.executable, str(TOOLS / "portal_screenshot.py"), "--out", str(out)],
                            capture_output=True, text=True, env=env, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().endswith("1920 x 1200")
    assert out.read_bytes()[:4] == b"RIFF" and out.read_bytes()[8:12] == b"WEBP"
