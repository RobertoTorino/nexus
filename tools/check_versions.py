#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""CI check: every version hard-coded in an app or in core (Python ``__version__ = "x.y.z"``, shell
``VERSION="x.y.z"``, pyproject and Cargo.toml ``version = "x.y.z"``, and a Rust crate's own entry in its
Cargo.lock) must equal that folder's VERSION file. VERSION is the single source; the literals exist so each script
and package still works on its own. Cargo.lock matters because CI builds with --locked, which fails when the lock
file's version of the crate differs from Cargo.toml. The root VERSION is Nexus's own and must be x.y.z; it has
no copies.

    python3 tools/check_versions.py                        # core, dev/ and every suite
    python3 tools/check_versions.py --suite windows-portable  # core, dev/ and that suite only: each suite's CI
                                                              # checks its own, so one suite never blocks another
    python3 tools/check_versions.py --nexus                # core and dev/ only: Nexus's CI (ci-nexus.yml)"""

import argparse
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = {                            # a comment may follow on the line
    ".py": re.compile(r'^__version__ = "([^"]+)"[ \t]*(?:#[^\n]*)?$', re.M),
    ".sh": re.compile(r'^VERSION="([^"]+)"[ \t]*(?:#[^\n]*)?$', re.M),
    ".toml": re.compile(r'^version = "([^"]+)"', re.M),         # pyproject.toml [project] version, Cargo.toml
}


def cargo_lock_pattern(lock: Path) -> re.Pattern | None:
    """The version of the crate itself in a Cargo.lock (the crate named in the Cargo.toml next to it), as group 1;
    None when there is no such Cargo.toml."""
    manifest = lock.with_name("Cargo.toml")
    if lock.name != "Cargo.lock" or not manifest.is_file():
        return None
    name = re.search(r'^name = "([^"]+)"', manifest.read_text(encoding="utf-8"), re.M)
    if name is None:
        return None
    return re.compile(r'^\[\[package\]\]\nname = "' + re.escape(name.group(1)) + r'"\nversion = "([^"]+)"', re.M)


# A line that assigns a literal version: one the pattern cannot read is an error, not a copy that is skipped (and
# then left behind by Nexus Releases' bump, which changes exactly the copies found here). Lines that read VERSION at
# run time (VERSION=$(...), __version__ = _read_version()) are no copies and stay out.
CANDIDATES = {".py": re.compile(r"""^__version__\s*=\s*["'].*$""", re.M),
              ".sh": re.compile(r"""^VERSION=["']?\d.*$""", re.M)}


def unreadable(path: Path, text: str) -> list[str]:
    """The lines of *text* that look like a version copy but do not match its pattern."""
    candidate, pattern = CANDIDATES.get(path.suffix), PATTERNS.get(path.suffix)
    if candidate is None:
        return []
    return [line for line in candidate.findall(text) if not pattern.fullmatch(line)]


def version_pattern(path: Path) -> re.Pattern | None:
    """How a version copy looks in this file, or None when the file holds none."""
    if path.name == "Cargo.lock":
        return cargo_lock_pattern(path)
    return PATTERNS.get(path.suffix)


def _suites():
    spec = importlib.util.spec_from_file_location("nexus_suites", ROOT / "tools" / "suites.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


suites = _suites()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", metavar="NAME", help="only this suite's folders, besides core and dev/")
    parser.add_argument("--nexus", action="store_true", help="core and dev/ only, no suite (Nexus's CI)")
    args = parser.parse_args([] if argv is None else argv)
    try:
        chosen = [] if args.nexus else [suites.suite(args.suite)] if args.suite else suites.suites()
    except LookupError as exc:
        print(exc, file=sys.stderr)
        return 1
    errors = []
    checked = 0
    # Nexus's own version (the root VERSION, GitHub's Latest release nexus-v<x.y.z>): no copies to compare, its
    # folder is the whole checkout, whose copies are the units' below.
    nexus = ROOT / "VERSION"
    if not nexus.is_file():
        errors.append("VERSION: no VERSION file at the root (Nexus's version)")
    elif not re.fullmatch(r"\d+\.\d+\.\d+", nexus.read_text(encoding="utf-8").strip()):
        errors.append(f"VERSION: {nexus.read_text(encoding='utf-8').strip()!r} is not x.y.z")
    units = [ROOT / "core", *sorted(p for p in (ROOT / "dev").glob("*") if p.is_dir())]   # the Nexus apps
    for suite in chosen:                        # each suite: its portal, apps and Installer Tests
        units += [suite / "portal", *sorted(p for p in (suite / "apps").iterdir() if p.is_dir())]
        if (suite / "tools" / "installer-tests" / "gui").is_dir():
            units.append(suite / "tools" / "installer-tests" / "gui")
    for unit in units:
        version_file = unit / "VERSION"
        if not version_file.is_file():
            errors.append(f"{unit.relative_to(ROOT)}: no VERSION file")
            continue
        want = version_file.read_text(encoding="utf-8").strip()
        if not re.fullmatch(r"\d+\.\d+\.\d+", want):
            errors.append(f"{version_file.relative_to(ROOT)}: {want!r} is not x.y.z")
        for path in unit.rglob("*"):
            if not path.is_file() or "tests" in path.parts or "target" in path.parts:
                continue
            pattern = version_pattern(path)
            if pattern is None:
                continue
            text = path.read_text(encoding="utf-8")
            for line in unreadable(path, text):
                errors.append(f"{path.relative_to(ROOT)}: version copy not in the form check_versions.py reads: {line}")
            for got in pattern.findall(text):
                checked += 1
                if got != want:
                    errors.append(f"{path.relative_to(ROOT)}: {got} != VERSION {want}")
    for e in errors:
        print(e, file=sys.stderr)
    if errors:
        return 1
    print(f"OK: {checked} versions in {len(units)} folders match their VERSION file")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
