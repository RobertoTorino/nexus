# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/check_prose.py: what counts as a finding, what is not text, and a file that reads worse than at the base."""

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

spec = importlib.util.spec_from_file_location("check_prose", TOOLS / "check_prose.py")
cp = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cp
spec.loader.exec_module(cp)

DENSE = ("The guard watches the temperatures: it warns, cools and shuts down; the fans go back as they were "
         "(the firmware's curve or the manual value they had before).\n")
PLAIN = "The guard watches the temperatures. It warns you when the board gets hot.\n"


def kinds(text: str, path: str = "a.md") -> list[str]:
    return sorted(f.kind for f in cp.score_text(path, text).findings)


def test_plain_sentences_have_no_findings():
    assert kinds(PLAIN) == []
    assert cp.score_text("a.md", PLAIN).words == 13


def test_each_kind_of_finding():
    assert kinds(DENSE) == ["colon", "parenthesis", "semicolon"]
    assert kinds("This sentence " + "goes on and " * 10 + "on.\n") == ["long"]
    assert kinds("Pick a colour in the settings.\n") == ["word"]
    assert kinds("See the manual for the steps.\n") == ["word"]
    assert kinds("The fan follows the curve or a manual value.\n") == []


def test_a_name_or_a_command_before_a_colon_is_no_finding():
    assert kinds("- **Turn on…:** turns the guard on with these limits.\n") == []
    assert kinds("To read the guard's log, run this command: `journalctl -u guard`\n") == []
    assert kinds("Not authorized: the dialog was canceled.\n") == []


def test_code_links_headings_and_tables_are_not_sentences():
    text = ("# A heading: with a colon; and more\n\n```bash\nrun; this (one two three four five six)\n```\n\n"
            "See [the page](https://example.org/a;b) and `a; b`.\n\n| Tool | Use |\n|---|---|\n| Git | all; of it |\n")
    assert kinds(text) == ["semicolon"]                 # the table cell's


def test_window_text_in_python_but_no_docstrings_or_labels():
    code = ('"""A docstring: long; and (one two three four five six)."""\n'
            'LABEL = "Turn on…"\n'
            'def f(n):\n'
            '    """Another; docstring."""\n'
            '    return f"The fan is at {n} RPM; check its connector and the header."\n')
    score = cp.score_text("app/window.py", code)
    assert [f.kind for f in score.findings] == ["semicolon"] and score.findings[0].line == 5
    assert score.words == 12


def test_which_files_are_read():
    assert cp.wanted("bc250-bazzite/docs/apps/fan.md") and cp.wanted("bc250-bazzite/apps/fan/fan_control/guard.py")
    assert cp.wanted("README.md") and cp.wanted("dev/dash/nexus_dashboard/main_window.py")
    for path in ("CHANGELOG", "bc250-bazzite/apps/fan/CHANGELOG", "MIGRATION.md", "CLAUDE.md", ".claude/checks.md",
                 "bc250-bazzite/apps/fan/tests/test_guard.py", "tools/check_prose.py",
                 "bc250-bazzite/tools/pin_app.py"):
        assert not cp.wanted(path), path


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_worst_first_and_worse_than_the_base(tmp_path, capsys):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, env=ENV)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "dense.md").write_text(DENSE * 8, encoding="utf-8")
    (tmp_path / "docs" / "plain.md").write_text(PLAIN * 12, encoding="utf-8")
    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "base")

    assert cp.main([], root=tmp_path) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[1].endswith("docs/dense.md") and lines[2].endswith("docs/plain.md")
    assert cp.main(["--base", "HEAD"], root=tmp_path) == 0

    (tmp_path / "docs" / "plain.md").write_text(PLAIN * 12 + DENSE, encoding="utf-8")
    (tmp_path / "docs" / "dense.md").write_text(PLAIN * 12, encoding="utf-8")       # better: no failure
    (tmp_path / "docs" / "new.md").write_text(DENSE, encoding="utf-8")              # new: nothing to compare with
    assert cp.main(["--base", "HEAD"], root=tmp_path) == 1
    out = capsys.readouterr().out
    assert "docs/plain.md: 0.0 ->" in out and "dense.md" not in out and "new.md" not in out
