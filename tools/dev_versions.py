#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The versions of the Nexus apps in dev/ (owner, 04-11-2026: set by hand, they go wrong). A dev app is never
released or tagged: as core's, a new version is its VERSION, every copy tools/check_versions.py checks, and a
"Version x.y.z." entry on top of its CHANGELOG. The version offered counts the entries since the last such entry by
their kind: Breaking. major, Added. minor, Fixed. patch (an entry without one counts as a fix). Nexus Dashboard's
Dev app versions tile works with it.

    python3 tools/dev_versions.py                           # every dev app: its version, what changed, the offer
    python3 tools/dev_versions.py dash                      # gives dev/dash the version offered
    python3 tools/dev_versions.py dash 0.3.0 --notes "..."  # this version, with a note in its entry

A version set and not pushed yet can be set again: the new one replaces it and its entry. A pushed entry is history
and stays. Nothing is committed, tagged or released."""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_versions  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BASE = "origin/main"                    # the last push: an entry there is history
FIRST = "0.1.0"                         # every app starts at it: before its first Version entry
KINDS = {"Breaking.": "major", "Added.": "minor", "Fixed.": "patch"}
LEVELS = ("patch", "minor", "major")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_ENTRY = re.compile(r"^Changelog: .*$", re.M)
_MARK = re.compile(r"^(?:Version|Release) (\d+\.\d+\.\d+)\.")     # a version's own entry; Release: the tools' word
_NAME = re.compile(r'^APP_NAME\s*=\s*"([^"]+)"', re.M)
SKIP = {"tests", "__pycache__", ".venv", "node_modules"}


@dataclass
class DevApp:
    """One app of dev/ and where its next version stands."""
    key: str                            # its folder: dash, nrt, ...
    name: str
    folder: Path
    version: str                        # its VERSION now
    base: str                           # the version the next one counts from
    entries: list[str] = field(default_factory=list)    # the entries since that version, newest first
    redo: bool = False                  # its newest entry is a version set here and not pushed: setting replaces it

    @property
    def level(self) -> str:
        """patch, minor or major by the entries' kinds; "" when nothing changed."""
        if not self.entries:
            return ""
        return max((KINDS.get(kind(body), "patch") for body in self.entries), key=LEVELS.index)

    @property
    def offered(self) -> str:
        return next_version(self.base, self.level) if self.level else ""

    @property
    def why(self) -> str:
        counts: dict[str, int] = {}
        for body in self.entries:
            word = kind(body) or "without a kind"
            counts[word] = counts.get(word, 0) + 1
        return ", ".join(f"{n} {word.rstrip('.')}" for word, n in counts.items()) or f"nothing since {self.base}"


def kind(body: str) -> str:
    return next((word for word in KINDS if body == word or body.startswith(word + " ")), "")


def next_version(version: str, level: str) -> str:
    major, minor, patch = (int(n) for n in version.split("."))
    return {"major": f"{major + 1}.0.0", "minor": f"{major}.{minor + 1}.0", "patch": f"{major}.{minor}.{patch + 1}"}[
        level]


def changelog_entries(text: str) -> list[str]:
    """Each entry, its Changelog: line included, newest first."""
    starts = [m.start() for m in _ENTRY.finditer(text)]
    return [text[a:b].strip() for a, b in zip(starts, starts[1:] + [len(text)])]


def body(entry: str) -> str:
    return entry.split("\n", 1)[1].strip() if "\n" in entry else ""


def pushed(root: Path, path: str, base: str = BASE) -> str | None:
    """The file as *base* has it; None when git or the file is not there."""
    try:
        result = subprocess.run(["git", "show", f"{base}:{path}"], cwd=root, capture_output=True, text=True,
                                encoding="utf-8")
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def dev_apps(root: Path = ROOT, base: str = BASE) -> list[DevApp]:
    """Every app of dev/ with a VERSION, by folder name."""
    return [status(root, folder, base) for folder in sorted((root / "dev").iterdir())
            if (folder / "VERSION").is_file()]


def app_name(folder: Path) -> str:
    for init in sorted(folder.glob("*/__init__.py")):
        found = _NAME.search(init.read_text(encoding="utf-8"))
        if found:
            return found[1]
    return folder.name


def status(root: Path, folder: Path, base: str = BASE) -> DevApp:
    version = (folder / "VERSION").read_text(encoding="utf-8").strip()
    rel = folder.relative_to(root).as_posix()
    log = folder / "CHANGELOG"
    entries = changelog_entries(log.read_text(encoding="utf-8")) if log.is_file() else []
    app = DevApp(folder.name, app_name(folder), folder, version, version)
    newest = _MARK.match(body(entries[0])) if entries else None
    if newest and newest[1] == version and entries[0] not in changelog_entries(pushed(root, f"{rel}/CHANGELOG", base)
                                                                               or ""):
        app.redo = True
        entries = entries[1:]
        before = (pushed(root, f"{rel}/VERSION", base) or "").strip()
        older = next((_MARK.match(body(e))[1] for e in entries if _MARK.match(body(e))), "")
        app.base = before if _VERSION.match(before) else older or FIRST
    for entry in entries:
        if _MARK.match(body(entry)):
            break
        app.entries.append(body(entry))
    return app


def amsterdam_now(now: datetime.datetime | None = None) -> datetime.datetime:
    """Europe/Amsterdam time without a tz database (Windows has none): CET, CEST from the last Sunday of March to
    the last Sunday of October, switching at 01:00 UTC; as Nexus Release Tool writes its entries."""
    utc = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(datetime.timezone.utc)

    def last_sunday(month: int) -> datetime.datetime:
        day = datetime.datetime(utc.year, month, 31, 1, tzinfo=datetime.timezone.utc)
        return day - datetime.timedelta(days=(day.weekday() + 1) % 7)

    summer = last_sunday(3) <= utc < last_sunday(10)
    return (utc + datetime.timedelta(hours=2 if summer else 1)).replace(tzinfo=None)


class VersionError(ValueError):
    """A version that cannot be set; the message says why."""


def set_version(root: Path, key: str, version: str = "", notes: str = "", base: str = BASE,
                now: datetime.datetime | None = None) -> list[Path]:
    """Gives the dev app *key* *version* (the offered one when empty): its VERSION, every copy check_versions.py
    checks and a "Version x.y.z." entry on top of its CHANGELOG, replacing a version set before and not pushed.
    Returns the files it changed."""
    folder = root / "dev" / key
    if not (folder / "VERSION").is_file():
        raise VersionError(f"dev/{key} is no dev app with a VERSION.")
    app = status(root, folder, base)
    if not app.entries:
        raise VersionError(f"{app.name}: nothing in its CHANGELOG since {app.base}, so no new version.")
    version = version.strip() or app.offered
    if not _VERSION.match(version):
        raise VersionError(f"{version!r} is no version: x.y.z, such as {app.offered}.")
    if tuple(map(int, version.split("."))) <= tuple(map(int, app.base.split("."))):
        raise VersionError(f"{app.name}: {version} is not above {app.base}.")

    changed = [folder / "VERSION"]
    (folder / "VERSION").write_bytes(f"{version}\n".encode())
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or SKIP & set(path.relative_to(folder).parts):
            continue
        pattern = check_versions.version_pattern(path)
        if pattern is None:
            continue
        text = path.read_text(encoding="utf-8")
        new = pattern.sub(lambda m: m.group(0).replace(f'"{m.group(1)}"', f'"{version}"'), text)
        if new != text:
            path.write_bytes(new.encode("utf-8"))
            changed.append(path)

    log = folder / "CHANGELOG"
    old = log.read_text(encoding="utf-8") if log.is_file() else ""
    if app.redo:                        # the version set before, not pushed: this one takes its place
        first = changelog_entries(old)[0]
        old = old[old.index(first) + len(first):].lstrip("\n")
    text = f"Version {version}." + (f" {notes.strip()}" if notes.strip() else "")
    stamp = amsterdam_now(now).strftime("%d-%m-%Y %H:%M:%S")
    log.write_bytes(f"Changelog: {stamp}\n\n{text}\n\n{old}".encode("utf-8"))
    changed.append(log)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("app", nargs="?", help="the dev app's folder (dash, nrt, demo, itests, sounds)")
    parser.add_argument("version", nargs="?", default="", help="x.y.z; default: the version offered")
    parser.add_argument("--notes", default="", help="a sentence after Version x.y.z. in its CHANGELOG entry")
    args = parser.parse_args(argv)
    if not args.app:
        for app in dev_apps():
            offer = f"offers {app.offered} ({app.level}: {app.why})" if app.offered else app.why
            print(f"{app.key:<8} {app.name:<24} {app.version:<8} {offer}" + (" [not pushed yet]" if app.redo else ""))
        return 0
    try:
        changed = set_version(ROOT, args.app, args.version, args.notes)
    except VersionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for path in changed:
        print(path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
