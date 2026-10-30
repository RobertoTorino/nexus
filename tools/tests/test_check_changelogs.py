# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/check_changelogs.py: no CHANGELOG loses an entry it had at the base, on a small git repository."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

spec = importlib.util.spec_from_file_location("check_changelogs", TOOLS / "check_changelogs.py")
cc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cc
spec.loader.exec_module(cc)

OLD = "Changelog: 02-10-2026 10:00:00\n\nFixed. Second.\n\nChangelog: 01-10-2026 10:00:00\n\nAdded. First.\n"
NEW = "Changelog: 03-10-2026 10:00:00\n\nAdded. Third.\n\n"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True, env=ENV).stdout


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "suite"
    for path in ("CHANGELOG", "apps/alpha/CHANGELOG", "apps/beta/CHANGELOG"):
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(OLD)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "pushed")
    git(root, "tag", "pushed")
    return root


def test_new_entries_on_top_are_fine(repo):
    (repo / "CHANGELOG").write_text(NEW + OLD)
    assert cc.check(repo, "pushed") == []


def test_an_old_entry_may_be_corrected(repo):
    (repo / "apps/alpha/CHANGELOG").write_text(OLD.replace("Second.", "Second, corrected."))
    assert cc.check(repo, "pushed") == []


def test_a_file_cut_down_to_its_new_entries_fails(repo):
    """What happened once: a CHANGELOG written over with only the newest entry."""
    (repo / "CHANGELOG").write_text(NEW)
    problems = cc.check(repo, "pushed")
    assert problems == ["CHANGELOG: 2 of the 2 entries it had at pushed are gone "
                        "(the newest: 'Changelog: 02-10-2026 10:00:00')"]


def test_one_entry_gone_fails(repo):
    (repo / "apps/beta/CHANGELOG").write_text(NEW + OLD.split("\n\n", 2)[2])
    problems = cc.check(repo, "pushed")
    assert len(problems) == 1 and problems[0].startswith("apps/beta/CHANGELOG: 1 of the 2")


def test_a_changelog_goes_only_with_its_folder(repo):
    (repo / "apps/alpha/CHANGELOG").unlink()
    assert cc.check(repo, "pushed") == ["apps/alpha/CHANGELOG: removed, while its folder is still there"]
    shutil.rmtree(repo / "apps/alpha")
    assert cc.check(repo, "pushed") == []                     # an app removed


def test_a_changelog_follows_a_git_mv(repo):
    """An app moved elsewhere (bc250-bazzite/apps/suite to dev/nrt, 26-10-2026): its CHANGELOG is compared with
    its new place, staged or committed, and still loses nothing."""
    (repo / "dev").mkdir()
    git(repo, "mv", "apps/alpha", "dev/alpha")
    assert cc.renamed(repo, "pushed") == {"apps/alpha/CHANGELOG": "dev/alpha/CHANGELOG"}
    assert cc.check(repo, "pushed") == []                     # staged
    git(repo, "commit", "-qm", "moved")
    (repo / "dev/alpha/CHANGELOG").write_text(NEW + OLD)
    assert cc.check(repo, "pushed") == []                     # committed, with a new entry
    (repo / "dev/alpha/CHANGELOG").write_text(NEW)
    assert cc.check(repo, "pushed") == ["apps/alpha/CHANGELOG: 2 of the 2 entries it had at pushed are gone "
                                        "(the newest: 'Changelog: 02-10-2026 10:00:00')"]


def test_without_a_base_it_passes(capsys):
    assert cc.main([]) == 0
    assert "nothing to compare" in capsys.readouterr().out
