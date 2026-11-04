# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/check-release.sh draft finds Homebrew's gh when the PATH lacks it, as in the terminal Nexus Release Tool opens
(a login shell, which does not read .bashrc where brew shellenv adds it)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check-release.sh"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="check-release.sh is bash")


def test_draft_uses_homebrews_gh(tmp_path):
    brew = tmp_path / "brew"
    (brew / "bin").mkdir(parents=True)
    gh = brew / "bin" / "gh"
    gh.write_text('#!/bin/sh\necho "gh $*"\nexit 3\n', encoding="utf-8")   # stops the script before it installs
    gh.chmod(0o755)
    tools = tmp_path / "tools"                      # what the script needs before gh, without a gh beside them
    tools.mkdir()
    for name in ("bash", "tr", "rm", "mkdir", "id", "dirname"):
        os.symlink(shutil.which(name), tools / name)
    env = {"PATH": str(tools), "HOME": str(tmp_path), "XDG_CACHE_HOME": str(tmp_path / "cache"),
           "HOMEBREW_PREFIX": str(brew)}
    out = subprocess.run([str(tools / "bash"), str(SCRIPT), "draft", "portal-v1.2.3"], env=env,
                         capture_output=True, text=True)
    assert "gh release download portal-v1.2.3" in out.stdout, out.stderr
    assert "command not found" not in out.stderr and "gh ended with 3" in out.stderr and out.returncode == 1
