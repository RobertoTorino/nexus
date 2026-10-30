# SPDX-License-Identifier: GPL-3.0-or-later
"""A Nexus release (owner, 30-10-2026): the one action of the Nexus Release Tool, Start new release, and what follows
it. No Qt here; the page is release_page.py.

The release holds every suite on the Nexus release (its release workflow can be called by release-nexus.yml) with
an app that needs a release, and core and Nexus's own version. The owner sees each version first and may type
another (owner: "keep the override"); a portal's and Nexus's version are worked out when Start writes them (at least
what the app releases need, check_manifest.py's rule), unless one is typed. Start writes the release, as steps 1
and 2 would (the versions and their copies, the "Release x.y.z." entries, the new tags in apps.toml with their
sha256 left for the workflow, the portal's version and its entry, Nexus's), then one command commits it, pushes it
(the pre-push hook checks it) and starts release-nexus.yml on that commit. The workflow builds, publishes and pins;
each suite's portal ends as a draft. The device test installs that draft on the handheld (check-release.ps1 draft);
Publish makes it a release, which makes the portal tag and the Nexus index. A run that failed is started again from
where it stopped (gh run rerun --failed); one that should not go on is stopped (gh run cancel)."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from . import plan as rp

AUTO = "auto"                           # a portal's or Nexus's version, worked out when Start writes the release
NEXUS_WORKFLOW = "release-nexus.yml"
WORKFLOW_NAME = "Release Nexus"         # its name on GitHub, as the runs list it
_RUN_ID = re.compile(r"/actions/runs/(\d+)")


def on_nexus_release(root: Path, suite: str) -> bool:
    """Whether release-nexus.yml carries the suite: its release-<suite>.yml can be called (workflow_call)."""
    workflow = root / ".github" / "workflows" / f"release-{suite}.yml"
    return workflow.is_file() and "workflow_call:" in workflow.read_text(encoding="utf-8")


def release_suites(root: Path) -> list[str]:
    return [suite for suite in rp.suites(root) if on_nexus_release(root, suite)]


@dataclass
class Pick:
    """One row of the release: an app, a portal, core or Nexus, with the versions offered (the first one is the
    suggestion), why, and what the owner chose."""
    unit: rp.Unit
    suite: str                          # "" for core and Nexus, which are every suite's
    choices: list[str]
    why: str
    version: str = ""                   # the chosen one; "" or AUTO: the suggestion
    notes: str = ""

    @property
    def label(self) -> str:
        return self.unit.key if not self.suite else f"{self.suite} · {self.unit.key}"


def picks(root: Path) -> list[Pick]:
    """What a Nexus release would hold now: per suite on the release, each portal app that needs a release and the
    portal; core when it changed since its last version; Nexus whenever anything is released."""
    found: list[Pick] = []
    shared: list[rp.Unit] = []
    for suite in release_suites(root):
        units = rp.load_units(root, suite)
        shared = shared or units
        blobs = rp.read_blobs(root, rp.changelog_specs(units))
        apps = [u for u in units if u.kind == "app" and not u.standalone and u.needs_release]
        for unit in apps:
            choices, why = rp.version_choices(root, unit, blobs)
            found.append(Pick(unit, suite, choices, why, choices[0]))
        portal = next(u for u in units if u.kind == "portal")
        if apps or portal.needs_release:
            found.append(Pick(portal, suite, [AUTO, *rp.next_versions(portal.version).values()],
                              "worked out at Start: at least what its app releases ask (check_manifest.py) and its "
                              "own CHANGELOG entries", AUTO))
    shared = shared or rp.load_units(root)
    core = next((u for u in shared if u.kind == "core"), None)
    if core is not None and not core.current and core.in_apps:
        choices, why = rp.version_choices(root, core)
        found.append(Pick(core, "", choices, why, choices[0]))
    nexus = next((u for u in shared if u.kind == rp.NEXUS), None)
    if nexus is not None and (found or nexus.needs_release):
        found.append(Pick(nexus, "", [AUTO, *rp.next_versions(nexus.version).values()],
                          "worked out at Start: a suite's release is at least minor (owner, 28-10-2026), and its own "
                          "CHANGELOG entries", AUTO))
    return found


def problems(chosen: list[Pick]) -> list[str]:
    """What is wrong with the versions typed, before anything is written."""
    found = []
    for pick in chosen:
        version = pick.version.strip() or AUTO
        if version == AUTO and pick.unit.kind in ("portal", rp.NEXUS):
            continue
        released = pick.unit.released or pick.unit.kind == "core"
        if msg := rp.check_new_version(pick.unit.version, version, released):
            found.append(f"{pick.label}: {msg}")
    return found


def higher(a: str, b: str) -> str:
    return a if rp.version_tuple(a) >= rp.version_tuple(b) else b


def write(root: Path, chosen: list[Pick], base: str = "origin/main") -> tuple[list[str], list[str]]:
    """Writes the release: each suite's apps (version, copies, entry, the new tag in apps.toml), then its portal, then
    core, then Nexus. Returns the log and the release's tags (the apps' and portals'; Nexus's last as nexus-v<x>)."""
    log: list[str] = []
    tags: list[str] = []
    suites = list(dict.fromkeys(p.suite for p in chosen if p.suite))
    for suite in suites:
        for pick in (p for p in chosen if p.suite == suite and p.unit.kind == "app"):
            unit, new = pick.unit, pick.version.strip() or pick.choices[0]
            if new != unit.version:
                rp.set_version(root, unit, new)
            text = rp.release_text(new, pick.notes)
            rp.add_changelog_entry(root, unit, text, base=base)
            rp.pin(root, unit, "", suite)               # the new tag; its sha256 is the workflow's
            tags.append(unit.tag)
            log.append(f"{suite} · {unit.key}: {new}, \"{text}\", apps.toml pins {unit.tag}")
        portal_pick = next((p for p in chosen if p.suite == suite and p.unit.kind == "portal"), None)
        if portal_pick is None:
            continue
        portal = portal_pick.unit
        typed = portal_pick.version.strip()
        suggested, why = rp.portal_suggestion(root, portal, suite)
        minimum, need = rp.portal_minimum(root, base, portal.version, suite)
        new = typed if typed and typed != AUTO else suggested
        if minimum and rp.version_tuple(minimum) > rp.version_tuple(new):
            log.append(f"{suite} · portal: {new} is less than CI asks ({need}): {minimum}")
            new = minimum
        if new != portal.version:
            rp.set_version(root, portal, new)
        text = rp.portal_text(new, rp.changed_pins(root, base, suite), portal_pick.notes,
                              rp.changed_withdrawals(root, base, suite))
        rp.add_changelog_entry(root, portal, text, base=base)
        tags.append(portal.tag)
        log.append(f"{suite} · portal: {new} ({why}), \"{text}\"")
    for pick in (p for p in chosen if p.unit.kind == "core"):
        new = pick.version.strip() or pick.choices[0]
        if new != pick.unit.version:
            rp.set_version(root, pick.unit, new)
        text = f"Version {new}." + (f" {pick.notes.strip()}" if pick.notes.strip() else "")
        rp.add_changelog_entry(root, pick.unit, text, base=base)
        log.append(f"core: {new}, \"{text}\"")
    for pick in (p for p in chosen if p.unit.kind == rp.NEXUS):
        # Its suggestion counts the suites' releases written above (plan.suite_releases reads the working tree).
        nexus = next(u for u in rp.load_units(root, suites[0] if suites else None) if u.kind == rp.NEXUS)
        typed = pick.version.strip()
        new = typed if typed and typed != AUTO else rp.version_choices(root, nexus)[0][0]
        text = rp.bump_nexus(root, new, pick.notes, base=base)
        tags.append(f"{rp.NEXUS}-v{new}")
        log.append(f"nexus: {new}, \"{text}\"")
    return log, tags


def ready(root: Path, base: str = "origin/main") -> list[str]:
    """Why Start new release cannot go yet ([] when it can): the working tree must be clean and HEAD must be what
    was pushed last, so the release commit holds the release and nothing else."""
    reasons = []
    dirty = rp.git(root, "status", "--porcelain")
    if dirty is None:
        return ["This folder is not a git checkout."]
    if dirty.strip():
        reasons.append("The working tree has changes: commit and push them first, or put them away.")
    head = (rp.git(root, "rev-parse", "HEAD") or "").strip()
    pushed = (rp.git(root, "rev-parse", "--verify", "-q", base) or "").strip()
    if not pushed:
        reasons.append(f"No {base} here: git fetch first.")
    elif head != pushed:
        ahead = int((rp.git(root, "rev-list", "--count", f"{base}..HEAD") or "0").strip() or 0)
        behind = rp.behind(root, base)
        reasons.append(f"HEAD has {ahead} commit{'s' if ahead != 1 else ''} not pushed: push them first."
                       if ahead else f"{base} has {behind} commit{'s' if behind != 1 else ''} this checkout does "
                       "not: git pull first.")
    return reasons


def unpushed_release(root: Path, base: str = "origin/main") -> str:
    """HEAD's subject when HEAD is a release commit Start made that is not pushed yet, right on top of *base* (the
    push stopped: the pre-push hook found something, or the network); "" otherwise."""
    subject = (rp.git(root, "log", "-1", "--format=%s") or "").strip()
    parent = (rp.git(root, "rev-parse", "-q", "--verify", "HEAD^") or "").strip()
    pushed = (rp.git(root, "rev-parse", "-q", "--verify", base) or "").strip()
    return subject if subject.startswith("Release ") and pushed and parent == pushed else ""


def commit_message(tags: list[str]) -> str:
    return f"Release {', '.join(tags)}"


def push_and_start_command() -> str:
    """The release commit pushed (the pre-push hook checks it) and release-nexus.yml started on it."""
    return (f'git push origin HEAD:main && gh workflow run {NEXUS_WORKFLOW} --ref main -f commit="$(git rev-parse '
            f"HEAD)\" && echo 'Started {NEXUS_WORKFLOW} on '\"$(git rev-parse --short HEAD)\"")


def start_command(message: str) -> str:
    """The one command Start runs in the command line (bash, on Windows too): the release commit, its push, and
    release-nexus.yml started on it."""
    return f"git commit -a -q -m {shlex.quote(message)} && {push_and_start_command()}"


def release_run(runs: list[rp.BuildRun], sha: str = "") -> rp.BuildRun | None:
    """The newest run of release-nexus.yml (on *sha* when given): GitHub lists the newest first."""
    return next((r for r in runs if (r.file == NEXUS_WORKFLOW or r.workflow == WORKFLOW_NAME)
                 and (not sha or r.sha == sha)), None)


def run_id(run: rp.BuildRun) -> str:
    found = _RUN_ID.search(run.url)
    return found[1] if found else ""


def stop_command(run: rp.BuildRun) -> str:
    return f"gh run cancel {run_id(run)}"


def resume_command(run: rp.BuildRun) -> str:
    """Started again from where it stopped: only the jobs that failed or were canceled, and what needs them."""
    return f"gh run rerun {run_id(run)} --failed"


def waiting_portals(root: Path) -> list[str]:
    """The portal tag of each suite on the Nexus release, as portal/VERSION says: what a device test and Publish
    work on after a release ran (a draft until published)."""
    return [f"{rp.tag_prefix(root, suite)}portal-v"
            f"{(rp.suite_dir(root, suite) / 'portal' / 'VERSION').read_text(encoding='utf-8').strip()}"
            for suite in release_suites(root)]


def publish_command(tag: str) -> str:
    """The owner's yes after the device test: the draft becomes a release, which makes its tag (on the pin commit)
    and starts the Nexus index. Never GitHub's Latest: that is the index."""
    return f"gh release edit {tag} --draft=false --latest=false"


def device_test_line(root: Path, suite: str, tag: str, windows: bool) -> str:
    """The suite's check script with its draft mode, for a terminal: PowerShell's call operator on Windows."""
    script = str(root / rp.check_script(root, suite))
    if windows:
        return "& '" + script.replace("'", "''") + f"' draft {tag}"
    return f"{shlex.quote(script)} draft {tag}"
