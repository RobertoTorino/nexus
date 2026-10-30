# SPDX-License-Identifier: GPL-3.0-or-later
"""publish_release.sh with gh stood in for: a new release (the tag made on the commit), a draft (made anew when one is
there), and a release that is out already (new assets, or left alone for a draft run)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "publish_release.sh"
BASH = shutil.which("bash")
TAG = "wp-portal-v4.1.0"
GH = """#!/usr/bin/env bash
echo "$*" >> "$CALLS"
if [ "$1 $2" = "release view" ]; then
    case "$STATE" in
        draft) echo true ;;
        published) echo false ;;
        *) echo "release not found" >&2; exit 1 ;;
    esac
fi
"""

pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")


def publish(tmp_path: Path, state: str, *extra: str) -> list[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(GH, encoding="utf-8", newline="\n")
    (bin_dir / "gh").chmod(0o755)
    dist = tmp_path / "dist"
    dist.mkdir()
    for name in (f"{TAG}.zip", "SHA256SUMS", "notes.md"):
        (dist / name).write_text("x", encoding="utf-8")
    (dist / "title.txt").write_text("Windows Portable Suite v4.1.0", encoding="utf-8")
    calls = tmp_path / "calls"
    env = {**os.environ, "STATE": state, "CALLS": str(calls),
           "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    script = SCRIPT.as_posix()
    result = subprocess.run([BASH, script, TAG, "abc123", dist.as_posix(), *extra], env=env, capture_output=True,
                            text=True, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    return calls.read_text(encoding="utf-8").splitlines()


def test_a_new_release_is_published_with_its_tag_on_the_commit(tmp_path):
    calls = publish(tmp_path, "none")
    create = calls[-1]
    assert create.startswith(f"release create {TAG} ") and "--target abc123" in create and "--latest=false" in create
    assert "--draft" not in create and "Windows Portable Suite v4.1.0" in create


def test_a_draft_run_makes_a_draft(tmp_path):
    create = publish(tmp_path, "none", "--draft")[-1]
    assert create.startswith(f"release create {TAG} ") and create.endswith("--draft")


def test_a_draft_there_already_is_made_anew(tmp_path):
    calls = publish(tmp_path, "draft", "--draft")
    assert calls[1] == f"release delete {TAG} --yes" and calls[2].startswith(f"release create {TAG} ")


def test_a_release_out_already_is_left_alone_by_a_draft_run(tmp_path):
    calls = publish(tmp_path, "published", "--draft")
    assert calls == [f"release view {TAG} --json isDraft --jq .isDraft"]


def test_a_tag_pushed_again_uploads_the_assets_again(tmp_path):
    calls = publish(tmp_path, "published")
    assert calls[-1].startswith(f"release upload {TAG} ") and calls[-1].endswith("--clobber")
