#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The apps and their features across the suites (owner, 07-11-2026: one short matrix to cross-reference the
suites, kept up to date as the rest). nexus/features.toml holds it: every suite's column, and every app as a family
that names its folder in each suite that has it (PCSX2 Manager is pcsx2 in all three, DatStation datstation, datstation
and datstat), with its features in a few words, each marked with the suites that have it. This tool writes the Nexus
page's Apps and features chapter from it, nexus/docs/features.md: the apps per suite, then a matrix per app.

    python3 tools/features.py            # writes nexus/docs/features.md
    python3 tools/features.py --check    # exits 1 when the file and the suites differ, or the chapter is not current

The check fails when an app in a suite's portal/apps.toml is in no family (a new app adds its family:
tools/new_app.py writes one), a family names an app or a suite that is not there, a feature names a suite its
family is not in, or the chapter was not written again after a change (tools/tests/test_features.py runs it in CI).
The names and categories come from each suite's portal/apps.toml, so a renamed app shows there by itself. A suite in
a repository of its own (tools/suites.py: OWN_REPOSITORIES) must be in the checkout, cloned as its folder, for the
chapter to be written; --check without it checks nothing and says so (Nexus's CI; the suite's CI checks it)."""

from __future__ import annotations

import argparse
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import suites as nexus_suites  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path("nexus") / "features.toml"
PAGE = Path("nexus") / "docs" / "features.md"
PORTAL = "portal"                       # a family's key for the suite's portal, which apps.toml does not list
CATEGORIES = {"sustainable": "Sustainable", "graphics": "Graphics", "gaming": "Gaming", "utilities": "Utilities"}
YES, NO = "✓", ""


@dataclass
class Suite:
    """A column: the suite's folder, its name, the short name over its column and its wiki's address."""
    key: str                            # bc250-bazzite
    name: str                           # BC250 Bazzite Suite
    short: str                          # BC250
    wiki: str                           # https://robertotorino.github.io/nexus/bc250-bazzite-suite/
    apps: dict[str, dict] = field(default_factory=dict)     # its portal/apps.toml's [apps]


@dataclass
class Family:
    """One app across the suites, with its features."""
    name: str
    apps: dict[str, str]                # suite -> the app's folder in it (or "portal")
    features: list[tuple[str, list[str]]]   # (text, the suites that have it)


ABSENT = "a repository of its own"      # in the error of a suite that is not in this checkout


def absent(root: Path = ROOT) -> list[str]:
    """The chapter's suites that are in a repository of their own and not in this checkout: without them the
    chapter can neither be written nor checked (their apps' names and categories are in their apps.toml)."""
    data = tomllib.loads((root / DATA).read_text(encoding="utf-8"))
    found = {p.name for p in nexus_suites.suites(root)}
    return [key for key in data.get("suites", {}) if key not in found and key in nexus_suites.OWN_REPOSITORIES]


def load(root: Path = ROOT) -> tuple[list[Suite], list[Family], list[str]]:
    """The suites and the families of *root*'s nexus/features.toml, and what is wrong with them (empty: nothing)."""
    data = tomllib.loads((root / DATA).read_text(encoding="utf-8"))
    errors: list[str] = []
    found = {p.name: p for p in nexus_suites.suites(root)}
    columns: list[Suite] = []
    for key, entry in data.get("suites", {}).items():
        suite = Suite(key, entry["name"], entry["short"], entry["wiki"])
        if key in found:
            manifest = tomllib.loads((found[key] / "portal" / "apps.toml").read_text(encoding="utf-8"))
            suite.apps = manifest.get("apps", {})
        elif key in nexus_suites.OWN_REPOSITORIES:
            errors.append(f"[suites.{key}]: {key}/ is not in this checkout ({ABSENT}: clone "
                          f"{nexus_suites.OWN_REPOSITORIES[key]} into it as {key}/)")
        else:
            errors.append(f"[suites.{key}]: there is no suite {key}/ with portal/apps.toml")
        columns.append(suite)
    for key in found:
        if key not in data.get("suites", {}) and key not in nexus_suites.OWN_REPOSITORIES:
            errors.append(f"the suite {key}/ has no [suites.{key}] (its name, short name and wiki)")
    by_key = {suite.key: suite for suite in columns}

    families: list[Family] = []
    listed: dict[tuple[str, str], str] = {}
    for entry in data.get("family", []):
        name = entry.get("name", "?")
        family = Family(name, dict(entry.get("apps", {})), [])
        if not family.apps:
            errors.append(f"{name}: no apps")
        for suite, app in family.apps.items():
            if suite not in by_key:
                errors.append(f"{name}: no suite {suite} in [suites]")
                continue
            if app != PORTAL and app not in by_key[suite].apps:
                errors.append(f"{name}: {suite} has no app {app} in its portal/apps.toml")
            if (suite, app) in listed:
                errors.append(f"{name}: {suite}'s {app} is listed under {listed[suite, app]} already")
            listed[suite, app] = name
        for feature in entry.get("features", []):
            text = feature.get("text", "").strip()
            where = feature.get("in", list(family.apps))
            if not text:
                errors.append(f"{name}: a feature without text")
            for suite in where:
                if suite not in family.apps:
                    errors.append(f"{name}: {text!r} is marked for {suite}, which has no app of this family")
            family.features.append((text, [s for s in family.apps if s in where]))
        if not family.features:
            errors.append(f"{name}: no features")
        families.append(family)

    for suite in columns:
        if suite.key in found and (suite.key, PORTAL) not in listed:
            errors.append(f"{suite.key}'s portal is in no family")
        for app in suite.apps:
            if (suite.key, app) not in listed:
                errors.append(f"{suite.key}'s {app} ({suite.apps[app].get('name', app)}) is in no family: add it to "
                              f"{DATA.as_posix()}")
    return columns, families, errors


def category(family: Family, columns: list[Suite]) -> str:
    """The family's tab in the portals: its first suite's (the portal has none and comes first)."""
    for suite in columns:
        app = family.apps.get(suite.key)
        if app == PORTAL:
            return ""
        if app:
            return suite.apps.get(app, {}).get("category", "utilities")
    return "utilities"


def title(family: Family, suite: Suite) -> str:
    """The app's name in *suite*, linked to its chapter in the suite's wiki."""
    app = family.apps[suite.key]
    if app == PORTAL:
        return f"[Portal]({suite.wiki}portal/)"
    return f"[{suite.apps[app].get('name', app)}]({suite.wiki}apps/{app}/)"


def anchor(name: str) -> str:
    """The heading's anchor, as the page's slugify (pymdownx, GitHub's) makes it."""
    return "".join(c for c in name.lower().replace(" ", "-") if c.isalnum() or c in "-_")


def render(columns: list[Suite], families: list[Family]) -> str:
    """The chapter, nexus/docs/features.md."""
    order = list(CATEGORIES)
    families = sorted(families, key=lambda f: (order.index(c) + 1 if (c := category(f, columns)) in order else 0))
    head = "| " + " | ".join(suite.short for suite in columns) + " |"
    rule = "|" + "|".join(":---:" for _ in columns) + "|"
    out = [
        "<!-- SPDX-License-Identifier: GPL-3.0-or-later -->",
        "<!-- Written by tools/features.py from nexus/features.toml: edit that file, then run the tool. -->",
        "",
        "# Apps and features",
        "",
        "Every app of every suite, and what each one does, side by side. A row is one app; a column is a suite:",
        ", ".join(f"**{s.short}** is the [{s.name}]({s.wiki})" for s in columns) + ".",
        "",
        "## The apps per suite",
        "",
        "| App " + head,
        "|---" + rule,
    ]
    current = None
    for family in families:
        group = CATEGORIES.get(category(family, columns), "")
        if group != current and group:
            out.append(f"| **{group}** |" + " |" * len(columns))
        current = group
        cells = [title(family, s) if s.key in family.apps else NO for s in columns]
        out.append(f"| [{family.name}](#{anchor(family.name)}) | " + " | ".join(cells) + " |")
    out += ["", "## Features", ""]
    for family in families:
        out += [f"### {family.name}", "", "| Feature " + head, "|---" + rule]
        for text, where in family.features:
            cells = [YES if s.key in where else NO for s in columns]
            out.append(f"| {text} | " + " | ".join(cells) + " |")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only check: exit 1 when something is wrong or the "
                                                             "chapter is not current")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.check and absent(args.root):    # a checkout of Nexus alone (its CI): checked where every suite is
        print(f"{PAGE.as_posix()} is not checked here: {', '.join(absent(args.root))} is {ABSENT}, not in this "
              "checkout")
        return 0
    columns, families, errors = load(args.root)
    for error in errors:
        print(f"{DATA.as_posix()}: {error}", file=sys.stderr)
    if errors:
        return 1
    page = render(columns, families)
    path = args.root / PAGE
    if args.check:
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        if current != page:
            print(f"{PAGE.as_posix()} is not current: run python3 tools/features.py", file=sys.stderr)
            return 1
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(page.encode("utf-8"))           # LF, as every text file in the repository
    print(f"wrote {PAGE.as_posix()}: {len(families)} apps, {sum(len(f.features) for f in families)} features")
    return 0


if __name__ == "__main__":
    sys.exit(main())
