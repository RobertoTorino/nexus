# SPDX-License-Identifier: GPL-3.0-or-later
"""Every script whose usage() prints its own header comment prints the comment, not the SPDX line above it (the
Help of GPU OC Bisect showed only "SPDX-License-Identifier" to the owner, 26-10-2026)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SUITE = Path(__file__).resolve().parents[2]
SCRIPTS = sorted(path for path in (SUITE / "apps").glob("*/*.sh")
                 if "usage() { sed -n '4,/^$/" in path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_help_is_the_header_comment(script: Path):
    assert SCRIPTS, "no script prints its header comment as help"
    result = subprocess.run(["bash", str(script), "--help"], capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines and lines[0].startswith(f"{script.name} - "), result.stdout[:200]
    assert "Usage:" in result.stdout and "SPDX" not in result.stdout
