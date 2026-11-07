# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/ci_local.py: the jobs it reads from the suite, Console and Nexus workflows (a matrix job once per entry,
Nexus's jobs with nexus- before the name), the ${{ }} expressions it fills in, which jobs a name selects, and the
requirement files that key a job's venv."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

pytest.importorskip("yaml")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ci_local  # noqa: E402

SUITE = Path(__file__).resolve().parents[2]
CI = SUITE / ".github" / "workflows" / "ci.yml"
CI_CONSOLE = SUITE / ".github" / "workflows" / "ci-bazzite-console.yml"
CI_NEXUS = SUITE / ".github" / "workflows" / "ci-nexus.yml"
# ci.yml's plan job runs python3 tools/ci_matrix.py, as in the container; Windows' python3 is the Store's stand-in
PLAN_JOB = pytest.mark.skipif(sys.platform == "win32", reason="ci.yml's plan job runs python3, as in the container")


@PLAN_JOB
def test_every_job_of_ci_yml_and_every_matrix_entry():
    jobs = {j.name: j for j in ci_local.load_jobs(CI)}
    assert {"versions", "native", "shell", "installers", "docs", "windows-exe"} <= set(jobs)
    assert "pytest/bc250-bazzite/apps/gpu" in jobs and "pytest" not in jobs
    assert jobs["pytest/bc250-bazzite/apps/gpu"].matrix == {"dir": "bc250-bazzite/apps/gpu"}
    assert not jobs["windows-exe"].runs_here and jobs["shell"].runs_here


def test_a_matrix_from_a_plan_job_is_read_by_running_it(tmp_path):
    """ci.yml's pytest matrix is the plan job's output (tools/ci_matrix.py, fromJSON): the plan job's steps run
    here and their $GITHUB_OUTPUT lines give the entries; the plan job itself is a job too."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text('''jobs:
  plan:
    runs-on: ubuntu-latest
    outputs:
      dirs: ${{ steps.plan.outputs.dirs }}
    steps:
      - uses: actions/checkout@v7
      - id: plan
        run: echo 'dirs=["a/one", "a/two"]' | tee -a "$GITHUB_OUTPUT"
      - run: echo 'word=plain' >> "$GITHUB_OUTPUT"
  pytest:
    needs: plan
    runs-on: ubuntu-latest
    strategy:
      matrix:
        dir: ${{ fromJSON(needs.plan.outputs.dirs) }}
    steps:
      - run: echo ${{ matrix.dir }}
''', encoding="utf-8")
    jobs = {j.name: j for j in ci_local.load_jobs(workflows / "ci.yml")}
    assert set(jobs) == {"plan", "pytest/a/one", "pytest/a/two"}
    assert jobs["pytest/a/two"].matrix == {"dir": "a/two"}
    assert ci_local.job_outputs(yaml.safe_load((workflows / "ci.yml").read_text())["jobs"], "plan", tmp_path) == {
        "dirs": ["a/one", "a/two"], "word": "plain"}
    assert not list(tmp_path.glob(".ci-local*"))                   # nothing written into the checkout


@PLAN_JOB
def test_nexus_jobs_come_after_the_suites_with_their_prefix():
    """ci-nexus.yml's jobs (core, tools, dev/, the repository's rules) run after both suite workflows."""
    nexus = {j.name: j for j in ci_local.load_jobs(CI_NEXUS, "nexus-")}
    assert {"nexus-versions", "nexus-shell", "nexus-docs", "nexus-pytest/core", "nexus-pytest/tools",
            "nexus-pytest/dev/nrt"} <= set(nexus)
    assert nexus["nexus-pytest/core"].matrix == {"dir": "core"} and all(j.runs_here for j in nexus.values())
    names = [j.name for j in ci_local.all_jobs(SUITE)]
    assert names == ([j.name for j in ci_local.load_jobs(CI)]
                     + [j.name for j in ci_local.load_jobs(CI_CONSOLE, "console-")]
                     + list(nexus)) and len(set(names)) == len(names)


@PLAN_JOB
def test_expressions_and_selection():
    jobs = ci_local.all_jobs(SUITE)
    governor = next(j for j in jobs if j.name == "pytest/bc250-bazzite/apps/gpu")
    assert ci_local.expand("cd ${{ matrix.dir }}", governor, "abc") == "cd bc250-bazzite/apps/gpu"
    assert ci_local.expand("${{ github.event.pull_request.base.sha || github.event.before }}", governor, "abc") == "abc"
    assert [j.name for j in ci_local.selected(jobs, ["nexus-pytest/tools"])] == ["nexus-pytest/tools"]
    assert [j.name for j in ci_local.selected(jobs, ["shell"])] == ["shell"]                  # not nexus-shell too
    assert all(j.name.startswith("pytest/") for j in ci_local.selected(jobs, ["pytest"]))    # the suite's only
    assert [j.name for j in ci_local.selected(jobs, ["nexus-pytest"])] == [
        "nexus-pytest/core", "nexus-pytest/tools", "nexus-pytest/dev/dash", "nexus-pytest/dev/demo",
        "nexus-pytest/dev/itests", "nexus-pytest/dev/nrt", "nexus-pytest/dev/sounds"]
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
    for workflow in (CI, CI_NEXUS):
        spec = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        push = spec.get("on", spec.get(True))["push"]                     # PyYAML reads the key on as True
        assert push.get("branches") == ["**"] and not {"branches-ignore", "tags", "tags-ignore"} & set(push)
        assert all("timeout-minutes" in job for job in spec["jobs"].values()), workflow.name
