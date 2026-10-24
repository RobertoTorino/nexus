#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Whether GitHub's CI passed on a commit: every run of .github/workflows/ci.yml on it (the push to main; a tag
starts none of its own) finished and passed. tools/tag-release.sh asks it before tagging, and release.yml before it builds, so
only a commit that CI passed becomes a release.

    python3 tools/ci_state.py [--wait MINUTES] <commit>

Prints the state (passed, failed, running, none) and the runs. Exit status: 0 passed, 1 failed, 2 still running or
no run yet (after waiting --wait minutes, default 0), 3 GitHub not reachable. Signs in with GH_TOKEN, GITHUB_TOKEN
or the gh login when there is one (60 requests an hour without, 5,000 with). BC250_CI_STATE answers instead of
GitHub (passed, failed, running, none): for the tests of tag-release.sh."""

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
RUNS_URL = "https://api.github.com/repos/{repo}/actions/workflows/ci.yml/runs?head_sha={sha}&per_page=50"
OK = ("success", "skipped", "neutral")
POLL_S = 30
EXIT = {"passed": 0, "failed": 1, "running": 2, "none": 2}


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


def fetch_runs(sha: str) -> list[dict]:
    """The CI runs on *sha*; raises OSError when GitHub cannot be reached or refuses (its hourly limit)."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "bc250-ci-state"}
    signed = token()
    if signed:
        headers["Authorization"] = f"Bearer {signed}"
    request = urllib.request.Request(RUNS_URL.format(repo=repo_slug(), sha=sha), headers=headers)
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


def check(sha: str, wait_minutes: float = 0, fetch=fetch_runs, sleep=time.sleep, now=time.monotonic) -> int:
    stub = os.environ.get("BC250_CI_STATE")
    deadline = now() + wait_minutes * 60
    while True:
        if stub:
            current, lines = stub, []
        else:
            try:
                runs = fetch(sha)
            except (OSError, ValueError) as exc:
                print(f"unreachable: GitHub could not be asked about {sha[:7]} ({exc})", file=sys.stderr)
                return 3
            current, lines = state(runs), describe(runs)
        if stub or current in ("passed", "failed") or now() >= deadline:      # a fixed answer: no use waiting
            break
        print(f"CI on {sha[:7]}: {current}, looking again in {POLL_S} s", file=sys.stderr, flush=True)
        sleep(POLL_S)
    print(current)
    for line in lines:
        print(line)
    return EXIT.get(current, 3)


def main(argv: list[str]) -> int:
    wait = 0.0
    if argv[:1] == ["--wait"] and len(argv) >= 2:
        wait, argv = float(argv[1]), argv[2:]
    if len(argv) != 1:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 3
    return check(argv[0], wait)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
