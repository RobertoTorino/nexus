# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/ci_local.py: the jobs it reads from ci.yml (a matrix job once per entry), the ${{ }} expressions it fills
in, which jobs a name selects, and the requirement files that key a job's venv."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ci_local  # noqa: E402

SUITE = Path(__file__).resolve().parents[2]
CI = SUITE / ".github" / "workflows" / "ci.yml"


def test_every_job_of_ci_yml_and_every_matrix_entry():
    jobs = {j.name: j for j in ci_local.load_jobs(CI)}
    assert {"versions", "native", "shell", "installers", "docs", "windows-exe"} <= set(jobs)
    assert "pytest/tools" in jobs and "pytest/bc250-bazzite/apps/gpu" in jobs and "pytest" not in jobs
    assert jobs["pytest/bc250-bazzite/apps/gpu"].matrix == {"dir": "bc250-bazzite/apps/gpu"}
    assert not jobs["windows-exe"].runs_here and jobs["shell"].runs_here


def test_expressions_and_selection():
    jobs = ci_local.load_jobs(CI)
    governor = next(j for j in jobs if j.name == "pytest/bc250-bazzite/apps/gpu")
    assert ci_local.expand("cd ${{ matrix.dir }}", governor, "abc") == "cd bc250-bazzite/apps/gpu"
    assert ci_local.expand("${{ github.event.pull_request.base.sha || github.event.before }}", governor, "abc") == "abc"
    assert [j.name for j in ci_local.selected(jobs, ["pytest/tools"])] == ["pytest/tools"]   # not .../gui as well
    assert all(j.name.startswith("pytest/") for j in ci_local.selected(jobs, ["pytest"]))
    assert ci_local.selected(jobs, []) == jobs


def test_requirement_files_follow_includes(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "requirements.txt").write_text("PyQt6\n")
    (tmp_path / "app" / "requirements-dev.txt").write_text("-r ../requirements.txt\npytest\n")
    found = ci_local.requirement_files("python -m pip install -q -r requirements-dev.txt", tmp_path / "app")
    assert [p.resolve() for p in found] == [(tmp_path / "app" / "requirements-dev.txt").resolve(),
                                            (tmp_path / "requirements.txt").resolve()]


def test_ci_runs_for_every_branch_push_and_no_tag():
    """A push to a branch runs CI, a tag does not (tag-release.sh tags only a commit CI passed). GitHub reads a push
    filter with only tags or tags-ignore as "no branch at all", which ran CI for no push."""
    import yaml
    spec = yaml.safe_load(CI.read_text(encoding="utf-8"))
    push = spec.get("on", spec.get(True))["push"]                     # PyYAML reads the key on as True
    assert push.get("branches") == ["**"] and not {"branches-ignore", "tags", "tags-ignore"} & set(push)
    assert all("timeout-minutes" in job for job in spec["jobs"].values())
