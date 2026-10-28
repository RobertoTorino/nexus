# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/pre-push.sh, git's pre-push hook through tools/hooks/pre-push: CI's quick checks before a push, against what
the remote has. check_versions.py, check_manifest.py and check_changelogs.py are stubs here that record how they were called."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
ZERO = "0" * 40
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
ENV.pop("BC250_PRE_PUSH", None)

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None, reason="needs bash, git")

STUB = """import os, sys
from pathlib import Path
with open(Path(__file__).parent.parent / "calls.txt", "a") as f:
    f.write(Path(__file__).name + " " + " ".join(sys.argv[1:]) + "\\n")
sys.exit(int(os.environ.get("FAIL_" + Path(__file__).stem.upper(), "0")))
"""


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True, env=ENV).stdout.strip()


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "suite"
    (root / "tools" / "hooks").mkdir(parents=True)
    for name in ("pre-push.sh", "hooks/pre-push", "suites.py"):
        shutil.copy(TOOLS / name, root / "tools" / name)
        (root / "tools" / name).chmod(0o755)
    (root / "portal").mkdir()
    (root / "portal" / "apps.toml").write_text("")                  # laid out as a suite itself (tools/suites.py)
    for name in ("check_versions.py", "check_manifest.py", "check_changelogs.py"):
        (root / "tools" / name).write_text(STUB)
    (root / ".gitignore").write_text("calls.txt\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "update-index", "--chmod=+x", "tools/pre-push.sh", "tools/hooks/pre-push")
    git(root, "commit", "-qm", "first")
    return root


def hook(root: Path, lines: list[str], **env: str) -> subprocess.CompletedProcess:
    """The hook as git runs it: the remote's name and url as arguments, the refs on stdin."""
    return subprocess.run(["bash", "tools/hooks/pre-push", "origin", "url"], cwd=root, input="\n".join(lines) + "\n",
                          capture_output=True, text=True, env=dict(ENV, **env))


def calls(root: Path) -> list[str]:
    path = root / "calls.txt"
    return path.read_text().splitlines() if path.exists() else []


def test_checks_against_what_the_remote_has(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "x.txt").write_text("x\n")
    git(repo, "add", "x.txt")
    git(repo, "commit", "-qm", "second")
    head = git(repo, "rev-parse", "HEAD")
    result = hook(repo, [f"refs/heads/main {head} refs/heads/main {base}"])
    assert result.returncode == 0, result.stderr
    assert calls(repo) == ["check_versions.py ", f"check_manifest.py --base {base}",
                           f"check_changelogs.py --base {base}"]


def test_a_portal_bump_missing_stops_the_push(repo):
    """The release push CI failed on: apps.toml changed without the portal bump."""
    head = git(repo, "rev-parse", "HEAD")
    result = hook(repo, [f"refs/heads/main {head} refs/heads/main {head}"], FAIL_CHECK_MANIFEST="1")
    assert result.returncode == 1
    assert "Bump portal" in result.stderr and "not pushed" in result.stderr and "--no-verify" in result.stderr


def test_a_changelog_that_lost_entries_stops_the_push(repo):
    head = git(repo, "rev-parse", "HEAD")
    result = hook(repo, [f"refs/heads/main {head} refs/heads/main {head}"], FAIL_CHECK_CHANGELOGS="1")
    assert result.returncode == 1
    assert "CHANGELOG lost entries" in result.stderr and "not pushed" in result.stderr


def test_a_remote_ahead_says_pull_first(repo):
    """Pushed from the other machine meanwhile (owner, 28-10-2026: the hook blamed a CHANGELOG): the remote's commit
    is not here, or here but not under HEAD. The hook says to pull, and runs no check against it."""
    first = git(repo, "rev-parse", "HEAD")
    (repo / "x.txt").write_text("x\n")
    git(repo, "add", "x.txt")
    git(repo, "commit", "-qm", "theirs")
    theirs = git(repo, "rev-parse", "HEAD")
    git(repo, "reset", "-q", "--hard", first)
    (repo / "y.txt").write_text("y\n")
    git(repo, "add", "y.txt")
    git(repo, "commit", "-qm", "mine")
    head = git(repo, "rev-parse", "HEAD")
    for remote in (theirs, "1" * 40):                                         # fetched, or not fetched at all
        result = hook(repo, [f"refs/heads/main {head} refs/heads/main {remote}"])
        assert result.returncode == 1 and "git pull --rebase" in result.stderr
        assert "CHANGELOG" not in result.stderr and calls(repo) == []


def test_a_suite_is_checked_only_when_the_push_changes_it(repo):
    """Two suites in their folders: a push that changes one runs that suite's checks only, so the other's, failing,
    holds nothing (owner, 28-10-2026: a Windows check never holds a Bazzite push); core alone: --nexus."""
    (repo / "portal" / "apps.toml").unlink()                         # the root is no suite here
    for suite in ("bc", "wp"):
        (repo / suite / "portal").mkdir(parents=True)
        (repo / suite / "portal" / "apps.toml").write_text("")
        (repo / suite / "tools").mkdir()
        (repo / suite / "tools" / "check_manifest.py").write_text(STUB.replace(
            "Path(__file__).parent.parent", "Path(__file__).parent.parent.parent").replace(
            "Path(__file__).name", f'"{suite}/" + Path(__file__).name').replace(
            '"FAIL_" + Path(__file__).stem.upper()', f'"FAIL_{suite.upper()}"'))
    (repo / "wp" / "TAG_PREFIX").write_text("wp-\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "two suites")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "bc" / "x.txt").write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "bc only")
    head = git(repo, "rev-parse", "HEAD")
    result = hook(repo, [f"refs/heads/main {head} refs/heads/main {base}"], FAIL_WP="1")
    assert result.returncode == 0, result.stderr                     # wp's failing check is not run
    assert calls(repo)[:2] == ["check_versions.py --suite bc", f"bc/check_manifest.py --base {base}"]
    assert not any(c.startswith("wp/") for c in calls(repo))
    (repo / "calls.txt").unlink()
    (repo / "core.txt").write_text("c\n")                             # shared parts only
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "shared")
    result = hook(repo, [f"refs/heads/main {git(repo, 'rev-parse', 'HEAD')} refs/heads/main {head}"], FAIL_WP="1")
    assert result.returncode == 0 and calls(repo)[0] == "check_versions.py --nexus"
    assert not any("check_manifest" in c for c in calls(repo))
    (repo / "calls.txt").unlink()
    (repo / "portal").mkdir(exist_ok=True)                            # the root's copy of the plain suite's apps.toml
    (repo / "portal" / "apps.toml").write_text("# copy\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "copy")
    result = hook(repo, [f"refs/heads/main {git(repo, 'rev-parse', 'HEAD')} refs/heads/main {base}"], FAIL_WP="1")
    assert "bc/check_manifest.py" in " ".join(calls(repo)) and "wp/check_manifest.py" not in " ".join(calls(repo))


def test_a_version_mismatch_stops_the_push(repo):
    head = git(repo, "rev-parse", "HEAD")
    result = hook(repo, [f"refs/heads/main {head} refs/heads/main {head}"], FAIL_CHECK_VERSIONS="1")
    assert result.returncode == 1 and "check_versions.py" in result.stderr


def test_a_new_branch_has_no_base_and_tags_are_left_alone(repo):
    head = git(repo, "rev-parse", "HEAD")
    assert hook(repo, [f"refs/heads/topic {head} refs/heads/topic {ZERO}"]).returncode == 0
    assert calls(repo) == ["check_versions.py "]                 # CI has no base for a new branch either
    (repo / "calls.txt").unlink()
    assert hook(repo, [f"refs/tags/alpha-v0.1.0 {head} refs/tags/alpha-v0.1.0 {ZERO}"]).returncode == 0
    assert calls(repo) == []                                      # tag-release.sh checks the tags


def test_a_script_without_its_exec_bit_stops_the_push(repo):
    (repo / "run.sh").write_text("#!/bin/sh\n")
    git(repo, "add", "run.sh")
    git(repo, "update-index", "--chmod=-x", "run.sh")
    git(repo, "commit", "-qm", "script")
    head = git(repo, "rev-parse", "HEAD")
    result = hook(repo, [f"refs/heads/main {head} refs/heads/main {ZERO}"])
    assert result.returncode == 1 and "run.sh" in result.stderr and "fix-modes.sh" in result.stderr


def test_crlf_stops_the_push(repo):
    (repo / "dos.txt").write_bytes(b"a\r\nb\r\n")
    subprocess.run(["git", "-c", "core.autocrlf=false", "add", "dos.txt"], cwd=repo, check=True, env=ENV)
    git(repo, "commit", "-qm", "crlf")
    head = git(repo, "rev-parse", "HEAD")
    result = hook(repo, [f"refs/heads/main {head} refs/heads/main {ZERO}"])
    assert result.returncode == 1 and "dos.txt" in result.stderr


def test_off_skips_every_check(repo):
    head = git(repo, "rev-parse", "HEAD")
    assert hook(repo, [f"refs/heads/main {head} refs/heads/main {head}"], BC250_PRE_PUSH="off",
                FAIL_CHECK_MANIFEST="1").returncode == 0
    assert calls(repo) == []


def test_by_hand_against_a_base(repo):
    base = git(repo, "rev-parse", "HEAD")
    result = subprocess.run(["bash", "tools/pre-push.sh", base], cwd=repo, capture_output=True, text=True, env=ENV,
                            stdin=subprocess.DEVNULL)
    assert result.returncode == 0, result.stderr
    assert calls(repo)[-2:] == [f"check_manifest.py --base {base}", f"check_changelogs.py --base {base}"]
