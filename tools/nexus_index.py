#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Nexus index: the text of the release that is GitHub's "Latest", one section per suite with its newest portal.

    python3 tools/nexus_index.py                    # Markdown on stdout, from the releases on GitHub (gh api)
    python3 tools/nexus_index.py --releases FILE    # from a saved release list (JSON: a list, or one per line)

A repository has one "Latest" release and Nexus holds several suites, so no portal is it: the release tagged nexus
is, and its text points at each suite's newest portal (tools/suites.py: the suites, their TAG_PREFIX; the name is
the portal's APP_NAME), with its tarball, SHA256SUMS and the install steps of its notes. A suite without a portal
release yet lists the newest release of each app in its apps.toml instead. Drafts and pre-releases are skipped. The
workflow .github/workflows/nexus-index.yml writes it to the nexus release after every release of any suite;
nothing is changed here."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "RobertoTorino/nexus"
RELEASES_URL = f"https://github.com/{REPO}/releases"
# What a suite is for, while it has no wiki whose site_description says it (owner, 28-10-2026: the Windows suite's)
SYSTEM_TEXTS = {"bazzite": "For Bazzite.", "windows": "For Windows running on portable gaming devices."}
_VERSION = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


suites = _load("nexus_suites", ROOT / "tools" / "suites.py")


def suite_name(folder: Path) -> str:
    """The portal's APP_NAME ("BC250 Bazzite Suite"), read without importing the portal; the folder's name without."""
    for init in sorted((folder / "portal").glob("*/__init__.py")):
        found = re.search(r'^APP_NAME = "(.*)"$', init.read_text(encoding="utf-8"), re.M)
        if found:
            return found[1]
    return folder.name


def wiki(folder: Path) -> tuple[str, str]:
    """The suite's wiki address and description (site_url and site_description of its mkdocs.yml), "" without."""
    path = folder / "mkdocs.yml"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    found = [re.search(rf"^{key}: (.+)$", text, re.M) for key in ("site_url", "site_description")]
    return (found[0][1].strip() if found[0] else "", found[1][1].strip() if found[1] else "")


def newest(releases: list[dict], prefix: str) -> tuple[str, dict] | None:
    """The newest published release whose tag is <prefix>v<x.y.z>, with its version; None without one."""
    best = None
    for release in releases:
        tag = str(release.get("tag_name", ""))
        if release.get("draft") or release.get("prerelease") or not tag.startswith(prefix):
            continue
        match = _VERSION.match(tag[len(prefix):])
        if match:
            version = tuple(int(part) for part in match.groups())
            if best is None or version > best[0]:
                best = (version, release)
    return (".".join(map(str, best[0])), best[1]) if best else None


def _asset(release: dict, suffixes: tuple[str, ...]) -> dict | None:
    return next((a for a in release.get("assets", []) if str(a.get("name", "")).endswith(suffixes)), None)


def install_steps(notes: str) -> str:
    """The first code block of the "### Install" section of a release's notes (the portal's, as build_release.py
    writes them), so each suite's own steps are shown; "" without one."""
    found = re.search(r"^### Install\s*$(.*?)(?=^### |\Z)", notes, re.M | re.S)
    block = re.search(r"^```.*?^```", found[1], re.M | re.S) if found else None
    return block[0].replace("\r\n", "\n") if block else ""


def section(folder: Path, releases: list[dict]) -> list[str]:
    name, prefix = suite_name(folder), suites.tag_prefix(folder)
    url, description = wiki(folder)
    system = suites.system(folder)
    about = " ".join(part for part in (
        f"{description.rstrip('.')}." if description else SYSTEM_TEXTS.get(system, f"For {system}." if system else ""),
        f"[Wiki]({url})" if url else "") if part)
    out = [f"## {name}", ""] + ([about, ""] if about else [])
    portal = newest(releases, f"{prefix}portal-")
    if portal:
        version, release = portal
        line = f"**[Portal {version}]({release.get('html_url', RELEASES_URL)})**"
        archive, sums = _asset(release, (".tar.gz", ".zip")), _asset(release, ("SHA256SUMS",))
        if archive and sums:
            line += (f": download [`{archive['name']}`]({archive['browser_download_url']}) and "
                     f"[`SHA256SUMS`]({sums['browser_download_url']}), then in the folder you downloaded them to:")
        steps = install_steps(str(release.get("body") or ""))
        return out + [line, ""] + ([steps, ""] if steps and archive and sums else [])
    apps = tomllib.loads((folder / suites.MANIFEST).read_text(encoding="utf-8")).get("apps", {})
    found = [(entry.get("name", key), newest(releases, f"{prefix}{key}-")) for key, entry in apps.items()]
    found = [(app, release) for app, release in found if release]
    if not found:
        return out + ["No release yet.", ""]
    return out + ["No portal release yet. The newest release of each app:", ""] + [
        f"- [{app} {version}]({release.get('html_url', RELEASES_URL)})" for app, (version, release) in found] + [""]


def body(releases: list[dict], root: Path = ROOT) -> str:
    out = ["Nexus is the home of the suites. Install a suite with its portal: it installs, updates and removes the "
           "suite's apps for you and checks every download.", ""]
    for folder in suites.suites(root):
        out += section(folder, releases)
    out += [f"Every release of every suite: [Releases]({RELEASES_URL}).", ""]
    return "\n".join(out)


def fetch_releases() -> list[dict]:
    """Every release on GitHub, through gh (signed in with GH_TOKEN in the workflow)."""
    result = subprocess.run(
        ["gh", "api", "--paginate", f"repos/{REPO}/releases?per_page=100", "--jq",
         ".[] | {tag_name, html_url, draft, prerelease, body, assets: [.assets[] | {name, browser_download_url}]}"],
        capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode != 0:
        raise SystemExit(f"gh api failed: {result.stderr.strip()}")
    return _parse(result.stdout)


def _parse(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The Nexus index, the text of GitHub's Latest release, as Markdown.")
    parser.add_argument("--releases", type=Path, help="a saved release list instead of asking GitHub")
    args = parser.parse_args(argv)
    releases = _parse(args.releases.read_text(encoding="utf-8")) if args.releases else fetch_releases()
    sys.stdout.write(body(releases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
