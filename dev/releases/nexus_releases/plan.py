#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The file edits of a release, for the window in main_window.py (and on their own: tools/release.sh --list lists
the apps). Nothing here commits, tags or pushes; it prints the git commands for that instead. It needs no PyQt6 and
no bc250_core, so it also runs with the system python3.

A release has two steps, because an app's checksum only exists once GitHub has built its release:

1. Release apps: the new VERSION, every copy that tools/check_versions.py checks, and a "Release x.y.z." CHANGELOG entry.
   The version offered first follows semantic versioning from the CHANGELOG entries since the last tag: one that
   starts with Breaking. asks for a major release, Added. for a minor one, Fixed. for a patch.
   Commit, push, tag <app>-v<x.y.z>, push the tag: release.yml builds the tarball and SHA256SUMS.
2. Pin and release Portal: pin each released app in portal/apps.toml (tag and sha256, as tools/pin_app.py), bump portal/VERSION at
   least as much as tools/check_manifest.py asks, and a CHANGELOG entry listing the pins. Commit, test on a board
   (check-release.sh local), then push and tag portal-v<x.y.z>, and check the published release
   (check-release.sh release).

A withdrawal (owner's decisions, 13-10-2026): an app release that must not be used any more (privacy, security, any
reason) is marked withdrawn in portal/apps.toml with the reason, and on GitHub (a pre-release titled "Withdrawn: ...",
so no update check offers it; the release itself stays). The next portal release shows the app as not available and
removes it from the boards that have it. Test it on a board with Test withdrawal before that portal is pushed."""

from __future__ import annotations

import datetime
import importlib.util
import json
import re
import shlex
import urllib.error
import urllib.request
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

CHECKOUT = Path(__file__).resolve().parents[3]        # dev/releases/nexus_releases/plan.py: the checkout (Nexus)
TOOLS = CHECKOUT / "tools"              # the Nexus tools (check_versions.py, stage_app.py, suites.py)
TAG_SCRIPT = "tools/tag-release.sh"     # tags only a pushed HEAD that holds the version: never one before the bump
CI_LOCAL = "tools/ci-local.sh"          # CI's jobs here, in a container (Linux): the push only when they pass
VERSIONS_CHECK = "tools/check_versions.py"                        # the Nexus tools' check, every suite
# A suite's own tools, in its tools/ (check_script(), record_script() and manifest_check() give the path in the
# checkout): the board checks of a portal release, the portal's video tour and the manifest check.
CHECK_SCRIPT = "tools/check-release.sh"
WINDOWS_CHECK_SCRIPT = "tools/check-release.ps1"    # a Windows suite's, on the handheld
RECORD_SCRIPT = "tools/record-tour.sh"
MANIFEST_CHECK = "tools/check_manifest.py"
CHECKOUT_ONLY = ".checkout-only"        # an app folder with this marker runs from the checkout and is never released
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
GIT_WORKERS = 8                         # git processes load_units() runs at once


def _load(name: str, folder: Path = TOOLS):
    spec = importlib.util.spec_from_file_location(name, folder / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check_versions = _load("check_versions")
stage_app = _load("stage_app")
nexus_suites = _load("suites")


def suites(root: Path = CHECKOUT) -> list[str]:
    """The suites in the checkout *root*, by name: each folder directly under it with portal/apps.toml
    (tools/suites.py); [] when *root* is laid out as a suite itself (the repositories the tests make)."""
    return [p.name for p in nexus_suites.suites(root) if p != root]


def suite_dir(root: Path, suite: str | None = None) -> Path:
    """The folder of the suite *suite* in the checkout *root* (its portal, apps, docs and tools), or of the first
    suite when none is named; *root* itself when it is laid out as a suite (the repositories the tests make)."""
    if suite:
        return root / suite
    names = suites(root)
    return root / names[0] if names else root


# The manifest's parser and the pin tool are a suite's (its portal reads its manifest): the first suite's serve
# every suite while the suites' portals read one kind of manifest.
check_manifest = _load("check_manifest", suite_dir(CHECKOUT) / "tools")
pin_app = _load("pin_app", suite_dir(CHECKOUT) / "tools")
_manifest_tools: dict[Path, object] = {}


def tag_prefix(root: Path, suite: str | None = None) -> str:
    """What the suite's release tags start with (its TAG_PREFIX, tools/suites.py): "wp-" for the Windows Portable
    Suite, "" for the BC250 suite."""
    return nexus_suites.tag_prefix(suite_dir(root, suite))


def manifest_tools(root: Path, suite: str | None = None):
    """The check_manifest module that reads the suite's apps.toml and counts its portal bumps: a suite with a tag
    prefix has a manifest of its own (wp-<app>-v<x.y.z> tags, its own categories), read by its own
    tools/check_manifest.py; the first suite's serves the suites without one."""
    folder = suite_dir(root, suite) / "tools"
    if not tag_prefix(root, suite) or not (folder / "check_manifest.py").is_file():
        return check_manifest
    key = folder.resolve()
    if key not in _manifest_tools:
        spec = importlib.util.spec_from_file_location(f"check_manifest_{key.parent.name}", folder / "check_manifest.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _manifest_tools[key] = module
    return _manifest_tools[key]


def rel(root: Path, *parts: str, suite: str | None = None) -> str:
    """A path in the suite's folder, relative to *root* (as git names it): "bc250-bazzite/portal/apps.toml"."""
    return (suite_dir(root, suite) / Path(*parts)).relative_to(root).as_posix()


def check_script(root: Path, suite: str | None = None) -> str:
    """The suite's board checks of a portal release (check-release.sh local|release), relative to the checkout; a
    Windows suite's are check-release.ps1 (local|release|installer), run on the handheld."""
    if suite_system(root, suite) == "windows":
        return rel(root, *WINDOWS_CHECK_SCRIPT.split("/"), suite=suite)
    return rel(root, *CHECK_SCRIPT.split("/"), suite=suite)


def suite_system(root: Path, suite: str | None = None) -> str:
    """The system the suite is made for and tested on: "bazzite" or "windows" (its SYSTEM file)."""
    return nexus_suites.system(suite_dir(root, suite))


def tests_here(root: Path, suite: str | None = None, platform: str | None = None) -> bool:
    """Whether the suite's release checks run on this computer (*platform*, sys.platform's): a Bazzite suite's on
    Linux (the board), a Windows suite's on Windows (the handheld)."""
    return ((platform or sys.platform) == "win32") == (suite_system(root, suite) == "windows")


def portal_run_script(root: Path, suite: str | None = None) -> str:
    """A Windows suite has no check-release.sh: its portal is tried on the handheld from the checkout, with its
    portal/run.ps1 (it installs the pinned apps from their GitHub releases). That path, relative to the checkout; ""
    for a suite tested on the board with check-release.sh."""
    if nexus_suites.system(suite_dir(root, suite)) != "windows":
        return ""
    return rel(root, "portal", "run.ps1", suite=suite)


def record_script(root: Path, suite: str | None = None) -> str:
    """The suite's script that records its portal's video tour, relative to the checkout."""
    return rel(root, *RECORD_SCRIPT.split("/"), suite=suite)


def manifest_check(root: Path, suite: str | None = None) -> str:
    """The suite's manifest check (check_manifest.py), relative to the checkout."""
    return rel(root, *MANIFEST_CHECK.split("/"), suite=suite)


def manifest_checks(root: Path, only: list[str] | None = None) -> list[str]:
    """The suites' manifest checks, as the commit runs them: every suite's, or those in *only* (touched_suites())."""
    return [manifest_check(root, suite) for suite in (suites(root) or [None]) if only is None or suite in only]


def touched_suites(root: Path, paths: list[str]) -> list[str] | None:
    """The suites whose folder holds one of *paths* (the root's copy of apps.toml, portal/, counts for the suite it
    copies): the commit checks those alone, as each suite's CI checks only its own (owner, 28-10-2026: a Windows
    check never holds a Bazzite commit). None in a checkout without suite folders: every check then."""
    names = suites(root)
    if not names:
        return None
    return [name for name in names
            if any(p.startswith(f"{name}/") or (p.startswith("portal/") and manifest_copy(root, name) is not None)
                   for p in paths)]


def staged_suites(root: Path) -> list[str] | None:
    """touched_suites() of what is staged: the suites the commit changes."""
    return touched_suites(root, (git(root, "diff", "--cached", "--name-only") or "").splitlines())


def version_checks(only: list[str] | None = None) -> list[str]:
    """check_versions.py as the commit runs it: every suite (*only* None), else each suite in *only* with core and
    dev/ (--suite), or core and dev/ alone (--nexus) when the commit touches no suite."""
    if only is None:
        return [VERSIONS_CHECK]
    return [f"{VERSIONS_CHECK} --suite {name}" for name in only] or [f"{VERSIONS_CHECK} --nexus"]


def manifest_path(root: Path, suite: str | None = None) -> Path:
    return suite_dir(root, suite) / "portal" / "apps.toml"


def manifest_copy(root: Path, suite: str | None = None) -> Path | None:
    """The root's copy of apps.toml, for the portals installed before the suite moved into bc250-bazzite/ (they
    read it at a tag for their update notice); check_manifest.py keeps it identical. None once the owner removed it,
    while the checkout is laid out as a suite, or for a suite that is not the first (the copy is the BC250 suite's)."""
    copy = root / "portal" / "apps.toml"
    first = suite_dir(root)
    return copy if first != root and suite_dir(root, suite) == first and copy.is_file() else None


def write_manifest(root: Path, text: str, suite: str | None = None) -> list[Path]:
    """Writes apps.toml, and the root's copy while there is one. Returns the files written."""
    paths = [manifest_path(root, suite)] + [p for p in [manifest_copy(root, suite)] if p]
    for path in paths:
        path.write_bytes(text.encode("utf-8"))
    return paths


def version_tuple(version: str) -> tuple[int, int, int]:
    a, b, c = (int(x) for x in version.split("."))
    return a, b, c


def next_versions(version: str) -> dict[str, str]:
    a, b, c = version_tuple(version)
    return {"patch": f"{a}.{b}.{c + 1}", "minor": f"{a}.{b + 1}.0", "major": f"{a + 1}.0.0"}


def check_new_version(current: str, new: str, released: bool) -> str:
    """"" when *new* can be released after *current*, otherwise why not. A version that was never tagged (the
    first release, 0.1.0) can be released as it is."""
    if not _VERSION.match(new):
        return f"{new!r} is not x.y.z"
    if version_tuple(new) < version_tuple(current) or (released and new == current):
        return f"{new} is not higher than {current}" + (", which is already tagged" if released else "")
    return ""


# --- git (read-only) -------------------------------------------------------------------------------------------

def git(root: Path, *args: str) -> str | None:
    # UTF-8, as git writes it: Windows' own encoding (cp1252) garbled every é and × of a CHANGELOG read at a tag, so
    # its entries no longer matched and step 1 counted them all as new.
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
    return result.stdout if result.returncode == 0 else None


def checkout_stamp(root: Path) -> str:
    """The checkout's last commit and its time in Amsterdam ("c109b51 · 15-10-2026 03:46"): Nexus Releases is never
    released, so its VERSION stays put and this says which code runs. "" outside a git checkout."""
    out = (git(root, "log", "-1", "--format=%h %ct") or "").split()
    if len(out) != 2 or not out[1].isdigit():
        return ""
    when = amsterdam_now(datetime.datetime.fromtimestamp(int(out[1]), datetime.timezone.utc))
    return f"{out[0]} · {when:%d-%m-%Y %H:%M}"


def all_tags(root: Path) -> list[str]:
    """Every tag of the checkout, read once: load_units() picks each unit's from it, as one git process per unit
    made the window slow on Windows (owner, 27-10-2026), where starting a process takes some 20 ms."""
    return (git(root, "tag", "--list") or "").split()


def tags_of(root: Path, key: str, prefix: str = "", tags: list[str] | None = None) -> list[str]:
    """The release tags of one app (or the portal), oldest first; *prefix*: the suite's (tag_prefix()); *tags*:
    all_tags() when already read."""
    found = []
    head = f"{prefix}{key}-v"
    listed = (git(root, "tag", "--list", f"{head}*") or "").split() if tags is None else \
        [tag for tag in tags if tag.startswith(head)]
    for tag in listed:
        version = tag[len(head):]
        if _VERSION.match(version):
            found.append((version_tuple(version), tag))
    return [tag for _, tag in sorted(found)]


def commits_since(root: Path, tag: str | None, path: str) -> int | None:
    out = git(root, "rev-list", "--count", f"{tag}..HEAD" if tag else "HEAD", "--", path)
    return int(out) if out and out.strip().isdigit() else None


# --- The units -------------------------------------------------------------------------------------------------

# Nexus's own version (owner, 28-10-2026): the root VERSION, bumped like an app's with a "Release x.y.z." entry in
# the root CHANGELOG. Never tagged here: nexus-index.yml publishes GitHub's Latest release as nexus-v<VERSION>.
NEXUS = "nexus"

@dataclass
class Unit:
    key: str                            # "gpu", "portal", "core"
    path: str                           # "bc250-bazzite/apps/gpu", relative to the checkout
    version: str
    last_tag: str | None                # newest <key>-v* tag; None for core (bundled, never tagged)
    commits: int | None                 # commits touching the folder since that tag
    pinned_tag: str = ""                # apps only: what portal/apps.toml pins
    pinned_sha: str = ""
    changed: list[str] | None = None    # shipped files that differ from the last tag; None: never released
    in_apps: list[str] = field(default_factory=list)  # core only: the apps whose release would carry its changes
    current: bool = False               # core only: nothing it ships changed since its VERSION was last bumped
    standalone: bool = False            # apps only: released separately, never pinned in the portal
    prefix: str = ""                    # the suite's tag prefix: "wp-" makes wp-test-v0.1.0
    released_as: str = ""               # nexus only: the version of the root CHANGELOG's newest "Release x.y.z."
    suite_releases: list[str] = field(default_factory=list)   # nexus only: the suites' releases since that version

    @property
    def needs_release(self) -> bool:
        """Something it ships changed since its last tag (or it was never released). Core is never released; Nexus
        when its CHANGELOG has entries since its last release (changed holds them), when a suite has a release since
        then (suite_releases: the Nexus index lists them, so its number moves too), or it never had one."""
        if self.kind == "nexus":
            return not self.released_as or bool(self.changed) or bool(self.suite_releases)
        return self.kind != "core" and (self.last_tag is None or bool(self.changed))

    @property
    def release_reason(self) -> str:
        if self.kind == "nexus":
            n = len(self.changed or [])
            parts = ([f"{n} CHANGELOG entr{'ies' if n != 1 else 'y'}"] if n else []) + self.suite_releases
            return "first release" if not self.released_as else f"yes: {', '.join(parts)}" if parts else "no"
        if self.kind == "core":
            n = len(self.in_apps)
            releases = f"{n} app release{'s' if n != 1 else ''}"
            if n and self.current:
                return f"{self.version} has it: goes into {releases}"
            return f"changed: goes into {releases}" if n else "no"
        if self.last_tag is None:
            return "first release"
        if not self.changed:
            return "no"
        core = [f for f in self.changed if f.startswith("core/")]
        own = len(self.changed) - len(core)
        parts = ([f"{own} file{'s' if own != 1 else ''}"] if own else []) + (["core"] if core else [])
        return "yes: " + " + ".join(parts)

    @property
    def kind(self) -> str:
        return self.key if self.key in ("core", "portal", NEXUS) else "app"

    @property
    def tag(self) -> str:
        """The tag of the current VERSION."""
        return f"{self.tag_head}{self.version}"

    @property
    def tag_head(self) -> str:
        """What its tags start with, before the version: "gpu-v", "wp-test-v"."""
        return f"{self.prefix}{self.key}-v"

    @property
    def released(self) -> bool:
        if self.kind == "nexus":                # its tag is the index workflow's: released once its entry is written
            return self.released_as == self.version
        return self.last_tag == self.tag


def shipped_sources(root: Path, key: str, path: str, suite: str | None = None) -> list[str]:
    """The source paths a release of *key* is made from, as tools/stage_app.py stages it."""
    paths = [path]
    if key != "core" and stage_app.uses_core(root / path):
        paths.append("core/bc250_core")
    if key not in ("core", "portal") and (suite_dir(root, suite) / "docs" / "apps" / f"{key}.md").is_file():
        paths.append(rel(root, "docs", "apps", f"{key}.md", suite=suite))
    return paths


def is_shipped(rel: str) -> bool:
    parts = rel.split("/")
    return not (set(parts) & stage_app.SKIP_DIRS) and parts[-1] not in stage_app.SKIP_FILES \
        and not parts[-1].endswith(".pyc") and not any(p.startswith(".venv") for p in parts)


def untracked(root: Path) -> list[str]:
    """The checkout's new files that git does not know yet (and does not ignore), read once for every unit."""
    return (git(root, "ls-files", "--others", "--exclude-standard") or "").splitlines()


def changed_since(root: Path, tag: str, paths: list[str], new_files: list[str] | None = None) -> list[str]:
    """Shipped files under *paths* that differ between *tag* and the working tree: committed, not yet committed
    and new (untracked) files alike; *new_files*: untracked() when already read."""
    diff = git(root, "diff", "--name-only", tag, "--", *paths) or ""
    if new_files is None:
        new = (git(root, "ls-files", "--others", "--exclude-standard", "--", *paths) or "").splitlines()
    else:
        new = [f for f in new_files if any(f == p or f.startswith(p.rstrip("/") + "/") for p in paths)]
    return sorted({f for f in [*diff.splitlines(), *new] if f and is_shipped(f)})


def read_blobs(root: Path, specs: list[str]) -> dict[str, str | None]:
    """The text of each "<rev>:<path>" in *specs*, read by one git cat-file --batch (None for one that does not
    exist), instead of a git show per file."""
    if not specs:
        return {}
    result = subprocess.run(["git", "cat-file", "--batch"], cwd=root, input="".join(f"{s}\n" for s in specs).encode(),
                            capture_output=True)
    out, at, found = result.stdout, 0, {}
    for spec in specs:
        end = out.find(b"\n", at)
        if end < 0:
            found[spec] = None
            continue
        header = out[at:end].decode(errors="replace").split()
        at = end + 1
        if len(header) == 3 and header[1] == "blob":
            size = int(header[2])
            found[spec] = out[at:at + size].decode("utf-8", errors="replace")
            at += size + 1                                  # the blob and its closing newline
        else:
            found[spec] = None                              # "<spec> missing", or not a blob
    return found


def bad_tags(root: Path, units: list[Unit]) -> list[str]:
    """Tags that point at a commit whose VERSION is not the tag's version: tagged before the version bump was
    committed. release.yml refuses to build those; delete the tag and tag the right commit again."""
    out = []
    tagged = [unit for unit in units if unit.kind != "core" and unit.last_tag]
    versions = read_blobs(root, [f"{unit.last_tag}:{unit.path}/VERSION" for unit in tagged])
    for unit in tagged:
        at_tag = (versions.get(f"{unit.last_tag}:{unit.path}/VERSION") or "").strip()
        want = unit.last_tag[len(unit.tag_head):]
        if at_tag and at_tag != want:
            out.append(f"{unit.last_tag} points at a commit where {unit.path}/VERSION is {at_tag}")
    return out


def load_units(root: Path = CHECKOUT, suite: str | None = None) -> list[Unit]:
    """Core, the suite's portal and its apps, each with its version, tags and pin (*suite*: a folder name from
    suites(); None: the first suite)."""
    pins = {}
    tools = manifest_tools(root, suite)
    prefix = tag_prefix(root, suite)
    every_tag, new_files = all_tags(root), untracked(root)        # once, not per unit: see all_tags()
    try:
        for entry in tools.manifest.load(manifest_path(root, suite)):
            pins[entry.key] = entry
    except (OSError, tools.manifest.ManifestError):
        pass
    units = []
    folders = [("core", "core")] + ([(NEXUS, ".")] if (root / "VERSION").is_file() else [])
    folders += [("portal", rel(root, "portal", suite=suite))]
    folders += [(p.name, rel(root, "apps", p.name, suite=suite)) for p in sorted((suite_dir(root, suite) / "apps").iterdir())
                if (p / "VERSION").is_file() and not (p / CHECKOUT_ONLY).is_file()]
    for key, path in folders:
        version = (root / path / "VERSION").read_text(encoding="utf-8").strip()
        tags = tags_of(root, key, prefix, every_tag) if key not in ("core", NEXUS) else []
        last = tags[-1] if tags else None
        unit = Unit(key, path, version, last, None,
                    standalone=(root / path / ".standalone").is_file(),
                    prefix="" if key in ("core", NEXUS) else prefix)
        if key in pins:
            unit.pinned_tag, unit.pinned_sha = pins[key].tag, pins[key].sha256
        units.append(unit)

    # Each unit's two git questions (commits since its tag, files changed since it) depend on its own tag. They run
    # side by side: a git process is mostly waiting to start, some 20 ms on Windows (owner, 27-10-2026: the window
    # was slow there), and the answers are the same as one after the other.
    def ask(unit: Unit) -> None:
        if unit.kind == NEXUS:                  # its CHANGELOG says what changed, not its files (the whole checkout)
            return
        unit.commits = commits_since(root, unit.last_tag, unit.path)
        if unit.last_tag:
            unit.changed = changed_since(root, unit.last_tag, shipped_sources(root, unit.key, unit.path, suite),
                                         new_files)
    with ThreadPoolExecutor(max_workers=GIT_WORKERS) as pool:
        list(pool.map(ask, units))
    # Core is never tagged: it ships inside each app that imports it, so its changes are the core files those
    # apps' releases would carry.
    core = units[0]
    carriers = [u for u in units if u.kind not in ("core", NEXUS) and any(f.startswith("core/") for f in u.changed or [])]
    core.in_apps = [u.key for u in carriers]
    core.changed = sorted({f for u in carriers for f in u.changed or [] if f.startswith("core/")})
    core.current = core_is_current(root, new_files)
    for unit in units:
        if unit.kind == NEXUS:
            text = (root / "CHANGELOG").read_text(encoding="utf-8") if (root / "CHANGELOG").is_file() else ""
            unit.released_as = last_release(text)
            unit.changed = [b.split("\n", 1)[0] for b in new_entries(root, unit)] if unit.released_as else []
            unit.suite_releases = suite_releases(root) if unit.released_as else []
    return units


NEW_SUITE = "new suite "


def suite_releases(root: Path) -> list[str]:
    """The suites' releases since Nexus's last version, as their tags ("wp-test-v1.3.0"): every app and portal, of
    every suite, whose VERSION differs from what it was in the last commit that changed the root VERSION, tagged
    already or still to be (the working tree counts). Latest, the Nexus index, lists every suite's newest portal and
    is made anew after each release, so its number has to move with them (owner, 28-10-2026: a Latest that still said
    v0.3.0 after a suite's release looked as if nothing had changed). [] while the root VERSION is changed and not
    committed (the bump that takes them in), or never committed. A suite that came since is listed as "new suite
    <folder>"."""
    if git(root, "diff", "--quiet", "HEAD", "--", "VERSION") is None:
        return []
    base = (git(root, "log", "-1", "--format=%H", "--", "VERSION") or "").strip()
    if not base:
        return []
    out = git(root, "diff", "--name-only", base, "--", ":(glob)**/apps/*/VERSION", ":(glob)**/portal/VERSION") or ""
    new = [f"{NEW_SUITE}{p.name}" for p in nexus_suites.suites(root)
           if p != root and git(root, "cat-file", "-e", f"{base}:{p.relative_to(root).as_posix()}/portal/apps.toml")
           is None]
    found = []
    for path in out.split():
        folder = root / path.rsplit("/", 1)[0]
        version_file = root / path
        if not version_file.is_file() or (folder / CHECKOUT_ONLY).is_file():
            continue
        suite = next((p for p in nexus_suites.suites(root) if folder.is_relative_to(p)), root)
        prefix = nexus_suites.tag_prefix(suite)
        key = "portal" if folder.name == "portal" else folder.name
        found.append(f"{prefix}{key}-v{version_file.read_text(encoding='utf-8').strip()}")
    return new + sorted(found)


_RELEASE = re.compile(r"^Release (\d+\.\d+\.\d+)\.")


def last_release(changelog: str) -> str:
    """The version of the newest "Release x.y.z." entry of a CHANGELOG; "" without one."""
    for entry in changelog_entries(changelog):
        found = _RELEASE.match(entry_body(entry))
        if found:
            return found[1]
    return ""


def core_is_current(root: Path, new_files: list[str] | None = None) -> bool:
    """Whether core's VERSION already covers what it ships: nothing under core/bc250_core changed since the commit
    that last changed core/VERSION, or that VERSION is changed and not committed yet (a bump in progress). Then an
    app release carries core as it is, and core needs no new version. *new_files*: untracked(), read already."""
    if git(root, "diff", "--quiet", "HEAD", "--", "core/VERSION") is None:
        return True
    bump = (git(root, "log", "-1", "--format=%H", "--", "core/VERSION") or "").strip()
    return bool(bump) and not changed_since(root, bump, ["core/bc250_core"], new_files)


# --- Edits -----------------------------------------------------------------------------------------------------

def set_version(root: Path, unit: Unit, new: str) -> list[Path]:
    """Writes *new* to the unit's VERSION and to every copy check_versions.py checks; returns the changed files.
    Nexus's VERSION has no copies: its folder is the whole checkout, whose copies are the other units'."""
    folder = root / unit.path
    changed = [folder / "VERSION"]
    (folder / "VERSION").write_bytes(f"{new}\n".encode())
    if unit.kind == NEXUS:
        unit.version = new
        return changed
    for path in sorted(folder.rglob("*")):
        parts = path.relative_to(folder).parts
        if not path.is_file() or "tests" in parts or "target" in parts:
            continue
        pattern = check_versions.version_pattern(path)       # Cargo.lock too: CI builds Rust with --locked
        if pattern is None:
            continue
        text = path.read_text(encoding="utf-8")
        new_text = pattern.sub(lambda m: m.group(0).replace(f'"{m.group(1)}"', f'"{new}"'), text)
        if new_text != text:
            path.write_bytes(new_text.encode("utf-8"))
            changed.append(path)
    unit.version = new
    return changed


def amsterdam_now(now: datetime.datetime | None = None) -> datetime.datetime:
    """Europe/Amsterdam time without a tz database (Windows has none): CET, CEST from the last Sunday of March to
    the last Sunday of October, switching at 01:00 UTC."""
    utc = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(datetime.timezone.utc)

    def last_sunday(month: int) -> datetime.datetime:
        day = datetime.datetime(utc.year, month, 31, 1, tzinfo=datetime.timezone.utc)
        return day - datetime.timedelta(days=(day.weekday() + 1) % 7)

    summer = last_sunday(3) <= utc < last_sunday(10)
    return (utc + datetime.timedelta(hours=2 if summer else 1)).replace(tzinfo=None)


def add_changelog_entry(root: Path, unit: Unit, text: str, now: datetime.datetime | None = None,
                        base: str = "origin/main") -> Path:
    """Puts "Changelog: <time>", a blank line and *text* on top of the unit's CHANGELOG. A release entry ("Release
    x.y.z.") replaces the newest entry when that is the same release already, so applying a release again (after a
    check stopped the commit) leaves one entry, with the latest notes (owner, 28-10-2026: "Release 1.3.0." twice).
    Never one *base* (the last push) has: that is history, which check_changelogs.py keeps (owner, 29-10-2026: the
    portal release replaced the "Release 3.2.0. Pins ..." entry its app release had pushed, and the push failed)."""
    path = root / unit.path / "CHANGELOG"
    stamp = amsterdam_now(now).strftime("%d-%m-%Y %H:%M:%S")
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    release = _RELEASE.match(text.strip())
    if release:
        entries = changelog_entries(old)
        newest = _RELEASE.match(entry_body(entries[0])) if entries else None
        pushed = git(root, "show", f"{base}:{Path(unit.path).as_posix()}/CHANGELOG") if newest else None
        if newest and newest[1] == release[1] and entries[0] not in changelog_entries(pushed or ""):
            old = old[old.index(entries[0]) + len(entries[0]):].lstrip("\n")
    path.write_bytes(f"Changelog: {stamp}\n\n{text.strip()}\n\n{old}".encode("utf-8"))
    return path


def release_text(version: str, notes: str) -> str:
    return f"Release {version}." + (f" {notes.strip()}" if notes.strip() else "")


def nexus_notes(notes: str, releases: list[str]) -> str:
    """The notes of Nexus's release entry: what was entered, else what the suites brought since its last version
    ("Brings wp-portal-v1.3.0."), so the entry says why the index moved."""
    if notes.strip() or not releases:
        return notes
    new = [r.removeprefix(NEW_SUITE) for r in releases if r.startswith(NEW_SUITE)]
    tags = [r for r in releases if not r.startswith(NEW_SUITE)]
    parts = ([f"the new suite{'s' if len(new) != 1 else ''} {', '.join(new)}"] if new else []) + tags
    return f"Brings {', '.join(parts)}."


def bump_nexus(root: Path, version: str, notes: str = "", base: str = "origin/main") -> str:
    """Nexus's version and its release entry, as step 1's Apply of the nexus row writes them; the entry's text."""
    nexus = next(u for u in load_units(root) if u.kind == NEXUS)
    text = release_text(version, nexus_notes(notes, suite_releases(root)))
    if version != nexus.version:
        set_version(root, nexus, version)
    add_changelog_entry(root, nexus, text, base=base)
    return text


# --- The kind of change: semantic versioning (owner, 15-10-2026) -----------------------------------------------

# A CHANGELOG entry starts with the kind of change it is; a release takes the highest kind since its last tag.
CHANGE_WORDS = {"Breaking.": "major", "Added.": "minor", "Fixed.": "patch"}
LEVELS = ("patch", "minor", "major")
# Entries the release tools write themselves: they are no change of their own.
TOOL_ENTRIES = ("Release ", "Version ", "Withdrawn: ", "Withdrawal of ")
_ENTRY = re.compile(r"^Changelog: .*$", re.M)


def changelog_entries(text: str) -> list[str]:
    """Each entry of a CHANGELOG, header line included, newest first."""
    starts = [m.start() for m in _ENTRY.finditer(text)]
    return [text[a:b].strip() for a, b in zip(starts, starts[1:] + [len(text)])]


def entry_body(entry: str) -> str:
    return entry.split("\n", 1)[1].strip() if "\n" in entry else ""


def change_word(body: str) -> str:
    """The entry's kind (Breaking., Added., Fixed.), "" when it has none."""
    return next((word for word in CHANGE_WORDS if body.startswith(word + " ") or body == word), "")


def changelog_specs(units: list[Unit]) -> list[str]:
    """The CHANGELOGs new_entries() reads at the units' last tags, as "<tag>:<path>/CHANGELOG": read them all at once
    with read_blobs() and hand that to version_choices() (one git process for the whole table, not one per row)."""
    specs = []
    for unit in units:
        if unit.kind == "core" or not unit.last_tag:
            continue
        specs.append(f"{unit.last_tag}:{unit.path}/CHANGELOG")
        if any(f.startswith("core/") for f in unit.changed or []):
            specs.append(f"{unit.last_tag}:core/CHANGELOG")
    return specs


def new_entries(root: Path, unit: Unit, blobs: dict[str, str | None] | None = None) -> list[str]:
    """The change entries (bodies) since the unit's last tag: its own, and core's when the release carries a core
    change. Core itself, never tagged: its entries since its last "Version x.y.z." entry. *blobs*: the CHANGELOGs at
    the tags, read already (changelog_specs())."""
    def since(path: str, ref: str | None, mark: str = "Version ") -> list[str]:
        file = root / path / "CHANGELOG"
        current = changelog_entries(file.read_text(encoding="utf-8")) if file.is_file() else []
        if ref is None:
            cut = next((i for i, e in enumerate(current) if entry_body(e).startswith(mark)), len(current))
            current = current[:cut]
        else:
            spec = f"{ref}:{path}/CHANGELOG"
            text = blobs[spec] if blobs is not None and spec in blobs else git(root, "show", spec)
            old = set(changelog_entries(text or ""))
            current = [e for e in current if e not in old]
        return [b for b in map(entry_body, current) if b and not b.startswith(TOOL_ENTRIES)]

    if unit.kind == "core":
        return since(unit.path, None)
    if unit.kind == NEXUS:                      # the root CHANGELOG since its last "Release x.y.z." entry
        return since(unit.path, None, "Release ")
    entries = since(unit.path, unit.last_tag) if unit.last_tag else []
    if unit.last_tag and any(f.startswith("core/") for f in unit.changed or []):
        entries += since("core", unit.last_tag)
    return entries


def suggested_level(entries: list[str]) -> tuple[str, str]:
    """The release level the entries ask for (patch, minor, major), and why. An entry without a kind counts as a
    fix, and says so."""
    counts = {word: 0 for word in CHANGE_WORDS}
    unmarked = 0
    for body in entries:
        word = change_word(body)
        if word:
            counts[word] += 1
        else:
            unmarked += 1
    level = max((CHANGE_WORDS[w] for w, n in counts.items() if n), key=LEVELS.index, default="patch")
    parts = [f"{n} {w.rstrip('.')}" for w, n in counts.items() if n] + \
            ([f"{unmarked} without Breaking./Added./Fixed. (counted as a fix)"] if unmarked else [])
    return level, ", ".join(parts) or "no CHANGELOG entries"


def _tagged_version(unit: Unit) -> str:
    """The version of the unit's last tag, where the next version counts from; its VERSION without a tag (Nexus:
    its last release)."""
    if unit.kind == NEXUS and unit.released_as:
        return unit.released_as
    return unit.last_tag[len(unit.tag_head):] if unit.last_tag else unit.version


def version_choices(root: Path, unit: Unit, blobs: dict[str, str | None] | None = None) -> tuple[list[str], str]:
    """The versions step 1 offers for the unit, the one semantic versioning gives first, and why. Breaking. ->
    major, Added. -> minor, otherwise patch, counted from the last tag. A VERSION bumped further already, never
    tagged, comes first; a first release is offered as it is."""
    nexts = list(next_versions(unit.version).values())
    if unit.kind == "core" and unit.current:
        return [unit.version] + nexts, f"{unit.version} already holds core's changes"
    if unit.kind == NEXUS and not unit.released_as or unit.kind not in ("core", NEXUS) and unit.last_tag is None:
        return [unit.version] + nexts, "the first release"
    level, why = suggested_level(new_entries(root, unit, blobs))
    if unit.kind == NEXUS:
        level, why = nexus_level(level, why, unit.suite_releases)
    suggested = next_versions(_tagged_version(unit))[level]
    reason = f"{level}: {why}" + (f" since {unit.last_tag}" if unit.last_tag else
                                  f" since Release {unit.released_as}" if unit.released_as else "")
    released = unit.released or unit.kind == "core"
    choices = [suggested, unit.version, *nexts]
    if version_tuple(unit.version) > version_tuple(suggested):
        choices.insert(0, unit.version)
    choices = [v for i, v in enumerate(choices) if v not in choices[:i] and not check_new_version(unit.version, v,
                                                                                                    released)]
    return choices, reason


def nexus_level(level: str, why: str, releases: list[str]) -> tuple[str, str]:
    """Nexus's level with its suites' releases since its last version (owner, 28-10-2026): a new suite is major, a
    suite's release minor; the higher of that and its own CHANGELOG's."""
    if not releases:
        return level, why
    new = [r.removeprefix(NEW_SUITE) for r in releases if r.startswith(NEW_SUITE)]
    tags = [r for r in releases if not r.startswith(NEW_SUITE)]
    reasons = ([why] if why != "no CHANGELOG entries" else []) +         ([f"new suite{'s' if len(new) != 1 else ''} {', '.join(new)}"] if new else []) +         ([f"the suites' releases {', '.join(tags)}"] if tags else [])
    return max(level, "major" if new else "minor", key=LEVELS.index), ", ".join(reasons)


def portal_suggestion(root: Path, portal: Unit, suite: str | None = None) -> tuple[str, str]:
    """The portal's next version by semantic versioning since its last tag, and why: its own CHANGELOG entries, and
    what changed in apps.toml since that tag (an app added or removed: minor; the largest app bump it pins), as
    tools/check_manifest.py counts it. A portal never tagged is offered as it is, as step 1 offers a first release
    (owner, 28-10-2026)."""
    if portal.last_tag is None:
        return portal.version, "the first release"
    level, why = suggested_level(new_entries(root, portal))
    reason = f"{level}: {why}" + (f" since {portal.last_tag}" if portal.last_tag else "")
    old = git(root, "show", f"{portal.last_tag}:{rel(root, 'portal', 'apps.toml', suite=suite)}") \
        if portal.last_tag else None
    if old is not None:
        need, what = manifest_tools(root, suite).required_bump(old, manifest_path(root, suite).read_text(
            encoding="utf-8"))
        if need > LEVELS.index(level) + 1:
            level = LEVELS[need - 1]
            reason = f"{level}: apps.toml changed since {portal.last_tag} ({what})"
    return next_versions(_tagged_version(portal))[level], reason


def portal_text(version: str, pins: list[str], notes: str, withdrawn: list[tuple[str, str]] = ()) -> str:
    text = f"Release {version}."
    if pins:
        text += " Pins " + ", ".join(pins) + "."
    for tag, reason in withdrawn:
        text += f" Withdraws {tag}: {reason.rstrip('.')}."
    return text + (f" {notes.strip()}" if notes.strip() else "")


# --- Withdrawing a release -------------------------------------------------------------------------------------

_BLOCK = re.compile(r"^\[apps\.(?P<key>[a-z0-9-]+)\]\s*$")


def set_withdrawn(text: str, key: str, reason: str) -> str:
    """apps.toml with [apps.<key>] marked withdrawn for *reason* (after its summary line), or unmarked when
    *reason* is empty; everything else stays as it is."""
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if (m := _BLOCK.match(line)) and m["key"] == key), None)
    if start is None:
        raise ValueError(f"apps.toml has no [apps.{key}]")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("[")), len(lines))
    block = [line for line in lines[start:end] if not line.startswith("withdrawn ")]
    if reason.strip():
        at = next((i + 1 for i, line in enumerate(block) if line.startswith("summary ")), 1)
        block.insert(at, f"withdrawn = {json.dumps(reason.strip(), ensure_ascii=False)}\n")
    return "".join(lines[:start] + block + lines[end:])


def withdrawable(root: Path, units: list[Unit], suite: str | None = None) -> list[Unit]:
    """The apps a portal pins that can be withdrawn: never the required one (Bazzite Test, always installed)."""
    required = {e.key for e in manifest_tools(root, suite).manifest.load(manifest_path(root, suite)) if e.required}
    return [u for u in units if u.kind == "app" and not u.standalone and u.pinned_tag and u.key not in required]


def withdrawn_reason(root: Path, key: str, suite: str | None = None) -> str:
    entries = manifest_tools(root, suite).manifest.load(manifest_path(root, suite))
    return next((e.withdrawn for e in entries if e.key == key), "")


def withdraw(root: Path, unit: Unit, reason: str, now: datetime.datetime | None = None,
             suite: str | None = None) -> list[Path]:
    """Marks the app's pinned release withdrawn (or, with no reason, takes that back) in apps.toml, with a CHANGELOG
    entry in the app. Returns the files changed."""
    path = manifest_path(root, suite)
    paths = write_manifest(root, set_withdrawn(path.read_text(encoding="utf-8"), unit.key, reason), suite)
    text = (f"Withdrawn: {unit.pinned_tag}. {reason.strip()}" if reason.strip() else
            f"Withdrawal of {unit.pinned_tag} taken back.")
    return [*paths, add_changelog_entry(root, unit, text, now)]


def changed_withdrawals(root: Path, base: str, suite: str | None = None) -> list[tuple[str, str]]:
    """(tag, reason) of the apps withdrawn since *base*: what the portal release that follows withdraws."""
    old_text = git(root, "show", f"{base}:{rel(root, 'portal', 'apps.toml', suite=suite)}") or ""
    tools = manifest_tools(root, suite)
    old = {e.key: e.withdrawn for e in tools.manifest.parse(old_text)} if old_text else {}
    new = tools.manifest.load(manifest_path(root, suite))
    return [(e.tag, e.withdrawn) for e in new if e.withdrawn and not old.get(e.key)]


def withdraw_commands(tag: str, reason: str, now: datetime.datetime | None = None, run_script: str = "") -> str:
    """What stays the owner's: mark the GitHub release (it stays, as a pre-release, so no update check offers it),
    then the portal release that removes the app from the boards. *run_script*: a Windows suite's portal/run.ps1
    (portal_run_script()), its test on the handheld."""
    date = amsterdam_now(now).strftime("%d-%m-%Y")
    notes = f"Withdrawn on {date}: {reason.strip()} Do not install this release."
    test = [
        "# 2. Test it on the handheld with the app installed: start the portal from this checkout. It must say the",
        "#    app is not available any more and remove it. Take back undoes the mark after a test.",
        f"powershell -NoProfile -ExecutionPolicy Bypass -File {run_script} --windowed",
    ] if run_script else [
        "# 2. Test it on a BC-250 with the app installed: Test withdrawal, tab Test on this board (check-release.sh",
        "#    local). The portal must show the app as \"App not available\" and remove it. Take back undoes the",
        "#    mark after a test.",
    ]
    return "\n".join([
        "# 1. Mark the release withdrawn on GitHub (it stays; a pre-release is offered by no update check):",
        f"gh release edit {tag} --prerelease --title {shlex.quote('Withdrawn: ' + tag)} "
        f"--notes {shlex.quote(notes)}",
        "",
        *test,
        "",
        "# 3. Then a portal release (2. Pin and release Portal: Bump portal, at least a minor version): it lists the",
        "#    withdrawal in its CHANGELOG entry; commit, push and tag it as usual.",
    ])


# --- Step 2: pins and the portal -------------------------------------------------------------------------------

def pin_candidates(units: list[Unit]) -> list[Unit]:
    """Apps whose current VERSION is not pinned with a checksum yet: tagged ones and ones still to be tagged or built,
    so step 2 shows them from Apply on and Pin waits for their builds (owner, 28-10-2026)."""
    return [u for u in units if u.kind == "app" and not u.standalone
            and (u.pinned_tag != u.tag or not u.pinned_sha)]


def applied(root: Path, unit: Unit) -> bool:
    """Whether step 1's Apply already wrote this unit's release: its newest CHANGELOG entry is "Release <VERSION>."
    ("Version <VERSION>." for core) and that version is not tagged yet. Apply then has nothing new for it."""
    if unit.released:
        return False
    try:
        entries = changelog_entries((root / unit.path / "CHANGELOG").read_text(encoding="utf-8"))
    except OSError:
        return False
    if not entries:
        return False
    body = entry_body(entries[0])
    return body.startswith(f"Release {unit.version}.") or body.startswith(f"Version {unit.version}.")


def pin(root: Path, unit: Unit, sha256: str, suite: str | None = None) -> None:
    text = manifest_path(root, suite).read_text(encoding="utf-8")
    write_manifest(root, pin_app.pin(text, unit.key, unit.tag, sha256.lower()), suite)
    unit.pinned_tag, unit.pinned_sha = unit.tag, sha256.lower()


def follow_unreleased_pin(root: Path, unit: Unit, suite: str | None = None) -> bool:
    """When apps.toml pins a tag of this app that was never released, CI only accepts it while it matches VERSION:
    move the pin to the new version (sha256 empty). True when apps.toml changed; that push then needs a portal bump."""
    if unit.kind != "app" or not unit.pinned_tag or unit.pinned_tag == unit.tag \
            or unit.pinned_tag in tags_of(root, unit.key, unit.prefix):
        return False
    text = manifest_path(root, suite).read_text(encoding="utf-8")
    write_manifest(root, pin_app.pin(text, unit.key, unit.tag, ""), suite)
    unit.pinned_tag, unit.pinned_sha = unit.tag, ""
    return True


def release_asset(tag: str, root: Path = CHECKOUT) -> str:
    """What a release tag's portal downloads: <tag>.zip for a Windows suite's (tools/build_release.py), <tag>.tar.gz
    otherwise."""
    try:
        folder = nexus_suites.of_tag(tag, root)[0]
    except LookupError:
        return f"{tag}.tar.gz"
    return f"{tag}.zip" if nexus_suites.system(folder) == "windows" else f"{tag}.tar.gz"


def fetch_sha256(tag: str) -> str:
    return pin_app.fetch_sha256(tag, release_asset(tag))


def changed_pins(root: Path, base: str, suite: str | None = None) -> list[str]:
    """The pinned tags that differ from *base*: the app releases this portal release brings."""
    old_text = git(root, "show", f"{base}:{rel(root, 'portal', 'apps.toml', suite=suite)}") or ""
    tools = manifest_tools(root, suite)
    old = {e.key: e.tag for e in tools.manifest.parse(old_text)} if old_text else {}
    new = tools.manifest.load(manifest_path(root, suite))
    return [e.tag for e in new if old.get(e.key) != e.tag]


def portal_minimum(root: Path, base: str, portal_version: str, suite: str | None = None) -> tuple[str, str]:
    """The lowest portal version CI accepts (tools/check_manifest.py), and why: apps.toml against the last portal
    release (its tag; a version not tagged yet may still change what it pins), or against *base* (the last push)
    while there is no portal tag; ("", "") when apps.toml is unchanged. That release's version is the starting
    point."""
    prefix = tag_prefix(root, suite)
    tools = manifest_tools(root, suite)
    tags = tags_of(root, "portal", prefix)
    ref = tags[-1] if tags else base
    old_text = git(root, "show", f"{ref}:{rel(root, 'portal', 'apps.toml', suite=suite)}")
    new_text = manifest_path(root, suite).read_text(encoding="utf-8")
    if old_text is None:
        return "", ""
    need, why = tools.required_bump(old_text, new_text)
    if need <= 0:
        return "", why
    start = ref[len(f"{prefix}portal-v"):] if tags else \
        (git(root, "show", f"{base}:{rel(root, 'portal', 'VERSION', suite=suite)}") or portal_version).strip()
    bumped = next_versions(start)[tools.LEVELS[need]]
    if version_tuple(portal_version) > version_tuple(start) and \
            tools.bump_level(start, portal_version) >= need:
        bumped = portal_version
    return bumped, why


# --- Run from the checkout ------------------------------------------------------------------------------------

@dataclass
class Launch:
    """One window of an app, as `python -m <module>` in the checkout: how an app is tried before its release."""
    key: str                            # the app folder under apps/
    module: str                         # "upscaler"
    name: str                           # its APP_NAME, else the module
    folder: Path                        # where the module runs from: its package's parent
    version: str
    changes_board: bool                 # as portal/apps.toml marks the app (standalone apps: False)
    icon: Path | None
    args: tuple[str, ...] = ()          # after `python -m <module>`
    url: str = ""                       # a server: the page to open once it answers
    app_id: str = ""                    # an app that runs once per user: a second launch only shows the first
    log_stem: str = ""                  # its log's name, when the module does not tell it apart (two wikis)
    note: str = ""                      # said once it started (a wiki on the network: its addresses)

    @property
    def label(self) -> str:
        return f"{self.name} {self.version}".strip()

    @property
    def log_name(self) -> str:
        return f"{self.log_stem or self.module}.log"


_CONSTANT = re.compile(r'^(APP_NAME|APP_ID)\s*=\s*"([^"]+)"', re.M)


def launch_targets(root: Path = CHECKOUT, suite: str | None = None) -> list[Launch]:
    """Every app window of the suite in the checkout: each package with a __main__.py (one or two levels below the
    app folder, tests left out). The checkout-only apps, like this one, are not listed."""
    try:
        tools = manifest_tools(root, suite)
        board = {e.key: getattr(e, "changes_board", False) for e in tools.manifest.load(manifest_path(root, suite))}
    except (OSError, tools.manifest.ManifestError):
        board = {}
    found = []
    for app in sorted((suite_dir(root, suite) / "apps").iterdir()):
        if not (app / "VERSION").is_file() or (app / CHECKOUT_ONLY).is_file():
            continue
        version = (app / "VERSION").read_text(encoding="utf-8").strip()
        mains = sorted(p for p in (*app.glob("*/__main__.py"), *app.glob("*/*/__main__.py"))
                       if "tests" not in p.relative_to(app).parts)
        for main in mains:
            package = main.parent
            try:
                init = (package / "__init__.py").read_text(encoding="utf-8")
            except OSError:
                init = ""
            consts = dict(_CONSTANT.findall(init))
            # The icon: the picture its __init__ names (its LOGO_PATH), else the one named after APP_ID, else the
            # first that is not a numbered screenshot.
            images = [p for folder in (app / "images", package.parent / "images")
                      for p in sorted(folder.glob("*.*")) if p.suffix in (".webp", ".png")]
            named = [p for p in images if f'"{p.name}"' in init] + [p for p in images if p.stem == consts.get("APP_ID")]
            icon = (named or [p for p in images if not p.stem[:1].isdigit()] or [None])[0]
            found.append(Launch(app.name, package.name, consts.get("APP_NAME", package.name), package.parent, version,
                                board.get(app.name, False), icon))
    return found


def portal_target(root: Path = CHECKOUT, suite: str | None = None) -> Launch | None:
    """The suite's portal, started from the checkout as `python -m <its package>` in portal/ (bc250_portal, the
    Windows Portable Suite's portable_portal: owner, 29-10-2026, a Windows suite's portal had no local test): it
    takes its apps from the checkout, as it does when it runs from one. None when the suite has no portal window."""
    folder = suite_dir(root, suite) / "portal"
    mains = sorted(p for p in folder.glob("*/__main__.py") if p.parent.name != "tests")
    if not mains:
        return None
    package = mains[0].parent
    try:
        version = (folder / "VERSION").read_text(encoding="utf-8").strip()
        consts = dict(_CONSTANT.findall((package / "__init__.py").read_text(encoding="utf-8")))
    except OSError:
        return None
    icon = wiki_icon(suite_dir(root, suite))           # images/<suite folder>-suite.webp
    return Launch("portal", package.name, consts.get("APP_NAME", package.name), folder, version, False, icon,
                  app_id=consts.get("APP_ID", ""))


def installer_tests_target(root: Path = CHECKOUT, suite: str | None = None) -> Launch | None:
    """The suite's installer tests window (tools/installer-tests/gui, BC-250 Installer Tests), started from the
    checkout as its run.sh does. None when the suite has no such window."""
    folder = suite_dir(root, suite) / "tools" / "installer-tests" / "gui"
    try:
        version = (folder / "VERSION").read_text(encoding="utf-8").strip()
        consts = dict(_CONSTANT.findall((folder / "installer_test_gui" / "__init__.py").read_text(encoding="utf-8")))
    except OSError:
        return None
    icon = folder / "images" / "bc250-installer-test-gui.webp"
    return Launch("installer-tests", "installer_test_gui", consts.get("APP_NAME", "installer_test_gui"), folder,
                  version, False, icon if icon.is_file() else None)


DOCS_HOST = "127.0.0.1"
DOCS_PORT = 8765                        # not mkdocs' default 8000, which other dev servers like to take
NETWORK_HOST = "0.0.0.0"                # every address of this computer, for the other devices
NETWORK_PORT = 8785                     # ports of their own, so a wiki can be served both ways at once


def network_addresses() -> list[str]:
    """This computer's IPv4 addresses that other devices can reach (no loopback), the one with the default route
    first. Read from the system; nothing is sent."""
    import socket
    found = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))         # TEST-NET-1: a UDP connect picks the route, sends nothing
            found.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        found += [info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        pass
    return [a for i, a in enumerate(found) if not a.startswith("127.") and a != "0.0.0.0" and a not in found[:i]]


def wiki_icon(folder: Path) -> Path | None:
    """The icon of the wiki in *folder*: its suite's portal icon (bc250-bazzite/portal/images/bc250-bazzite-suite.webp),
    else its own drawing at 256 px (nexus/images/nexus-256.png); None without either."""
    for icon in (folder / "portal" / "images" / f"{folder.name}-suite.webp", folder / "images" / f"{folder.name}-256.png"):
        if icon.is_file():
            return icon
    return None


def suite_name(root: Path, suite: str | None = None) -> str:
    """The suite's name, as its portal calls itself (APP_NAME in portal/<package>/__init__.py: BC250 Bazzite Suite,
    Windows Portable Suite); its folder's name without one."""
    folder = suite_dir(root, suite)
    for init in sorted((folder / "portal").glob("*/__init__.py")):
        found = _CONSTANT.search(init.read_text(encoding="utf-8"))
        while found and found.group(1) != "APP_NAME":
            found = _CONSTANT.search(init.read_text(encoding="utf-8"), found.end())
        if found:
            return found.group(2)
    return folder.name


def suite_icon(root: Path, suite: str | None = None) -> Path | None:
    """The suite's icon: its portal's (wiki_icon()), else its own drawing (windows-portable/icons/
    windows-portable-256.png) for a suite whose portal has no images yet; None without either."""
    folder = suite_dir(root, suite)
    icon = wiki_icon(folder)
    if icon is not None:
        return icon
    return next((p for size in (256, 128) if (p := folder / "icons" / f"{folder.name}-{size}.png").is_file()), None)


def wiki_configs(root: Path = CHECKOUT) -> list[Path]:
    """Each wiki in the checkout: mkdocs.yml at the root (none since the suites moved into their folders), then one
    in a folder directly below it (bc250-bazzite/, nexus/, and a new suite's), by folder name."""
    return [p for p in (root / "mkdocs.yml", *sorted(root.glob("*/mkdocs.yml"))) if p.is_file()]


def docs_targets(root: Path = CHECKOUT, network: bool = False,
                 addresses: list[str] | None = None, suite: str | None = None) -> list[Launch]:
    """Each wiki, served from the checkout with `mkdocs serve` (the dev venv has it), each on a port of its own: it
    rebuilds on every save, and its page opens with the design panel. The page is under the path of site_url, as on
    GitHub Pages. With *network* it is served on every address of this computer, for the other devices on the
    network; the browser here still opens it at 127.0.0.1. With *suite*, that suite's wiki and the ones that are no
    suite's (the Nexus page), never another suite's (owner, 29-10-2026: the BC250 wiki showed under the Windows
    suite); a wiki keeps its port whichever suite is ticked."""
    others = {name for name in suites(root) if name != suite} if suite else set()
    found = []
    for number, config in enumerate(wiki_configs(root)):
        if config.parent.name in others and config.parent != root:
            continue
        text = config.read_text(encoding="utf-8")
        name = re.search(r"^site_name:\s*(.+?)\s*$", text, re.M)
        site = re.search(r"^site_url:\s*(\S+)", text, re.M)
        path = urlparse(site[1]).path.strip("/") if site else ""
        path = f"/{path}/" if path else "/"
        port = (NETWORK_PORT if network else DOCS_PORT) + number
        folder = config.parent.relative_to(root).as_posix()
        where = "network" if network else "local"
        note = ""
        if network:
            reach = [f"http://{a}:{port}{path}" for a in (network_addresses() if addresses is None else addresses)]
            note = ("On the other devices: " + ", ".join(reach)) if reach else \
                "This computer has no network address the other devices can reach."
        found.append(Launch("docs" if folder == "." else f"docs-{folder}", "mkdocs",
                            f"{name[1] if name else folder} wiki ({where})", root, "", False, wiki_icon(config.parent),
                            ("serve", "-f", config.relative_to(root).as_posix(),
                             "--dev-addr", f"{NETWORK_HOST if network else DOCS_HOST}:{port}"),
                            f"http://{DOCS_HOST}:{port}{path}?design",
                            log_stem=f"mkdocs-{'root' if folder == '.' else folder}-{where}", note=note))
    return found


def launch_command(root: Path, target: Launch, python: str = sys.executable) -> tuple[list[str], dict[str, str]]:
    """The command and environment that start *target* from the checkout: the dev venv's python, with the
    checkout's core on the path as run.sh does it (a release bundles core instead)."""
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(root / "core"), env.get("PYTHONPATH"))))
    return [python, "-m", target.module, *target.args], env


# --- GitHub Actions: did the push build? -----------------------------------------------------------------------

RUNS_URL = "https://api.github.com/repos/{repo}/actions/runs?per_page=30"
ACTIONS_URL = "{repo_url}/actions"
OK_CONCLUSIONS = ("success", "skipped", "neutral")


@dataclass(frozen=True)
class BuildRun:
    """One workflow run on GitHub: CI, Release or Manual, on a branch or a tag."""
    workflow: str                       # "CI"
    ref: str                            # "main", "governor-v0.1.1"
    status: str                         # "queued", "in_progress", "completed", ...
    conclusion: str                     # "success", "failure", "canceled", ...; "" until it is completed
    url: str                            # its page; also what tells two runs apart
    sha: str
    title: str                          # the commit message's first line
    jobs_url: str = ""                  # its jobs on GitHub's API (fetch_jobs)
    started: float = 0.0                # seconds since the epoch; 0 when GitHub does not say
    file: str = ""                      # its workflow's file: "ci.yml", "ci-windows-portable.yml"

    @property
    def done(self) -> bool:
        return self.status == "completed"

    @property
    def passed(self) -> bool:
        return self.done and self.conclusion in OK_CONCLUSIONS

    @property
    def outcome(self) -> str:
        return ("passed" if self.passed else self.conclusion.replace("_", " ") or "failed") if self.done \
            else self.status.replace("_", " ")

    @property
    def label(self) -> str:
        return f"{self.workflow} on {self.ref}"


def repo_slug() -> str:
    return pin_app.REPO_URL.removeprefix("https://github.com/")


def parse_runs(data: object) -> list[BuildRun]:
    runs = data.get("workflow_runs", []) if isinstance(data, dict) else []
    return [BuildRun(str(r.get("name") or ""), str(r.get("head_branch") or ""), str(r.get("status") or ""),
                     str(r.get("conclusion") or ""), str(r.get("html_url") or ""), str(r.get("head_sha") or ""),
                     str(r.get("display_title") or ""), str(r.get("jobs_url") or ""),
                     epoch(r.get("run_started_at")), str(r.get("path") or "").split("@")[0].rsplit("/", 1)[-1])
            for r in runs if isinstance(r, dict)]


def epoch(text: object) -> float:
    """GitHub's time ("2026-10-28T09:12:03Z") in seconds since the epoch; 0 without one."""
    try:
        return datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


GH_FALLBACK = "/home/linuxbrew/.linuxbrew/bin/gh"   # Homebrew's gh on Bazzite: not on PATH when started from the menu


@dataclass(frozen=True)
class RateInfo:
    """GitHub's hourly limit as its last answer reported it (the X-RateLimit headers, also on unchanged answers)."""
    limit: int
    remaining: int
    reset: float                        # seconds since the epoch
    signed_in: bool

    @classmethod
    def from_headers(cls, headers, signed_in: bool) -> "RateInfo | None":
        try:
            return cls(int(headers.get("X-RateLimit-Limit")), int(headers.get("X-RateLimit-Remaining")),
                       float(headers.get("X-RateLimit-Reset")), signed_in)
        except (TypeError, ValueError, AttributeError):
            return None

    @property
    def until(self) -> str:
        return time.strftime("%H:%M", time.localtime(self.reset))

    @property
    def text(self) -> str:
        who = "signed in" if self.signed_in else "not signed in"
        return f"GitHub API: {self.remaining:,} of {self.limit:,} left until {self.until}, {who}"


class RateLimited(OSError):
    """GitHub refuses until *reset* (seconds since the epoch): the hour's requests are used up."""

    def __init__(self, reset: float, signed_in: bool, rate: RateInfo | None = None):
        super().__init__(f"GitHub's hourly limit is used up until {time.strftime('%H:%M', time.localtime(reset))}")
        self.reset = reset
        self.signed_in = signed_in
        self.rate = rate or RateInfo(60 if not signed_in else 5000, 0, reset, signed_in)


_token: str | None = None               # the token found once per run; "" when there is none
_token_lock = threading.Lock()          # the checks run in worker threads: one asks gh, the others wait for it


def github_token(run=subprocess.run) -> str:
    """GITHUB_TOKEN or GH_TOKEN, else the token of a gh login (gh auth token); "" without one. With a token GitHub
    allows 5,000 requests an hour instead of 60. It is only sent to GitHub's API and never stored here."""
    global _token
    with _token_lock:
        if _token is None:
            token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
            gh = shutil.which("gh") or (GH_FALLBACK if os.access(GH_FALLBACK, os.X_OK) else "")
            if not token and gh:
                try:
                    out = run([gh, "auth", "token"], capture_output=True, text=True, timeout=10)
                    token = out.stdout.strip() if out.returncode == 0 else ""
                except (OSError, subprocess.SubprocessError):
                    token = ""
            _token = token              # only the finished answer: never "" while gh is still being asked
        return _token


def token_warning(token: str) -> str:
    """What push and tag say about the GitHub token on this machine: a gh login (gho_) or a classic token (ghp_)
    reaches every repository of the account, a fine-grained one (github_pat_) only those it names. "" when it is
    fine-grained or there is none."""
    if not token or token.startswith("github_pat_"):
        return ""
    return ("The GitHub token on this machine (a gh login or a classic token) reaches every repository of your "
            "account, not only this one. A fine-grained token for this repository only limits what someone with "
            "this account can do: github.com, Settings, Developer settings, Fine-grained tokens.")


def github_get(url: str, etag: str = "") -> tuple[object | None, str, RateInfo | None]:
    """GitHub's API answer at *url* (parsed JSON), the ETag to send next time and GitHub's hourly limit as it
    stands; the answer None when nothing changed since *etag*. GitHub answers that with 304, which does not count
    against the limit (60 requests without a token, 5,000 with the token of a gh login). Raises RateLimited when
    the limit is used up, OSError offline."""
    global _token
    token = github_token()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "nexus-releases"}
    if etag:
        headers["If-None-Match"] = etag
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return (json.load(response), response.headers.get("ETag", ""),
                    RateInfo.from_headers(response.headers, bool(token)))
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return None, etag, RateInfo.from_headers(exc.headers, bool(token))
        if exc.code == 401 and token:            # an expired or revoked login: go on without it
            _token = ""
            return github_get(url, etag)
        if exc.code in (403, 429) and exc.headers.get("X-RateLimit-Remaining") == "0":
            raise RateLimited(float(exc.headers.get("X-RateLimit-Reset") or time.time() + 3600), bool(token),
                              RateInfo.from_headers(exc.headers, bool(token))) from exc
        raise


def fetch_runs(etag: str = "") -> tuple[list[BuildRun] | None, str, RateInfo | None]:
    """The newest workflow runs (newest first), the ETag to send next time and GitHub's hourly limit as it stands;
    runs None when nothing changed since *etag* (github_get)."""
    data, etag, rate = github_get(RUNS_URL.format(repo=repo_slug()), etag)
    return (None if data is None else parse_runs(data)), etag, rate


def latest_push(runs: list[BuildRun]) -> list[BuildRun]:
    """The runs of the newest commit: a push and its tags start CI, Release and Manual on the same commit."""
    return [r for r in runs if r.sha == runs[0].sha] if runs else []


def build_state(runs: list[BuildRun]) -> str:
    """"running" while one of *runs* has not finished, else "failed" when one did not pass, else "passed"; ""
    without runs."""
    if not runs:
        return ""
    if not all(r.done for r in runs):
        return "running"
    return "passed" if all(r.passed for r in runs) else "failed"


def just_finished(before: dict[str, BuildRun], runs: list[BuildRun]) -> list[BuildRun]:
    """The runs that were running at the last look (*before*, by url) and have finished now."""
    return [r for r in runs if r.done and r.url in before and not before[r.url].done]


def is_release(run: BuildRun) -> bool:
    """A suite's release workflow: release.yml ("Release"), or release-<suite>.yml for a suite with a tag prefix
    ("Release Windows Portable"); by its name when GitHub gives no file."""
    if run.file:
        return run.file == "release.yml" or (run.file.startswith("release-") and run.file.endswith(".yml"))
    return run.workflow == "Release" or run.workflow.startswith("Release ")


def release_run(runs: list[BuildRun], tag: str) -> BuildRun | None:
    """The newest release run on *tag* (release.yml or the suite's release-<suite>.yml, which builds and publishes
    its release); None while GitHub shows none: the tag is not pushed yet, or the run is not among the newest ones
    any more."""
    return next((r for r in runs if is_release(r) and r.ref == tag), None)


def release_state(runs: list[BuildRun], tag: str) -> str:
    """"running" while release.yml builds *tag*, "passed" once its tarball is published, "failed" when it did not
    build it, "" while GitHub shows no run on the tag."""
    run = release_run(runs, tag)
    return build_state([run]) if run else ""


def finished_releases(announced: set[str], runs: list[BuildRun], tags: list[str]) -> list[BuildRun]:
    """The Release runs of *tags* (the releases the window waits for) that have finished and were not announced
    yet (*announced*: their urls). Seen running before or not: a run that starts and ends between two looks, or
    before the first, counts too, so a release that is ready to pin is announced once, whenever it is seen."""
    found = []
    for tag in tags:
        run = release_run(runs, tag)
        if run and run.done and run.url not in announced:
            found.append(run)
    return found


# --- GitHub Actions: the jobs of a run and the step each is at, for the ticker -----------------------------------

@dataclass(frozen=True)
class BuildJob:
    """One job of a workflow run (a CI matrix entry, the release build) and the step it is at."""
    name: str                           # "pytest (core)"
    status: str                         # "queued", "in_progress", "completed"
    conclusion: str                     # "success", "failure", ...; "" until it is completed
    url: str                            # its page, with its log
    step: str = ""                      # the step that runs, else the first that failed, else the next; ""
    step_number: int = 0                # its place among the job's steps, from 1; 0 without one
    steps: int = 0

    @property
    def done(self) -> bool:
        return self.status == "completed"

    @property
    def passed(self) -> bool:
        return self.done and self.conclusion in OK_CONCLUSIONS

    @property
    def outcome(self) -> str:
        return ("passed" if self.passed else self.conclusion.replace("_", " ") or "failed") if self.done \
            else self.status.replace("_", " ")


def current_step(steps: list[dict]) -> tuple[str, int]:
    """The step a job is at, with its place from 1: the one running, else the first that did not pass (a failed
    job's), else the first not finished (between two steps); ("", 0) without one."""
    for pick in (lambda st: st.get("status") == "in_progress",
                 lambda st: st.get("status") == "completed" and (st.get("conclusion") or "") not in OK_CONCLUSIONS,
                 lambda st: st.get("status") != "completed"):
        for i, st in enumerate(steps):
            if pick(st):
                return str(st.get("name") or ""), i + 1
    return "", 0


def parse_jobs(data: object) -> list[BuildJob]:
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    found = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        steps = [st for st in job.get("steps") or [] if isinstance(st, dict)]
        step, number = current_step(steps)
        found.append(BuildJob(str(job.get("name") or ""), str(job.get("status") or ""),
                              str(job.get("conclusion") or ""), str(job.get("html_url") or ""), step, number,
                              len(steps)))
    return found


def fetch_jobs(url: str, etag: str = "") -> tuple[list[BuildJob] | None, str, RateInfo | None]:
    """The jobs of a run (its BuildRun.jobs_url) with the step each is at, read as fetch_runs reads the runs."""
    data, etag, rate = github_get(f"{url}?per_page=100", etag)
    return (None if data is None else parse_jobs(data)), etag, rate


def elapsed(seconds: float) -> str:
    """2:14, or 1:02:03 past an hour."""
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60}:{rest % 60:02d}"


def suite_workflows(root: Path, suite: str | None = None) -> set[str]:
    """The workflow files that are the suite's own: ci.yml and release.yml for the suite without a tag prefix,
    ci-<suite>.yml and release-<suite>.yml for one with (each suite's CI and releases stand apart, owner
    27-10-2026)."""
    if not tag_prefix(root, suite):
        return {"ci.yml", "release.yml"}
    name = suite_dir(root, suite).name
    return {f"ci-{name}.yml", f"release-{name}.yml"}


def other_suites_workflows(root: Path, suite: str | None = None) -> set[str]:
    """The workflow files of every suite but *suite*: the ticker leaves their runs out, so it follows the suite
    being released and Nexus's own workflows (CI Nexus, Manual)."""
    mine = suite_workflows(root, suite)
    return {f for name in suites(root) if name != suite for f in suite_workflows(root, name)} - mine


def ticker_runs(runs: list[BuildRun]) -> list[BuildRun]:
    """The ticker's runs in its order: those running, then those that failed, then those that passed."""
    return sorted(runs, key=lambda r: 0 if not r.done else 2 if r.passed else 1)


def run_line(run: BuildRun, jobs: list[BuildJob] | None, now: float) -> str:
    """Where one run stands, for the ticker: "CI on main: 3 of 8 jobs done · pytest (core): Run tests (4/7) ·
    2:14"; a failed run names its job and step; without its jobs (not read), the run's own state."""
    if run.passed:
        return f"{run.label}: passed"
    failed = [j for j in jobs or [] if j.done and not j.passed]
    if run.done:
        where = (f" in {failed[0].name}" + (f", step {failed[0].step}" if failed[0].step else "")) if failed else ""
        return f"{run.label}: {run.outcome}{where}"
    parts = [f"{run.label}: {run.outcome}"]
    if jobs:
        parts = [f"{run.label}: {sum(j.done for j in jobs)} of {len(jobs)} jobs done"]
        if failed:
            parts.append(f"{len(failed)} failed")
        parts += [f"{j.name}: {j.step} ({j.step_number}/{j.steps})" if j.step else j.name
                  for j in jobs if j.status == "in_progress"]
    if run.started:
        parts.append(elapsed(now - run.started))
    return " · ".join(parts)


def ticker_line(runs: list[BuildRun], jobs: dict[str, list[BuildJob]], now: float) -> str:
    """The ticker: every run of the newest push, the running ones first (run_line)."""
    return "   |   ".join(run_line(r, jobs.get(r.url), now) for r in ticker_runs(runs))


def ticker_details(runs: list[BuildRun], jobs: dict[str, list[BuildJob]], now: float) -> str:
    """The ticker's tooltip: the commit, then each run with every job and the step it is at."""
    if not runs:
        return ""
    lines = [f"{runs[0].sha[:7]} {runs[0].title}"]
    for run in ticker_runs(runs):
        lines += ["", f"{run.label}: {run.outcome}"
                  + (f", {elapsed(now - run.started)}" if run.started and not run.done else "")]
        for job in jobs.get(run.url) or []:
            step = f", step {job.step_number} of {job.steps}: {job.step}" if job.step and not job.passed else ""
            lines.append(f"    {job.name}: {job.outcome}{step}")
    return "\n".join(lines)


def ticker_target(runs: list[BuildRun], jobs: dict[str, list[BuildJob]]) -> str:
    """What a click on the ticker opens: the job that runs, else the one that failed, else the run that runs or
    failed, else the newest run; "" without runs."""
    ordered = ticker_runs(runs)
    for run in ordered:
        if run.passed:
            break
        listed = jobs.get(run.url) or []
        pick = next((j for j in listed if j.status == "in_progress"), None) or \
            next((j for j in listed if j.done and not j.passed), None)
        return pick.url if pick and pick.url else run.url
    return ordered[0].url if ordered else ""


# --- GitHub issues: the open ones, closed once handled -----------------------------------------------------------

ISSUES_URL = "https://api.github.com/repos/{repo}/issues?state=open&per_page=100"


@dataclass(frozen=True)
class Issue:
    """One open issue on GitHub: the weekly Upstream review or Backlog review, or one someone opened."""
    number: int
    title: str
    url: str
    updated: str                        # "2026-10-20", the day of its last change

    @property
    def label(self) -> str:
        return f"#{self.number} {self.title} (updated {self.updated})"


def parse_issues(data: object) -> list[Issue]:
    """The issues of GitHub's answer, without the pull requests it lists among them."""
    return [Issue(int(i.get("number") or 0), str(i.get("title") or ""), str(i.get("html_url") or ""),
                  str(i.get("updated_at") or "")[:10])
            for i in data if isinstance(i, dict) and "pull_request" not in i] if isinstance(data, list) else []


def fetch_open_issues() -> list[Issue]:
    """The repository's open issues, newest first. Raises OSError offline, urllib.error.HTTPError on GitHub's
    refusal (its hourly limit)."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "nexus-releases"}
    token = github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(ISSUES_URL.format(repo=repo_slug()), headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        return parse_issues(json.load(response))


def close_issues_command(numbers: list[int], comment: str = "") -> str:
    """gh issue close for each of *numbers*, with *comment* on each when there is one; it needs a gh login."""
    note = f" --comment {shlex.quote(comment.strip())}" if comment.strip() else ""
    return " && ".join(f"gh issue close {n} --repo {repo_slug()}{note}" for n in numbers)


# --- GitHub's own status: is GitHub up? ------------------------------------------------------------------------

STATUS_PAGE = "https://www.githubstatus.com/"
STATUS_URL = STATUS_PAGE + "api/v2/summary.json"


@dataclass(frozen=True)
class GitHubStatus:
    """What githubstatus.com reports: up when every part of GitHub works as it should."""
    indicator: str                      # "none", "minor", "major", "critical" (Statuspage's)
    description: str                    # "All Systems Operational", "Partially Degraded Service"
    affected: tuple[str, ...] = ()      # "Actions: degraded performance"
    incidents: tuple[str, ...] = ()     # the names of the open incidents

    @property
    def up(self) -> bool:
        return self.indicator == "none"


def parse_github_status(data: object) -> GitHubStatus:
    data = data if isinstance(data, dict) else {}
    status = data.get("status") if isinstance(data.get("status"), dict) else {}
    affected = tuple(f"{c.get('name')}: {str(c.get('status')).replace('_', ' ')}" for c in data.get("components") or []
                     if isinstance(c, dict) and c.get("status") not in (None, "operational"))
    incidents = tuple(str(i.get("name")) for i in data.get("incidents") or [] if isinstance(i, dict) and i.get("name"))
    return GitHubStatus(str(status.get("indicator") or ""), str(status.get("description") or ""), affected, incidents)


def fetch_github_status() -> GitHubStatus:
    """githubstatus.com's summary (a public page: no token, no limit to count). Raises OSError offline."""
    request = urllib.request.Request(STATUS_URL, headers={"User-Agent": "nexus-releases"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return parse_github_status(json.load(response))


# --- Claude usage: the tokens Claude Code used, from its transcripts on this machine ------------------------------

CLAUDE_USAGE_PAGE = "https://claude.ai/settings/usage"
CLAUDE_WINDOW = 5 * 3600                # Claude's usage limits count in windows of 5 hours


@dataclass(frozen=True)
class ClaudeUsage:
    """The tokens of Claude Code's answers since *since* (seconds since the epoch), by kind and by model."""
    since: float
    messages: int = 0
    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0
    models: tuple[tuple[str, int], ...] = ()     # (model, tokens), the most first

    @property
    def total(self) -> int:
        return self.input + self.output + self.cache_write + self.cache_read


def claude_dir() -> Path:
    """Claude Code's folder: CLAUDE_CONFIG_DIR, else ~/.claude (on Windows too)."""
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def read_claude_answers(folder: Path, since: float) -> list[tuple[float, str, dict]]:
    """Each answer of Claude since *since* in the transcripts under *folder*/projects (subagents' included), once:
    (time, model, usage). An answer of several parts repeats its usage on every part, so it counts by its ids.
    Only files written since then are read; a line that is not an answer, or not JSON, is skipped."""
    seen: set[tuple[str, str]] = set()
    answers = []
    for path in (folder / "projects").rglob("*.jsonl"):
        try:
            if path.stat().st_mtime < since:
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if '"usage"' not in line:
                continue
            try:
                entry = json.loads(line)
                message = entry["message"]
                usage = message["usage"]
                at = datetime.datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).timestamp()
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            key = (str(message.get("id")), str(entry.get("requestId")))
            if entry.get("type") != "assistant" or not isinstance(usage, dict) or at < since or key in seen:
                continue
            seen.add(key)
            answers.append((at, str(message.get("model") or "unknown"), usage))
    return answers


def sum_claude_usage(answers: list[tuple[float, str, dict]], since: float) -> ClaudeUsage:
    def count(usage: dict, name: str) -> int:
        value = usage.get(name)
        return value if isinstance(value, int) else 0

    kinds = {"input": "input_tokens", "output": "output_tokens", "cache_write": "cache_creation_input_tokens",
             "cache_read": "cache_read_input_tokens"}
    totals = dict.fromkeys(kinds, 0)
    models: dict[str, int] = {}
    messages = 0
    for at, model, usage in answers:
        if at < since or model == "<synthetic>":         # Claude Code's own notes, not answers of the model
            continue
        messages += 1
        for kind, name in kinds.items():
            totals[kind] += count(usage, name)
        models[model] = models.get(model, 0) + sum(count(usage, name) for name in kinds.values())
    ranked = tuple(sorted(models.items(), key=lambda m: -m[1]))
    return ClaudeUsage(since, messages, models=ranked, **totals)


def fetch_claude_usage(now: float | None = None, folder: Path | None = None) -> tuple[ClaudeUsage, ClaudeUsage] | None:
    """Claude Code's tokens today (since local midnight) and in the last 5 hours; None without Claude Code here."""
    folder = claude_dir() if folder is None else folder
    if not (folder / "projects").is_dir():
        return None
    now = time.time() if now is None else now
    midnight = datetime.datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    recent = now - CLAUDE_WINDOW
    answers = read_claude_answers(folder, min(midnight, recent))
    return sum_claude_usage(answers, midnight), sum_claude_usage(answers, recent)


def short_count(n: int) -> str:
    """12,345 as 12.3k, 4,567,890 as 4.6M: for a pill."""
    for size, unit in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "k")):
        if n >= size:
            return f"{n / size:.1f}{unit}"
    return str(n)


# --- The commands for the owner --------------------------------------------------------------------------------

def push_command(linux: bool | None = None) -> str:
    """git push, after CI's jobs passed here (tools/ci-local.sh runs on Linux only)."""
    if linux is None:
        linux = sys.platform.startswith("linux")
    return f"{CI_LOCAL} && git push" if linux else "git push"


def pull_command() -> str:
    """The git pull button: what was pushed from the other machine, with this checkout's own commits put on top of
    it (--rebase: no merge commit) and its changes not committed yet kept as they are (--autostash)."""
    return "git pull --rebase --autostash"


def behind(root: Path, base: str) -> int:
    """How many commits *base* (the remote's main, as git last fetched it) has that HEAD does not: pushed from the
    other machine. 0 when unknown."""
    out = (git(root, "rev-list", "--count", f"HEAD..{base}") or "0").strip()
    return int(out) if out.isdigit() else 0


def add_command() -> str:
    """The git add button: everything, the exec bits CI checks, and what is staged now."""
    return "git add -A && tools/fix-modes.sh && git status --short"


def tag_command(tags: list[str]) -> str:
    """The git tag button: tag-release.sh, which tags only a pushed HEAD that CI passed, and pushes the tags."""
    return f"{TAG_SCRIPT} {' '.join(tags)}"


def commit_command(message: str, base: str, amend: bool = False, python: str = "python3",
                   manifests: list[str] | None = None, versions: list[str] | None = None) -> str:
    """The git commit button: the version check and the suites' manifest checks first (CI's quick ones; *manifests*:
    their paths, manifest_checks(), every suite's of the checkout by default; *versions*: version_checks(), every
    suite by default), the commit only when they pass. *amend*: the staged changes join HEAD, with its message."""
    checks = " && ".join([*(f"{python} {check}" for check in (versions or [VERSIONS_CHECK])),
                          *(f"{python} {check} --base {shlex.quote(base)}" for check in
                            (manifest_checks(CHECKOUT) if manifests is None else manifests))])
    commit = "git commit --amend --no-edit" if amend else f"git commit -m {shlex.quote(message)}"
    return f"{checks} && {commit}"


def commit_message(text: str) -> tuple[str, bool]:
    """The commit a step's commands make: its message, or ("", True) when they amend HEAD; ("", False) for none."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("git commit --amend"):
            return "", True
        if line.startswith("git commit -m "):
            words = shlex.split(line, comments=True)
            return words[3] if len(words) > 3 else "", False
    return "", False


def git_state(root: Path, base: str) -> tuple[bool, bool, int]:
    """For the git buttons: whether something is not staged (changed or new), whether something is staged, and how
    many commits HEAD has that *base* (the last push) does not."""
    status = git(root, "status", "--porcelain") or ""
    lines = [line for line in status.splitlines() if len(line) > 2]
    unstaged = any(line[1] != " " for line in lines)
    staged = any(line[0] not in " ?" for line in lines)
    ahead = (git(root, "rev-list", "--count", f"{base}..HEAD") or "0").strip()
    return unstaged, staged, int(ahead) if ahead.isdigit() else 0


def app_commands(tags: list[str], linux: bool | None = None, portal: str = "", amend: bool = False) -> str:
    """The commands after step 1's Apply. *portal*: the portal version this push also needs (apps.toml changed since
    the last portal release), which comes first: committed without it, the push fails CI. *amend*: HEAD is the release commit
    of these tags and is not pushed yet (the bump came after the commit), so the bump joins it."""
    lines = [f"# First: step 2's Bump portal (portal {portal}), or CI fails on this push; then:"] if portal else []
    lines += ["git add -A && tools/fix-modes.sh"]
    lines += ["git commit --amend --no-edit     # HEAD is the release commit, not pushed yet: the bump joins it"] \
        if amend else [f'git commit -m "Release {", ".join(tags)}"']
    lines += [push_command(linux)]
    lines += [f"{TAG_SCRIPT} {' '.join(tags)}     # refuses until the bump is committed and pushed"]
    lines += ["# when GitHub has built the releases: step 2 (pin and portal)"]
    return "\n".join(lines)


NEXUS_INDEX_NOTE = ("# Nexus {version}: once this push is on main, GitHub's Latest release becomes nexus-v{version} "
                    "(nexus-index.yml); nothing to tag")


def nexus_commands(version: str, linux: bool | None = None) -> str:
    """The commands after step 1's Apply of Nexus's version alone: commit and push; the index workflow publishes
    the Latest release as nexus-v<version> when the push changes VERSION."""
    return "\n".join(["git add -A && tools/fix-modes.sh", f'git commit -m "Release {NEXUS}-v{version}"',
                      push_command(linux), NEXUS_INDEX_NOTE.format(version=version)])


def untagged_releases(units: list[Unit]) -> list[str]:
    """The tags step 1 still has to push: every portal app whose VERSION has no tag. While there is one, the portal
    cannot be released (release.yml checks every pinned tag), so a portal bump made now goes into step 1's push."""
    return [u.tag for u in units if u.kind == "app" and not u.standalone and not u.released]


def unpushed_release_commit(root: Path, base: str) -> str:
    """HEAD's subject when it is a release commit ("Release ...") that *base* does not have yet: the commit step 1's
    bump can still be amended into. "" otherwise."""
    if git(root, "merge-base", "--is-ancestor", "HEAD", base) is not None:
        return ""
    subject = (git(root, "log", "-1", "--format=%s") or "").strip()
    return subject if subject.startswith("Release ") else ""


def portal_commands(tag: str, linux: bool | None = None, check: str = CHECK_SCRIPT, run_script: str = "") -> str:
    """Commit, test on a board, and only then push and tag: the tag is what reaches the users' portals. *check*:
    the suite's check-release.sh, relative to the checkout (check_script()); *run_script*: a Windows suite's
    portal/run.ps1 instead (portal_run_script()), tried on the handheld."""
    if run_script:
        before = [
            "# 2. Test on the handheld: start the portal from this checkout; it installs the apps apps.toml pins from",
            "#    their GitHub releases, as the installed portal does:",
            f"powershell -NoProfile -ExecutionPolicy Bypass -File {run_script} --windowed",
        ]
        after = [
            "# 4. Once GitHub's release workflow has built it: download the published release, then install it on",
            "#    the handheld as the portal's README says (check SHA256SUMS, Expand-Archive, install.ps1) and start it:",
            f'gh release download {tag} --dir "$TEMP/{tag}" --clobber',
        ]
    else:
        before = [
            "# 2. Test on a BC-250 (docs/portal.md, Testing a portal release before its tag): Test updates, or",
            f"{check} local     # ./install.sh, then bc250-bazzite-suite --source release",
        ]
        after = [
            "# 4. Once GitHub's release workflow has built it: Test release, or",
            f"{check} release {tag}   # installs and starts the published portal release",
        ]
    return "\n".join([
        "# 1. Commit (no push yet):",
        "git add -A && tools/fix-modes.sh",
        f'git commit -m "Release {tag}"',
        "",
        *before,
        "#    The apps whose pin changed show Update: update them, open each one, check that it works.",
        "#    Something wrong? Fix the app and release a new patch version (step 1), then pin again.",
        "",
        "# 3. All good: push, then tag the portal. The tag goes on the commit of step 1, so commit before you tag:",
        "#    the script refuses while HEAD does not hold the bump.",
        push_command(linux),
        f"{TAG_SCRIPT} {tag}",
        "",
        *after,
    ])


def main() -> int:
    """The units of every suite in the checkout, one line each (a line with the suite's name first when there are
    several): tools/release.sh --list."""
    names = suites(CHECKOUT) or [None]
    for name in names:
        if len(names) > 1:
            print(f"== {name}")
        list_units(load_units(CHECKOUT, name))
    return 0


def list_units(units: list[Unit]) -> None:
    for problem in bad_tags(CHECKOUT, units):
        print(f"WARNING: {problem}: delete the tag and tag the commit with the bump ({TAG_SCRIPT})", file=sys.stderr)
    for u in units:
        since = (f"released {u.released_as}" if u.released_as else "never released") if u.kind == NEXUS else \
            "never released" if u.last_tag is None and u.kind != "core" else \
            f"{u.commits} commits since {u.last_tag}" if u.last_tag else ""
        pinned = f"  pinned {u.pinned_tag}{'' if u.pinned_sha else ' (no sha256)'}" if u.pinned_tag else ""
        needs = f"  needs a release: {u.release_reason}" if u.needs_release else \
            f"  {u.release_reason}: {', '.join(u.in_apps)}" if u.in_apps else ""
        print(f"{u.key:<16} {u.version:<8} {since}{pinned}{needs}")


if __name__ == "__main__":
    sys.exit(main())
