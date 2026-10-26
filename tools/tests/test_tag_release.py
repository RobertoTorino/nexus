# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/tag-release.sh: it tags only a pushed HEAD that holds the version and passed CI, never a commit from before
the bump or one CI failed. GitHub's answer comes from BC250_CI_STATE here (tools/ci_state.py)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "tag-release.sh"
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
           BC250_CI_STATE="passed")

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None, reason="needs bash, git")


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True, env=ENV).stdout


@pytest.fixture
def repo(tmp_path) -> Path:
    origin, root = tmp_path / "origin.git", tmp_path / "suite"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    (root / "tools").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "tools" / "tag-release.sh")
    shutil.copy(SCRIPT.with_name("ci_state.py"), root / "tools" / "ci_state.py")
    shutil.copy(SCRIPT.with_name("suites.py"), root / "tools" / "suites.py")
    for folder, version in (("portal", "0.9.4"), ("apps/governor", "0.1.0")):
        (root / folder).mkdir(parents=True)
        (root / folder / "VERSION").write_text(version + "\n")
    (root / "portal" / "apps.toml").write_text("")                  # laid out as a suite itself (tools/suites.py)
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", str(origin))
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start")
    git(root, "push", "-q", "origin", "main")
    return root


def tag(root: Path, *tags: str, ci: str = "passed") -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(root / "tools" / "tag-release.sh"), *tags], cwd=root, capture_output=True,
                          text=True, env=dict(ENV, BC250_CI_STATE=ci))


def remote_tags(root: Path) -> str:
    return git(root, "ls-remote", "--tags", "origin")


def test_refuses_a_bump_that_is_not_committed(repo):
    (repo / "portal" / "VERSION").write_text("0.9.5\n")             # Bump portal wrote it; no commit yet
    result = tag(repo, "portal-v0.9.5")
    assert result.returncode != 0 and "not committed yet" in result.stderr
    assert git(repo, "tag") == "" and remote_tags(repo) == ""


def test_refuses_an_unpushed_bump_then_tags_the_pushed_one(repo):
    (repo / "portal" / "VERSION").write_text("0.9.5\n")
    git(repo, "commit", "-qam", "Release portal-v0.9.5")
    result = tag(repo, "portal-v0.9.5")
    assert result.returncode != 0 and "git push first" in result.stderr
    git(repo, "push", "-q", "origin", "main")
    result = tag(repo, "portal-v0.9.5")
    assert result.returncode == 0, result.stderr
    head = git(repo, "rev-parse", "HEAD").strip()
    assert f"{head}\trefs/tags/portal-v0.9.5" in remote_tags(repo)    # on the commit with the bump
    again = tag(repo, "portal-v0.9.5")
    assert again.returncode != 0 and "exists already" in again.stderr


def test_checks_every_tag_before_tagging_any(repo):
    (repo / "apps/governor/VERSION").write_text("0.1.1\n")
    git(repo, "commit", "-qam", "Release governor-v0.1.1")
    git(repo, "push", "-q", "origin", "main")
    result = tag(repo, "governor-v0.1.1", "portal-v0.9.5")           # the portal is not bumped
    assert result.returncode != 0 and "HEAD has portal/VERSION 0.9.4, not 0.9.5" in result.stderr
    assert git(repo, "tag") == ""
    (repo / "apps/governor/notes").write_text("x")
    git(repo, "add", "-A")
    dirty = tag(repo, "governor-v0.1.1")
    assert dirty.returncode != 0 and "not committed" in dirty.stderr
    assert tag(repo, "governor-0.1.1").returncode != 0               # not <name>-v<x.y.z>


def test_tags_only_a_commit_ci_passed(repo):
    (repo / "portal" / "VERSION").write_text("0.9.5\n")
    git(repo, "commit", "-qam", "Release portal-v0.9.5")
    git(repo, "push", "-q", "origin", "main")
    failed = tag(repo, "portal-v0.9.5", ci="failed")
    assert failed.returncode != 0 and "CI has not passed on HEAD" in failed.stderr
    assert git(repo, "tag") == "" and remote_tags(repo) == ""
    assert tag(repo, "portal-v0.9.5", ci="running").returncode != 0          # still running after the wait: no tag
    assert git(repo, "tag") == ""
    assert tag(repo, "portal-v0.9.5", ci="passed").returncode == 0
    assert "refs/tags/portal-v0.9.5" in remote_tags(repo)


def test_a_portal_tag_waits_for_the_app_releases_it_pins(repo):
    """The portal release that failed: tagged with an app release that was not tagged yet, pinned without sha256."""
    manifest = repo / "portal" / "apps.toml"
    manifest.write_text('[apps.governor]\nname = "Governor"\ntag = "governor-v0.1.0"\nsha256 = ""\n')
    (repo / "portal" / "VERSION").write_text("0.9.5\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "Release portal-v0.9.5")
    git(repo, "push", "-q", "origin", "main")
    untagged = tag(repo, "portal-v0.9.5")
    assert untagged.returncode != 0 and "pins governor-v0.1.0, which is not tagged yet" in untagged.stderr
    assert tag(repo, "governor-v0.1.0").returncode == 0
    unpinned = tag(repo, "portal-v0.9.5")
    assert unpinned.returncode != 0 and "without its sha256" in unpinned.stderr
    manifest.write_text(manifest.read_text().replace('sha256 = ""', f'sha256 = "{"a" * 64}"'))
    (repo / "portal" / "VERSION").write_text("0.9.6\n")
    git(repo, "commit", "-qam", "Release portal-v0.9.6")
    git(repo, "push", "-q", "origin", "main")
    assert tag(repo, "portal-v0.9.6").returncode == 0
    assert "refs/tags/portal-v0.9.6" in remote_tags(repo) and "portal-v0.9.5" not in remote_tags(repo)
