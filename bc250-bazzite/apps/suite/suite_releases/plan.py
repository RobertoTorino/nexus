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
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

SUITE_DIR = "bc250-bazzite"             # the suite's folder in the checkout (Nexus holds every suite)
SUITE = Path(__file__).resolve().parents[4]           # bc250-bazzite/apps/suite/suite_releases/plan.py: the checkout
TOOLS = SUITE / "tools"                 # the Nexus tools (check_versions.py, stage_app.py)
SUITE_TOOLS = SUITE / SUITE_DIR / "tools"   # the suite's (check_manifest.py, pin_app.py)
CHECK_SCRIPT = f"{SUITE_DIR}/apps/suite/check-release.sh"  # relative to the checkout
RECORD_SCRIPT = f"{SUITE_DIR}/tools/record-tour.sh"   # the portal's video tour, relative to the checkout
TAG_SCRIPT = "tools/tag-release.sh"     # tags only a pushed HEAD that holds the version: never one before the bump
CI_LOCAL = "tools/ci-local.sh"          # CI's jobs here, in a container (Linux): the push only when they pass
VERSIONS_CHECK = "tools/check_versions.py"                        # the Nexus tools' check, every suite
MANIFEST_CHECK = f"{SUITE_DIR}/tools/check_manifest.py"          # the suite's manifest check
CHECKOUT_ONLY = ".checkout-only"        # an app folder with this marker runs from the checkout and is never released
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def _load(name: str, folder: Path = TOOLS):
    spec = importlib.util.spec_from_file_location(name, folder / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check_versions = _load("check_versions")
stage_app = _load("stage_app")
check_manifest = _load("check_manifest", SUITE_TOOLS)
pin_app = _load("pin_app", SUITE_TOOLS)


def suite_dir(root: Path) -> Path:
    """The suite's folder in the checkout *root* (its portal, apps, docs and tools): bc250-bazzite/, or *root*
    itself when it is laid out as a suite (the repositories the tests make)."""
    folder = root / SUITE_DIR
    return folder if (folder / "portal").is_dir() else root


def rel(root: Path, *parts: str) -> str:
    """A path in the suite's folder, relative to *root* (as git names it): "bc250-bazzite/portal/apps.toml"."""
    return (suite_dir(root) / Path(*parts)).relative_to(root).as_posix()


def manifest_path(root: Path) -> Path:
    return suite_dir(root) / "portal" / "apps.toml"


def manifest_copy(root: Path) -> Path | None:
    """The root's copy of apps.toml, for the portals installed before the suite moved into bc250-bazzite/ (they
    read it at a tag for their update notice); check_manifest.py keeps it identical. None once the owner removed it,
    or while the checkout is laid out as a suite."""
    copy = root / "portal" / "apps.toml"
    return copy if suite_dir(root) != root and copy.is_file() else None


def write_manifest(root: Path, text: str) -> list[Path]:
    """Writes apps.toml, and the root's copy while there is one. Returns the files written."""
    paths = [manifest_path(root)] + [p for p in [manifest_copy(root)] if p]
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
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def checkout_stamp(root: Path) -> str:
    """The checkout's last commit and its time in Amsterdam ("c109b51 · 15-10-2026 03:46"): Suite Releases is never
    released, so its VERSION stays put and this says which code runs. "" outside a git checkout."""
    out = (git(root, "log", "-1", "--format=%h %ct") or "").split()
    if len(out) != 2 or not out[1].isdigit():
        return ""
    when = amsterdam_now(datetime.datetime.fromtimestamp(int(out[1]), datetime.timezone.utc))
    return f"{out[0]} · {when:%d-%m-%Y %H:%M}"


def tags_of(root: Path, key: str) -> list[str]:
    """The release tags of one app (or the portal), oldest first."""
    found = []
    for tag in (git(root, "tag", "--list", f"{key}-v*") or "").split():
        version = tag[len(key) + 2:]
        if _VERSION.match(version):
            found.append((version_tuple(version), tag))
    return [tag for _, tag in sorted(found)]


def commits_since(root: Path, tag: str | None, path: str) -> int | None:
    out = git(root, "rev-list", "--count", f"{tag}..HEAD" if tag else "HEAD", "--", path)
    return int(out) if out and out.strip().isdigit() else None


# --- The units -------------------------------------------------------------------------------------------------

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

    @property
    def needs_release(self) -> bool:
        """Something it ships changed since its last tag (or it was never released). Core is never released."""
        return self.kind != "core" and (self.last_tag is None or bool(self.changed))

    @property
    def release_reason(self) -> str:
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
        return self.key if self.key in ("core", "portal") else "app"

    @property
    def tag(self) -> str:
        """The tag of the current VERSION."""
        return f"{self.key}-v{self.version}"

    @property
    def released(self) -> bool:
        return self.last_tag == self.tag


def shipped_sources(root: Path, key: str, path: str) -> list[str]:
    """The source paths a release of *key* is made from, as tools/stage_app.py stages it."""
    paths = [path]
    if key != "core" and stage_app.uses_core(root / path):
        paths.append("core/bc250_core")
    if key not in ("core", "portal") and (suite_dir(root) / "docs" / "apps" / f"{key}.md").is_file():
        paths.append(rel(root, "docs", "apps", f"{key}.md"))
    return paths


def is_shipped(rel: str) -> bool:
    parts = rel.split("/")
    return not (set(parts) & stage_app.SKIP_DIRS) and parts[-1] not in stage_app.SKIP_FILES \
        and not parts[-1].endswith(".pyc") and not any(p.startswith(".venv") for p in parts)


def changed_since(root: Path, tag: str, paths: list[str]) -> list[str]:
    """Shipped files under *paths* that differ between *tag* and the working tree: committed, not yet committed
    and new (untracked) files alike."""
    diff = git(root, "diff", "--name-only", tag, "--", *paths) or ""
    new = git(root, "ls-files", "--others", "--exclude-standard", "--", *paths) or ""
    return sorted({f for f in (diff + new).splitlines() if f and is_shipped(f)})


def bad_tags(root: Path, units: list[Unit]) -> list[str]:
    """Tags that point at a commit whose VERSION is not the tag's version: tagged before the version bump was
    committed. release.yml refuses to build those; delete the tag and tag the right commit again."""
    out = []
    for unit in units:
        if unit.kind == "core" or not unit.last_tag:
            continue
        at_tag = (git(root, "show", f"{unit.last_tag}:{unit.path}/VERSION") or "").strip()
        want = unit.last_tag[len(unit.key) + 2:]
        if at_tag and at_tag != want:
            out.append(f"{unit.last_tag} points at a commit where {unit.path}/VERSION is {at_tag}")
    return out


def load_units(root: Path = SUITE) -> list[Unit]:
    pins = {}
    try:
        for entry in check_manifest.manifest.load(manifest_path(root)):
            pins[entry.key] = entry
    except (OSError, check_manifest.manifest.ManifestError):
        pass
    units = []
    folders = [("core", "core"), ("portal", rel(root, "portal"))]
    folders += [(p.name, rel(root, "apps", p.name)) for p in sorted((suite_dir(root) / "apps").iterdir())
                if (p / "VERSION").is_file() and not (p / CHECKOUT_ONLY).is_file()]
    for key, path in folders:
        version = (root / path / "VERSION").read_text(encoding="utf-8").strip()
        tags = tags_of(root, key) if key != "core" else []
        last = tags[-1] if tags else None
        unit = Unit(key, path, version, last, commits_since(root, last, path),
                    standalone=(root / path / ".standalone").is_file())
        if last:
            unit.changed = changed_since(root, last, shipped_sources(root, key, path))
        if key in pins:
            unit.pinned_tag, unit.pinned_sha = pins[key].tag, pins[key].sha256
        units.append(unit)
    # Core is never tagged: it ships inside each app that imports it, so its changes are the core files those
    # apps' releases would carry.
    core = units[0]
    carriers = [u for u in units if u.kind != "core" and any(f.startswith("core/") for f in u.changed or [])]
    core.in_apps = [u.key for u in carriers]
    core.changed = sorted({f for u in carriers for f in u.changed or [] if f.startswith("core/")})
    core.current = core_is_current(root)
    return units


def core_is_current(root: Path) -> bool:
    """Whether core's VERSION already covers what it ships: nothing under core/bc250_core changed since the commit
    that last changed core/VERSION, or that VERSION is changed and not committed yet (a bump in progress). Then an
    app release carries core as it is, and core needs no new version."""
    if git(root, "diff", "--quiet", "HEAD", "--", "core/VERSION") is None:
        return True
    bump = (git(root, "log", "-1", "--format=%H", "--", "core/VERSION") or "").strip()
    return bool(bump) and not changed_since(root, bump, ["core/bc250_core"])


# --- Edits -----------------------------------------------------------------------------------------------------

def set_version(root: Path, unit: Unit, new: str) -> list[Path]:
    """Writes *new* to the unit's VERSION and to every copy check_versions.py checks; returns the changed files."""
    folder = root / unit.path
    changed = [folder / "VERSION"]
    (folder / "VERSION").write_bytes(f"{new}\n".encode())
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


def add_changelog_entry(root: Path, unit: Unit, text: str, now: datetime.datetime | None = None) -> Path:
    """Puts "Changelog: <time>", a blank line and *text* on top of the unit's CHANGELOG."""
    path = root / unit.path / "CHANGELOG"
    stamp = amsterdam_now(now).strftime("%d-%m-%Y %H:%M:%S")
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.write_bytes(f"Changelog: {stamp}\n\n{text.strip()}\n\n{old}".encode("utf-8"))
    return path


def release_text(version: str, notes: str) -> str:
    return f"Release {version}." + (f" {notes.strip()}" if notes.strip() else "")


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


def new_entries(root: Path, unit: Unit) -> list[str]:
    """The change entries (bodies) since the unit's last tag: its own, and core's when the release carries a core
    change. Core itself, never tagged: its entries since its last "Version x.y.z." entry."""
    def since(path: str, ref: str | None) -> list[str]:
        file = root / path / "CHANGELOG"
        current = changelog_entries(file.read_text(encoding="utf-8")) if file.is_file() else []
        if ref is None:
            cut = next((i for i, e in enumerate(current) if entry_body(e).startswith("Version ")), len(current))
            current = current[:cut]
        else:
            old = set(changelog_entries(git(root, "show", f"{ref}:{path}/CHANGELOG") or ""))
            current = [e for e in current if e not in old]
        return [b for b in map(entry_body, current) if b and not b.startswith(TOOL_ENTRIES)]

    if unit.kind == "core":
        return since(unit.path, None)
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
    """The version of the unit's last tag, where the next version counts from; its VERSION without a tag."""
    return unit.last_tag[len(unit.key) + 2:] if unit.last_tag else unit.version


def version_choices(root: Path, unit: Unit) -> tuple[list[str], str]:
    """The versions step 1 offers for the unit, the one semantic versioning gives first, and why. Breaking. ->
    major, Added. -> minor, otherwise patch, counted from the last tag. A VERSION bumped further already, never
    tagged, comes first; a first release is offered as it is."""
    nexts = list(next_versions(unit.version).values())
    if unit.kind == "core" and unit.current:
        return [unit.version] + nexts, f"{unit.version} already holds core's changes"
    if unit.kind != "core" and unit.last_tag is None:
        return [unit.version] + nexts, "the first release"
    level, why = suggested_level(new_entries(root, unit))
    suggested = next_versions(_tagged_version(unit))[level]
    reason = f"{level}: {why}" + (f" since {unit.last_tag}" if unit.last_tag else "")
    released = unit.released or unit.kind == "core"
    choices = [suggested, unit.version, *nexts]
    if version_tuple(unit.version) > version_tuple(suggested):
        choices.insert(0, unit.version)
    choices = [v for i, v in enumerate(choices) if v not in choices[:i] and not check_new_version(unit.version, v,
                                                                                                    released)]
    return choices, reason


def portal_suggestion(root: Path, portal: Unit) -> tuple[str, str]:
    """The portal's next version by semantic versioning since its last tag, and why: its own CHANGELOG entries, and
    what changed in apps.toml since that tag (an app added or removed: minor; the largest app bump it pins), as
    tools/check_manifest.py counts it."""
    level, why = suggested_level(new_entries(root, portal))
    reason = f"{level}: {why}" + (f" since {portal.last_tag}" if portal.last_tag else "")
    old = git(root, "show", f"{portal.last_tag}:{rel(root, 'portal', 'apps.toml')}") if portal.last_tag else None
    if old is not None:
        need, what = check_manifest.required_bump(old, (manifest_path(root)).read_text(encoding="utf-8"))
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


def withdrawable(root: Path, units: list[Unit]) -> list[Unit]:
    """The apps a portal pins that can be withdrawn: never the required one (Bazzite Test, always installed)."""
    required = {e.key for e in check_manifest.manifest.load(manifest_path(root)) if e.required}
    return [u for u in units if u.kind == "app" and not u.standalone and u.pinned_tag and u.key not in required]


def withdrawn_reason(root: Path, key: str) -> str:
    entries = check_manifest.manifest.load(manifest_path(root))
    return next((e.withdrawn for e in entries if e.key == key), "")


def withdraw(root: Path, unit: Unit, reason: str, now: datetime.datetime | None = None) -> list[Path]:
    """Marks the app's pinned release withdrawn (or, with no reason, takes that back) in apps.toml, with a CHANGELOG
    entry in the app. Returns the files changed."""
    path = manifest_path(root)
    paths = write_manifest(root, set_withdrawn(path.read_text(encoding="utf-8"), unit.key, reason))
    text = (f"Withdrawn: {unit.pinned_tag}. {reason.strip()}" if reason.strip() else
            f"Withdrawal of {unit.pinned_tag} taken back.")
    return [*paths, add_changelog_entry(root, unit, text, now)]


def changed_withdrawals(root: Path, base: str) -> list[tuple[str, str]]:
    """(tag, reason) of the apps withdrawn since *base*: what the portal release that follows withdraws."""
    old_text = git(root, "show", f"{base}:{rel(root, 'portal', 'apps.toml')}") or ""
    old = {e.key: e.withdrawn for e in check_manifest.manifest.parse(old_text)} if old_text else {}
    new = check_manifest.manifest.load(manifest_path(root))
    return [(e.tag, e.withdrawn) for e in new if e.withdrawn and not old.get(e.key)]


def withdraw_commands(tag: str, reason: str, now: datetime.datetime | None = None) -> str:
    """What stays the owner's: mark the GitHub release (it stays, as a pre-release, so no update check offers it),
    then the portal release that removes the app from the boards."""
    date = amsterdam_now(now).strftime("%d-%m-%Y")
    notes = f"Withdrawn on {date}: {reason.strip()} Do not install this release."
    return "\n".join([
        "# 1. Mark the release withdrawn on GitHub (it stays; a pre-release is offered by no update check):",
        f"gh release edit {tag} --prerelease --title {shlex.quote('Withdrawn: ' + tag)} "
        f"--notes {shlex.quote(notes)}",
        "",
        "# 2. Test it on a BC-250 with the app installed: Test withdrawal, tab Test on this board (check-release.sh",
        "#    local). The portal must show the app as \"App not available\" and remove it. Take back undoes the",
        "#    mark after a test.",
        "",
        "# 3. Then a portal release (2. Pin and release Portal: Bump portal, at least a minor version): it lists the",
        "#    withdrawal in its CHANGELOG entry; commit, push and tag it as usual.",
    ])


# --- Step 2: pins and the portal -------------------------------------------------------------------------------

def pin_candidates(units: list[Unit]) -> list[Unit]:
    """Apps whose current VERSION is tagged but not pinned with a checksum yet."""
    return [u for u in units if u.kind == "app" and not u.standalone and u.released
            and (u.pinned_tag != u.tag or not u.pinned_sha)]


def pin(root: Path, unit: Unit, sha256: str) -> None:
    text = manifest_path(root).read_text(encoding="utf-8")
    write_manifest(root, pin_app.pin(text, unit.key, unit.tag, sha256.lower()))
    unit.pinned_tag, unit.pinned_sha = unit.tag, sha256.lower()


def follow_unreleased_pin(root: Path, unit: Unit) -> bool:
    """When apps.toml pins a tag of this app that was never released, CI only accepts it while it matches VERSION:
    move the pin to the new version (sha256 empty). True when apps.toml changed; that push then needs a portal bump."""
    if unit.kind != "app" or not unit.pinned_tag or unit.pinned_tag == unit.tag \
            or unit.pinned_tag in tags_of(root, unit.key):
        return False
    text = manifest_path(root).read_text(encoding="utf-8")
    write_manifest(root, pin_app.pin(text, unit.key, unit.tag, ""))
    unit.pinned_tag, unit.pinned_sha = unit.tag, ""
    return True


def fetch_sha256(tag: str) -> str:
    return pin_app.fetch_sha256(tag)


def changed_pins(root: Path, base: str) -> list[str]:
    """The pinned tags that differ from *base*: the app releases this portal release brings."""
    old_text = git(root, "show", f"{base}:{rel(root, 'portal', 'apps.toml')}") or ""
    old = {e.key: e.tag for e in check_manifest.manifest.parse(old_text)} if old_text else {}
    new = check_manifest.manifest.load(manifest_path(root))
    return [e.tag for e in new if old.get(e.key) != e.tag]


def portal_minimum(root: Path, base: str, portal_version: str) -> tuple[str, str]:
    """The lowest portal version CI accepts (tools/check_manifest.py), and why: apps.toml against the last portal
    release (its tag; a version not tagged yet may still change what it pins), or against *base* (the last push)
    while there is no portal tag; ("", "") when apps.toml is unchanged. That release's version is the starting
    point."""
    tags = tags_of(root, "portal")
    ref = tags[-1] if tags else base
    old_text = git(root, "show", f"{ref}:{rel(root, 'portal', 'apps.toml')}")
    new_text = (manifest_path(root)).read_text(encoding="utf-8")
    if old_text is None:
        return "", ""
    need, why = check_manifest.required_bump(old_text, new_text)
    if need <= 0:
        return "", why
    start = ref[len("portal-v"):] if tags else (git(root, "show", f"{base}:{rel(root, 'portal', 'VERSION')}") or portal_version).strip()
    bumped = next_versions(start)[check_manifest.LEVELS[need]]
    if version_tuple(portal_version) > version_tuple(start) and \
            check_manifest.bump_level(start, portal_version) >= need:
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


def launch_targets(root: Path = SUITE) -> list[Launch]:
    """Every app window in the checkout: each package with a __main__.py (one or two levels below the app folder,
    tests left out). The checkout-only apps, like this one, are not listed."""
    try:
        board = {e.key: e.changes_board for e in check_manifest.manifest.load(manifest_path(root))}
    except (OSError, check_manifest.manifest.ManifestError):
        board = {}
    found = []
    for app in sorted((suite_dir(root) / "apps").iterdir()):
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


def portal_target(root: Path = SUITE) -> Launch | None:
    """The portal, started from the checkout as `python -m bc250_portal` in portal/: it takes its apps from the
    checkout, as it does when it runs from one. None when the checkout has no portal window."""
    folder = suite_dir(root) / "portal"
    if not (folder / "bc250_portal" / "__main__.py").is_file():
        return None
    try:
        version = (folder / "VERSION").read_text(encoding="utf-8").strip()
        consts = dict(_CONSTANT.findall((folder / "bc250_portal" / "__init__.py").read_text(encoding="utf-8")))
    except OSError:
        return None
    icon = folder / "images" / "bc250-bazzite-suite.webp"
    return Launch("portal", "bc250_portal", consts.get("APP_NAME", "bc250_portal"), folder, version, False,
                  icon if icon.is_file() else None, app_id=consts.get("APP_ID", ""))


def installer_tests_target(root: Path = SUITE) -> Launch | None:
    """BC-250 Installer Tests (tools/installer-tests/gui), started from the checkout as its run.sh does. None when the
    checkout has no such window."""
    folder = suite_dir(root) / "tools" / "installer-tests" / "gui"
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


def wiki_configs(root: Path = SUITE) -> list[Path]:
    """Each wiki in the checkout: mkdocs.yml at the root (none since the suites moved into their folders), then one
    in a folder directly below it (bc250-bazzite/, nexus/, and a new suite's), by folder name."""
    return [p for p in (root / "mkdocs.yml", *sorted(root.glob("*/mkdocs.yml"))) if p.is_file()]


def docs_targets(root: Path = SUITE, network: bool = False,
                 addresses: list[str] | None = None) -> list[Launch]:
    """Each wiki, served from the checkout with `mkdocs serve` (the dev venv has it), each on a port of its own: it
    rebuilds on every save, and its page opens with the design panel. The page is under the path of site_url, as on
    GitHub Pages. With *network* it is served on every address of this computer, for the other devices on the
    network; the browser here still opens it at 127.0.0.1."""
    found = []
    for number, config in enumerate(wiki_configs(root)):
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
        icon = suite_dir(root) / "portal" / "images" / "bc250-bazzite-suite.webp"
        found.append(Launch("docs" if folder == "." else f"docs-{folder}", "mkdocs",
                            f"{name[1] if name else folder} wiki ({where})", root, "", False,
                            icon if icon.is_file() else None,
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
                     str(r.get("display_title") or "")) for r in runs if isinstance(r, dict)]


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


def fetch_runs(etag: str = "") -> tuple[list[BuildRun] | None, str, RateInfo | None]:
    """The newest workflow runs (newest first), the ETag to send next time and GitHub's hourly limit as it stands;
    runs None when nothing changed since *etag*. GitHub answers that with 304, which does not count against the
    limit (60 requests without a token, 5,000 with the token of a gh login). Raises RateLimited when the limit is
    used up, OSError offline."""
    global _token
    token = github_token()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "bc250-release"}
    if etag:
        headers["If-None-Match"] = etag
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(RUNS_URL.format(repo=repo_slug()), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return (parse_runs(json.load(response)), response.headers.get("ETag", ""),
                    RateInfo.from_headers(response.headers, bool(token)))
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return None, etag, RateInfo.from_headers(exc.headers, bool(token))
        if exc.code == 401 and token:            # an expired or revoked login: go on without it
            _token = ""
            return fetch_runs(etag)
        if exc.code in (403, 429) and exc.headers.get("X-RateLimit-Remaining") == "0":
            raise RateLimited(float(exc.headers.get("X-RateLimit-Reset") or time.time() + 3600), bool(token),
                              RateInfo.from_headers(exc.headers, bool(token))) from exc
        raise


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


def release_run(runs: list[BuildRun], tag: str) -> BuildRun | None:
    """The newest Release run on *tag* (release.yml, which builds and publishes its tarball); None while GitHub
    shows none: the tag is not pushed yet, or the run is not among the newest ones any more."""
    return next((r for r in runs if r.workflow == "Release" and r.ref == tag), None)


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
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "bc250-release"}
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
    request = urllib.request.Request(STATUS_URL, headers={"User-Agent": "bc250-release"})
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


def add_command() -> str:
    """The git add button: everything, the exec bits CI checks, and what is staged now."""
    return "git add -A && tools/fix-modes.sh && git status --short"


def tag_command(tags: list[str]) -> str:
    """The git tag button: tag-release.sh, which tags only a pushed HEAD that CI passed, and pushes the tags."""
    return f"{TAG_SCRIPT} {' '.join(tags)}"


def commit_command(message: str, base: str, amend: bool = False, python: str = "python3") -> str:
    """The git commit button: the version and manifest checks first (CI's quick ones), the commit only when they
    pass. *amend*: the staged changes join HEAD, with its message."""
    checks = f"{python} {VERSIONS_CHECK} && {python} {MANIFEST_CHECK} --base {shlex.quote(base)}"
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


def portal_commands(tag: str, linux: bool | None = None) -> str:
    """Commit, test on a board, and only then push and tag: the tag is what reaches the users' portals."""
    return "\n".join([
        "# 1. Commit (no push yet):",
        "git add -A && tools/fix-modes.sh",
        f'git commit -m "Release {tag}"',
        "",
        "# 2. Test on a BC-250 (docs/portal.md, Testing a portal release before its tag): Test updates, or",
        f"{CHECK_SCRIPT} local     # ./install.sh, then bc250-bazzite-suite --source release",
        "#    The apps whose pin changed show Update: update them, open each one, check that it works.",
        "#    Something wrong? Fix the app and release a new patch version (step 1), then pin again.",
        "",
        "# 3. All good: push, then tag the portal. The tag goes on the commit of step 1, so commit before you tag:",
        "#    the script refuses while HEAD does not hold the bump.",
        push_command(linux),
        f"{TAG_SCRIPT} {tag}",
        "",
        "# 4. Once GitHub's release workflow has built it: Test release, or",
        f"{CHECK_SCRIPT} release {tag}   # installs and starts the published portal release",
    ])


def main() -> int:
    units = load_units()
    for problem in bad_tags(SUITE, units):
        print(f"WARNING: {problem}: delete the tag and tag the commit with the bump ({TAG_SCRIPT})", file=sys.stderr)
    for u in units:
        since = "never released" if u.last_tag is None and u.kind != "core" else \
            f"{u.commits} commits since {u.last_tag}" if u.last_tag else ""
        pinned = f"  pinned {u.pinned_tag}{'' if u.pinned_sha else ' (no sha256)'}" if u.pinned_tag else ""
        needs = f"  needs a release: {u.release_reason}" if u.needs_release else \
            f"  {u.release_reason}: {', '.join(u.in_apps)}" if u.in_apps else ""
        print(f"{u.key:<16} {u.version:<8} {since}{pinned}{needs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
