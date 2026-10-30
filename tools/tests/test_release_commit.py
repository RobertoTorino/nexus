# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/release_commit.py: a commit that only writes a release (owner, 30-10-2026: its work commit's CI answers for
it) is told from one that changes anything more, which must never pass."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import release_commit  # noqa: E402

APP = "s/apps/demo"
WORK = {
    "VERSION": "1.1.0\n",
    "CHANGELOG": "Changelog: 30-10-2026 17:18:10\n\nFixed. Something.\n",
    f"{APP}/VERSION": "2.0.0\n",
    f"{APP}/CHANGELOG": "Changelog: 30-10-2026 16:00:00\n\nAdded. A feature.\n",
    f"{APP}/demo/__init__.py": 'NAME = "Demo"\n__version__ = "2.0.0"\n\ndef run():\n    return 1\n',
    f"{APP}/run.sh": '#!/bin/bash\nVERSION="2.0.0"   # = VERSION\necho hi\n',
    f"{APP}/pyproject.toml": '[project]\nname = "demo"\nversion = "2.0.0"           # = VERSION\n',
    "s/portal/apps.toml": '[apps.demo]\nname = "Demo"\ntag = "demo-v2.0.0"\nsha256 = "abc"\nrequired = true\n',
}
RELEASE = {
    "VERSION": "1.2.0\n",
    "CHANGELOG": "Changelog: 30-10-2026 19:43:50\n\nRelease 1.2.0. Brings demo-v2.1.0.\n\n" + WORK["CHANGELOG"],
    f"{APP}/VERSION": "2.1.0\n",
    f"{APP}/CHANGELOG": "Changelog: 30-10-2026 19:43:48\n\nRelease 2.1.0.\n\n" + WORK[f"{APP}/CHANGELOG"],
    f"{APP}/demo/__init__.py": WORK[f"{APP}/demo/__init__.py"].replace("2.0.0", "2.1.0"),
    f"{APP}/run.sh": WORK[f"{APP}/run.sh"].replace("2.0.0", "2.1.0"),
    f"{APP}/pyproject.toml": WORK[f"{APP}/pyproject.toml"].replace("2.0.0", "2.1.0"),
    "s/portal/apps.toml": WORK["s/portal/apps.toml"].replace('"demo-v2.0.0"\nsha256 = "abc"',
                                                             '"demo-v2.1.0"\nsha256 = ""'),
}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", *args],
                          cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def commit(repo: Path, files: dict[str, str | None], message: str) -> str:
    for name, text in files.items():
        path = repo / name
        if text is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q")
    work = commit(tmp_path, WORK, "work")
    monkeypatch.setattr(release_commit, "ROOT", tmp_path)
    return tmp_path, work


def test_a_release_commit_as_the_nexus_release_tool_writes_it(repo):
    path, work = repo
    sha = commit(path, RELEASE, "Release demo-v2.1.0")
    assert release_commit.check(sha) == (work, [])
    pin = commit(path, {"s/portal/apps.toml": RELEASE["s/portal/apps.toml"].replace('sha256 = ""',
                                                                                     'sha256 = "def"')}, "Pin")
    assert release_commit.check(pin) == (sha, [])                      # the pin commit, too


@pytest.mark.parametrize("change, reason", [
    ({f"{APP}/demo/__init__.py": RELEASE[f"{APP}/demo/__init__.py"].replace("return 1", "return 2")},
     "a line other than a version copy changed"),
    ({f"{APP}/demo/__init__.py": RELEASE[f"{APP}/demo/__init__.py"].replace('"2.1.0"', '"2.1.0"; run()')},
     "a line other than a version copy changed"),
    ({f"{APP}/demo/__init__.py": RELEASE[f"{APP}/demo/__init__.py"] + "run()\n"}, "lines added or removed"),
    ({f"{APP}/run.sh": RELEASE[f"{APP}/run.sh"].replace("echo hi", "rm -rf /tmp/x")},
     "a line other than a version copy changed"),
    ({f"{APP}/VERSION": "2.1.0\nrm\n"}, "a VERSION that is not one x.y.z line"),
    ({f"{APP}/CHANGELOG": "Changelog: 30-10-2026 19:43:48\n\nFixed. A fix slipped in.\n\n"
      + WORK[f"{APP}/CHANGELOG"]}, "no Release x.y.z. or Version x.y.z. line"),
    ({f"{APP}/CHANGELOG": RELEASE[f"{APP}/CHANGELOG"].replace("A feature", "A different feature")},
     "changed below its new entries"),
    ({"s/portal/apps.toml": RELEASE["s/portal/apps.toml"].replace("required = true", "required = false")},
     "a line other than tag or sha256 changed"),
    ({"s/portal/apps.toml": RELEASE["s/portal/apps.toml"].replace('tag = "demo-v2.1.0"', 'sha256 = "x"')},
     "a line other than tag or sha256 changed"),
    ({f"{APP}/demo/new.py": "print(1)\n"}, "added"),
    ({f"{APP}/run.sh": None}, "removed"),
    ({"README.md": "x\n"}, "added"),
])
def test_anything_more_is_not_a_release_commit(repo, change, reason):
    path, _ = repo
    sha = commit(path, {**RELEASE, **change}, "Release and more")
    first, reasons = release_commit.check(sha)
    assert first is None and any(reason in r for r in reasons), reasons


def test_a_changed_file_that_holds_no_version_copy(repo):
    path, _ = repo
    commit(path, {"s/docs/page.md": "Version 2.0.0\n"}, "docs")
    sha = commit(path, {**RELEASE, "s/docs/page.md": "Version 2.1.0\n"}, "Release")
    first, reasons = release_commit.check(sha)
    assert first is None and reasons == ["s/docs/page.md: not a VERSION, CHANGELOG, apps.toml or version copy"]


def test_a_merge_or_an_unknown_parent_is_not(repo, capsys):
    path, work = repo
    git(path, "checkout", "-q", "-b", "side")
    side = commit(path, {"x.txt": "x\n"}, "side")
    git(path, "checkout", "-q", "-")
    commit(path, RELEASE, "Release")
    git(path, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-edit", side)
    assert release_commit.check(git(path, "rev-parse", "HEAD"))[0] is None
    assert release_commit.check(work)[0] is None                       # the root commit
    assert release_commit.main([work]) == 1 and "more than a release commit" in capsys.readouterr().err
