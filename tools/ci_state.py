#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Whether GitHub's CI passed on a commit: every run of .github/workflows/ci.yml on it (the push to main; a tag
starts none of its own) finished and passed; with --workflow, of another workflow: a suite's own CI
(ci-windows-portable.yml: each suite's releases wait for its own CI, not another suite's, owner 27-10-2026) or
Nexus's (ci-nexus.yml, which every suite's releases wait for besides their own). tools/tag-release.sh asks it
before tagging, and the release workflows before they build, so only a commit that CI passed becomes a release.

    python3 tools/ci_state.py [--wait MINUTES] [--workflow FILE] [--release-commit] <commit>

Prints the state (passed, failed, running, none) and the runs. Exit status: 0 passed, 1 failed, 2 still running or
no run yet (after waiting --wait minutes, default 0), 3 GitHub not reachable. A suite's CI runs only when a push
changes the suite or the shared parts (the workflows' paths, 29-10-2026), so a commit may have no run at all: when
none has appeared after NONE_GRACE_S of waiting, the answer is "none" at once, with the reason, rather than after the
whole wait. Signs in with GH_TOKEN, GITHUB_TOKEN
or the gh login when there is one (60 requests an hour without, 5,000 with). BC250_CI_STATE answers instead of
GitHub (passed, failed, running, none): for the tests of tag-release.sh.

With --release-commit (the release workflows, owner 30-10-2026): when the commit only writes a release
(tools/release_commit.py: versions, Release and Version entries, apps.toml's tags and sha256), the CI of its parent,
the work commit, answers for it, so a release does not wait for CI to run again on the same code. When the work
commit has no run of the workflow (its push did not touch the workflow's paths), the commit's own CI answers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = "RobertoTorino/nexus"
RUNS_URL = "https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs?head_sha={sha}&per_page=50"
WORKFLOW = "ci.yml"                     # the BC250 Bazzite Suite's; another suite: ci-<suite>.yml; Nexus: ci-nexus.yml
OK = ("success", "skipped", "neutral")
POLL_S = 30
NONE_GRACE_S = 300                      # a run GitHub is about to start appears well within this
EXIT = {"passed": 0, "failed": 1, "running": 2, "none": 2}
NO_RUN = ("no run of {workflow} on {sha}: it runs only when a push changes its suite or the shared parts (the "
          "workflow's paths). Tag a commit that changed them, or push one.")


def repo_slug() -> str:
    """owner/name: GitHub Actions says it; else the origin remote; else the suite's repository."""
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        url = ""
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    return match.group(1) if match else REPO


def token() -> str:
    found = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    gh = shutil.which("gh") or "/home/linuxbrew/.linuxbrew/bin/gh"
    if not found and os.access(gh, os.X_OK):
        try:
            out = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, timeout=10)
            found = out.stdout.strip() if out.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            pass
    return found


def fetch_runs(sha: str, workflow: str = WORKFLOW) -> list[dict]:
    """The runs of *workflow* on *sha*; raises OSError when GitHub cannot be reached or refuses (its hourly limit)."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "bc250-ci-state"}
    signed = token()
    if signed:
        headers["Authorization"] = f"Bearer {signed}"
    request = urllib.request.Request(RUNS_URL.format(repo=repo_slug(), workflow=workflow, sha=sha), headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.load(response)
    return [r for r in data.get("workflow_runs", []) if isinstance(r, dict)]


def state(runs: list[dict]) -> str:
    if not runs:
        return "none"
    if any(r.get("status") != "completed" for r in runs):
        return "running"
    return "passed" if all(r.get("conclusion") in OK for r in runs) else "failed"


def describe(runs: list[dict]) -> list[str]:
    return [f"  CI on {r.get('head_branch')}: {r.get('conclusion') or r.get('status')}  {r.get('html_url', '')}"
            for r in runs]


def check(sha: str, wait_minutes: float = 0, fetch=fetch_runs, sleep=time.sleep, now=time.monotonic,
          workflow: str = WORKFLOW) -> int:
    stub = os.environ.get("BC250_CI_STATE")
    started = now()
    deadline = started + wait_minutes * 60
    while True:
        if stub:
            current, lines = stub, []
        else:
            try:
                runs = fetch(sha) if workflow == WORKFLOW else fetch(sha, workflow)
            except (OSError, ValueError) as exc:
                print(f"unreachable: GitHub could not be asked about {sha[:7]} ({exc})", file=sys.stderr)
                return 3
            current, lines = state(runs), describe(runs)
        if stub or current in ("passed", "failed") or now() >= deadline:      # a fixed answer: no use waiting
            break
        if current == "none" and now() >= started + NONE_GRACE_S:               # no run is coming
            print(NO_RUN.format(workflow=workflow, sha=sha[:7]), file=sys.stderr)
            break
        print(f"CI on {sha[:7]}: {current}, looking again in {POLL_S} s", file=sys.stderr, flush=True)
        sleep(POLL_S)
    print(current)
    for line in lines:
        print(line)
    return EXIT.get(current, 3)


def work_commit_of(sha: str) -> str | None:
    """The parent of *sha* when *sha* only writes a release (tools/release_commit.py); else None."""
    import release_commit                   # next to this file
    return release_commit.check(sha)[0]


def check_release_commit(sha: str, wait_minutes: float = 0, workflow: str = WORKFLOW, fetch=fetch_runs,
                         work_commit=work_commit_of, **kwargs) -> int:
    """check() of the work commit when *sha* only writes a release and the work commit has a run; else of *sha*."""
    work = None if os.environ.get("BC250_CI_STATE") else work_commit(sha)
    if work is not None:
        try:
            has_run = bool(fetch(work) if workflow == WORKFLOW else fetch(work, workflow))
        except (OSError, ValueError):
            has_run = True                          # check() says it is unreachable
        if has_run:
            print(f"{sha[:7]} only writes a release: the CI of its work commit {work[:7]} answers for it",
                  file=sys.stderr)
            return check(work, wait_minutes, fetch=fetch, workflow=workflow, **kwargs)
        print(f"{sha[:7]} only writes a release, but its work commit {work[:7]} has no run of {workflow}: the "
              "commit's own CI answers", file=sys.stderr)
    return check(sha, wait_minutes, fetch=fetch, workflow=workflow, **kwargs)


def main(argv: list[str]) -> int:
    wait, workflow, release = 0.0, WORKFLOW, False
    while argv[:1] == ["--release-commit"] or argv[:1] in (["--wait"], ["--workflow"]) and len(argv) >= 2:
        if argv[0] == "--release-commit":
            release, argv = True, argv[1:]
            continue
        if argv[0] == "--wait":
            wait = float(argv[1])
        else:
            workflow = argv[1]
        argv = argv[2:]
    if len(argv) != 1:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 3
    if release:
        return check_release_commit(argv[0], wait, workflow=workflow)
    return check(argv[0], wait, workflow=workflow)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
