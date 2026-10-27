#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs the jobs of .github/workflows/ci.yml (the BC250 Bazzite Suite's CI) and ci-nexus.yml (Nexus's: core, the
tools, dev/, the repository's rules) as GitHub runs them, inside the container tools/ci-local.sh starts: Python
3.12, each job (and each entry of a matrix) in its own environment with only what that job installs. Tests that
pass in the suite's full venv on a newer Python can still fail in CI; this shows it before the push.

    tools/ci-local.sh [--list] [--workers N] [job[/matrix value] ...]
    e.g.  tools/ci-local.sh pytest/bc250-bazzite/apps/gpu shell nexus-pytest/tools

The jobs come from the workflows themselves, so a new app in the matrix or a new installer step is run without
changing this. ci-nexus.yml's jobs are listed with nexus- before their name (nexus-shell, nexus-pytest/core), as
both workflows have a versions, pytest, shell and docs job.
What cannot run here is reported, not hidden: a job for another system (windows-latest), apt-get steps (the image
has those packages) and actions/cache (its folder is kept in ~/.cache/bc250-ci-local instead). The work happens on a
copy of the checkout with every change staged, as a commit would have it; logs go to the cache folder."""

from __future__ import annotations

import concurrent.futures
import hashlib
import itertools
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SRC = Path(os.environ.get("CI_LOCAL_SRC", "/src"))          # the checkout, read-only
WORK = Path(os.environ.get("CI_LOCAL_WORK", "/tmp/ci-local-work"))   # the copy the jobs run in
CACHE = Path(os.environ.get("CI_LOCAL_CACHE", "/cache"))     # venvs, pip's cache, logs: kept between runs
WORKFLOWS = (("ci.yml", ""), ("ci-nexus.yml", "nexus-"))     # each workflow run here, with the prefix of its job names
COPY_EXCLUDES = (".venv*", "target", "site", "__pycache__", ".pytest_cache", "dist", "node_modules")
SHELL = ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c"]      # GitHub's shell for run steps on Linux
EXPR = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")
_venv_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


@dataclass
class Job:
    name: str                           # "pytest/tools", "shell"
    spec: dict
    matrix: dict = field(default_factory=dict)

    @property
    def runs_here(self) -> bool:
        return "ubuntu" in str(self.spec.get("runs-on", ""))


@dataclass
class Result:
    job: str
    ok: bool
    seconds: float
    failed_step: str = ""
    tail: str = ""
    notes: list[str] = field(default_factory=list)
    skipped: bool = False               # a job for another system: neither passed nor failed


def load_jobs(workflow: Path, prefix: str = "") -> list[Job]:
    """Every job of the workflow, a matrix job once per combination ("pytest/apps/gpu"), *prefix* before each name."""
    jobs = []
    for name, spec in yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"].items():
        matrix = (spec.get("strategy") or {}).get("matrix") or {}
        keys = [k for k, v in matrix.items() if isinstance(v, list)]
        if not keys:
            jobs.append(Job(prefix + name, spec))
            continue
        for values in itertools.product(*(matrix[k] for k in keys)):
            combo = dict(zip(keys, values))
            jobs.append(Job(f"{prefix}{name}/{'/'.join(str(v) for v in values)}", spec, combo))
    return jobs


def all_jobs(src: Path = SRC) -> list[Job]:
    """The jobs of every workflow run here (WORKFLOWS), in that order."""
    return [job for name, prefix in WORKFLOWS for job in load_jobs(src / ".github" / "workflows" / name, prefix)]


def expand(text: str, job: Job, base: str) -> str:
    """The ${{ }} expressions the workflows use: matrix values, and the base commit of check_manifest and
    check_changelogs (origin/main)."""
    def value(m: re.Match) -> str:
        expr = m.group(1)
        if expr.startswith("matrix."):
            return str(job.matrix.get(expr.removeprefix("matrix."), ""))
        if "github.event" in expr and ("before" in expr or "base.sha" in expr):
            return base
        if expr.startswith("hashFiles") or expr.startswith("runner."):
            return "local"
        return ""
    return EXPR.sub(value, str(text))


def requirement_files(text: str, folder: Path) -> list[Path]:
    """The requirement files a pip line installs, with the files they include (-r), for the venv's key."""
    found, todo = [], [folder / m for m in re.findall(r"-r\s+(\S+)", text)]
    while todo:
        path = todo.pop()
        if path in found or not path.is_file():
            continue
        found.append(path)
        todo += [path.parent / m for m in re.findall(r"^\s*-r\s+(\S+)", path.read_text(encoding="utf-8"), re.M)]
    return found


def venv_for(job: Job, steps: list[dict], base: str) -> Path:
    """A venv per set of requirements: reused while they stay the same, so a package dropped from them cannot
    linger and hide a missing dependency (as the full venv did)."""
    key = hashlib.sha256()
    workdir = WORK / expand((job.spec.get("defaults") or {}).get("run", {}).get("working-directory", "."), job, base)
    for step in steps:
        run = expand(step.get("run", ""), job, base)
        if "pip install" in run:
            key.update(run.encode())
            folder = WORK / expand(step.get("working-directory", ""), job, base) if step.get("working-directory") \
                else workdir
            for path in requirement_files(run, folder):
                key.update(path.read_bytes())
    venv = CACHE / "venvs" / key.hexdigest()[:16]
    with _locks_lock:
        lock = _venv_locks.setdefault(venv.name, threading.Lock())
    with lock:                              # jobs with the same requirements share it: made once
        if not (venv / "bin" / "python").exists():
            shutil.rmtree(venv, ignore_errors=True)
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    return venv


def cache_hit(step_id: str, steps: list[dict], job: Job, base: str) -> bool:
    for step in steps:
        if step.get("id") == step_id and "cache" in str(step.get("uses", "")):
            path = expand((step.get("with") or {}).get("path", ""), job, base).replace("~", str(Path.home()), 1)
            return Path(path).is_dir() and any(Path(path).iterdir())        # an empty folder is no cache
    return False


def run_job(job: Job, base: str) -> Result:
    started = time.monotonic()
    steps = job.spec.get("steps", [])
    if not job.runs_here:
        return Result(job.name, True, 0, notes=[f"not run here: needs {job.spec.get('runs-on')}"], skipped=True)
    venv = venv_for(job, steps, base)
    log_path = CACHE / "logs" / (job.name.replace("/", "_") + ".log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    defaults = (job.spec.get("defaults") or {}).get("run", {})
    env = dict(os.environ, PATH=f"{venv}/bin:{os.environ['PATH']}", VIRTUAL_ENV=str(venv),
               PIP_CACHE_DIR=str(CACHE / "pip"), CI="true", GITHUB_ACTIONS="true")
    env.update({k: expand(v, job, base) for k, v in (job.spec.get("env") or {}).items()})
    result = Result(job.name, True, 0)
    with log_path.open("w", encoding="utf-8") as log:
        for number, step in enumerate(steps, 1):
            label = step.get("name") or step.get("uses") or str(step.get("run", "")).splitlines()[0]
            if "uses" in step:
                if "cache" in step["uses"]:
                    result.notes.append(f"{label}: kept in ~/.cache/bc250-ci-local")
                continue                            # checkout: the copy; setup-python: the image's 3.12
            condition = str(step.get("if", ""))
            hit = re.search(r"steps\.(\S+?)\.outputs\.cache-hit\s*!=\s*'true'", condition)
            if hit and cache_hit(hit.group(1), steps, job, base):
                continue
            run = expand(step["run"], job, base)
            if "apt-get" in run:
                continue                            # the image has these packages
            workdir = WORK / expand(step.get("working-directory") or defaults.get("working-directory", "."), job,
                                    base)
            step_env = dict(env, **{k: expand(v, job, base) for k, v in (step.get("env") or {}).items()})
            log.write(f"\n===== {number}. {label} (in {workdir.relative_to(WORK)})\n{run}\n")
            log.flush()
            proc = subprocess.run([*SHELL, run], cwd=workdir, env=step_env, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, errors="replace")
            log.write(proc.stdout)
            if proc.returncode != 0:
                result.ok, result.failed_step = False, label
                result.tail = "\n".join(proc.stdout.rstrip().splitlines()[-25:])
                break
    result.seconds = time.monotonic() - started
    return result


def prepare_copy() -> str:
    """The checkout copied to WORK with every change staged, as the commit would have it; returns origin/main."""
    if WORK.exists():
        shutil.rmtree(WORK)
    excludes = [f"--exclude={pattern}" for pattern in COPY_EXCLUDES]
    subprocess.run(["rsync", "-a", "--delete", *excludes, f"{SRC}/", f"{WORK}/"], check=True)
    subprocess.run(["git", "add", "-A"], cwd=WORK, check=True)
    base = subprocess.run(["git", "rev-parse", "origin/main"], cwd=WORK, capture_output=True, text=True)
    return base.stdout.strip() if base.returncode == 0 else ""


def selected(jobs: list[Job], wanted: list[str]) -> list[Job]:
    if not wanted:
        return jobs
    """A job by its full name (pytest/tools), or every entry of a job by the job's name (pytest)."""
    return [j for j in jobs if any(j.name == w or j.name.split("/", 1)[0] == w for w in wanted)]


def main(argv: list[str]) -> int:
    workers = max(2, (os.cpu_count() or 4) // 2)
    if "--workers" in argv:
        i = argv.index("--workers")
        workers, argv = int(argv[i + 1]), argv[:i] + argv[i + 2:]
    jobs = all_jobs()
    if "--list" in argv:
        print("\n".join(j.name + ("" if j.runs_here else f"   (not here: {j.spec.get('runs-on')})") for j in jobs))
        return 0
    jobs = selected(jobs, argv)
    if not jobs:
        print(f"no job matches {' '.join(argv)}; tools/ci-local.sh --list shows them", file=sys.stderr)
        return 2
    base = prepare_copy()
    print(f"{len(jobs)} jobs from {' and '.join(name for name, _ in WORKFLOWS)}, {workers} at a time, "
          f"on Python {sys.version.split()[0]}", flush=True)
    results: list[Result] = []
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        for result in pool.map(lambda j: run_job(j, base), jobs):
            results.append(result)
            mark = "skip" if result.skipped else "ok  " if result.ok else "FAIL"
            print(f"  {mark} {result.job:45s} {result.seconds:6.1f} s"
                  + (f"   {'; '.join(result.notes)}" if result.notes else ""), flush=True)
    failed = [r for r in results if not r.ok]
    ran = [r for r in results if not r.skipped]
    for r in failed:
        print(f"\n===== {r.job}: {r.failed_step}\n{r.tail}")
    skipped = len(results) - len(ran)
    print(f"\n{len(ran) - len(failed)} of {len(ran)} jobs passed" + (f", {skipped} not run here" if skipped else "")
          + f"; logs in {os.environ.get('CI_LOCAL_HOST_LOGS', CACHE / 'logs')}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
