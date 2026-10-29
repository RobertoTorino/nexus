#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Upstream check: is every emulator an app of the Windows Portable Suite installs still the newest stable release?

    python3 windows-portable/tools/check_upstream.py [--report FILE] [app ...]      # every app when none is named

Each app that installs an emulator pins one release in its emulator.py (PCSX2 Manager's, PPSSPP Manager's, RPCS3
Manager's, shadPS4 Manager's): REPO, its GitHub repository; VERSION (or TAG), the release; ASSET, the file it
downloads; SHA256, the checksum it was tried with; and, where the file is published in another repository than the releases (RPCS3's builds,
RPCS3/rpcs3-binaries-win, one release per build, its landmarks tagged in RPCS3/rpcs3), BUILDS, that repository, and
BUILD_TAG, the file's release there. They are read here without importing the app, from every
apps/<name>/<package>/emulator.py of the suite. For each:
 * the latest stable release: newer than the pin means a new version of the app, which brings it once tried on the
   device (owner, 29-10-2026: a new emulator can break things, so it never reaches the device without a release of
   the app); the report names the release and the constant to move. An emulator that publishes a build for every
   change (Vita3K Manager's: CADENCE = "daily" in its emulator.py, as the BC250 suite's check leaves Vita3K out) is
   not compared: it would be reported every week, and the app's own pane shows its newest build;
 * the pinned release's asset: GitHub's published SHA-256 for it must still be the pinned one (a replaced file would
   fail every install).

Exit code 0: all in step; 1: an upstream moved (the report says what); 2: one could not be checked (network, GitHub's
rate limit). --report FILE writes what moved as Markdown, for the "Upstream review (Windows Portable Suite)" issue
(empty when all are in step). The weekly workflow .github/workflows/upstream-windows-portable.yml runs it; with
GITHUB_TOKEN set it asks GitHub's API as that token. Nothing is changed or published. The BC250 suite has its own
(bc250-bazzite/tools/check_upstream.py): each suite stands apart."""

from __future__ import annotations

import ast
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

SUITE = Path(__file__).resolve().parent.parent
API = "https://api.github.com/repos/{repo}"
TIMEOUT = 30
TITLE = "Upstream review (Windows Portable Suite)"

Fetch = Callable[[str], bytes]


class CheckError(Exception):
    pass


def fetch(url: str) -> bytes:
    headers = {"User-Agent": "windows-portable-check-upstream", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise CheckError(f"{url}: GitHub answered {error.code}") from error
    except (urllib.error.URLError, OSError) as error:
        raise CheckError(f"{url}: {getattr(error, 'reason', error)}") from error


@dataclass(frozen=True)
class Pin:
    """What an app pins, from its emulator.py."""
    app: str                                    # the app's folder: "ppsspp"
    name: str                                   # its APP_NAME: "PPSSPP Manager"
    repo: str                                   # "hrydgard/ppsspp"
    version: str                                # "1.20.4"
    tag: str                                    # "v1.20.4"
    asset: str                                  # "PPSSPP-v1.20.4-Windows-x64.zip"
    sha256: str
    where: str                                  # "VERSION in windows-portable/apps/ppsspp/ppsspp_manager/emulator.py"
    asset_repo: str = ""                        # where the file is, when not *repo*: "RPCS3/rpcs3-binaries-win"
    asset_tag: str = ""                         # its release there: "build-<commit>"
    daily: bool = False                         # a build for every change (CADENCE = "daily"): the file checked only

    @property
    def file_repo(self) -> str:
        return self.asset_repo or self.repo

    @property
    def file_tag(self) -> str:
        return self.asset_tag or self.tag


def _constants(path: Path) -> dict[str, str]:
    """The module's string constants, f-strings and names worked out from the constants before them
    (TAG = f"v{VERSION}", TAG = VERSION)."""
    found: dict[str, str] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            found[node.targets[0].id] = value.value
        elif isinstance(value, ast.Name) and value.id in found:     # TAG = VERSION
            found[node.targets[0].id] = found[value.id]
        elif isinstance(value, ast.JoinedStr):
            parts = []
            for part in value.values:
                if isinstance(part, ast.Constant):
                    parts.append(str(part.value))
                elif isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name) \
                        and part.value.id in found:
                    parts.append(found[part.value.id])
                else:
                    break
            else:
                found[node.targets[0].id] = "".join(parts)
    return found


def pins(suite: Path = SUITE) -> list[Pin]:
    """Every app of the suite whose emulator.py pins a release (REPO, VERSION or TAG, ASSET, SHA256), by folder."""
    found = []
    for path in sorted(suite.glob("apps/*/*/emulator.py")):
        values = _constants(path)
        if not {"REPO", "ASSET", "SHA256"} <= set(values) or not ({"VERSION", "TAG"} & set(values)):
            continue
        init = _constants(path.parent / "__init__.py") if (path.parent / "__init__.py").is_file() else {}
        version = values.get("VERSION") or values["TAG"].lstrip("v")
        constant = "VERSION" if "VERSION" in values else "TAG"
        found.append(Pin(path.parent.parent.name, init.get("APP_NAME", path.parent.parent.name), values["REPO"],
                         version, values.get("TAG", f"v{version}"), values["ASSET"], values["SHA256"].lower(),
                         f"{constant} in {path.relative_to(suite.parent).as_posix()}",
                         values.get("BUILDS", ""), values.get("BUILD_TAG", ""), values.get("CADENCE") == "daily"))
    return found


def _version(tag: str) -> tuple[int, ...]:
    parts = tag.lstrip("v.").split("-")[0].split(".")
    return tuple(int(p) for p in parts if p.isdigit())


@dataclass
class Report:
    pin: Pin
    latest: str = ""
    drift: list[str] = field(default_factory=list)
    fine: list[str] = field(default_factory=list)

    def text(self) -> str:
        latest = "a build daily, not compared" if self.pin.daily else f"latest stable {self.latest or 'unknown'}"
        head = f"{self.pin.name}: pinned {self.pin.version}, {latest}. " + ("In step." if not self.drift else "Moved:")
        return "\n".join([head] + [f"  - {line}" for line in self.drift] + [f"  ok {line}" for line in self.fine])


def check(pin: Pin, get: Fetch = fetch) -> Report:
    report = Report(pin)
    if pin.daily:
        report.fine.append("newer builds are not compared: the app's pane shows the newest")
    else:
        latest = json.loads(get(f"{API.format(repo=pin.repo)}/releases/latest"))
        tag = str(latest.get("tag_name", ""))
        report.latest = tag.lstrip("v.")            # v1.20.4, and shadPS4's v.0.20.0
        if tag and _version(tag) > _version(pin.version):
            report.drift.append(f"{tag} is out ({str(latest.get('published_at', ''))[:10]}): a new version of "
                                f"{pin.name} brings it, once tried on the device ({pin.where}). "
                                f"{latest.get('html_url', '')}")
        else:
            report.fine.append(f"no stable release newer than {pin.version}")
    pinned = json.loads(get(f"{API.format(repo=pin.file_repo)}/releases/tags/{pin.file_tag}"))
    asset = next((a for a in pinned.get("assets", []) if a.get("name") == pin.asset), None)
    if asset is None:
        report.drift.append(f"{pin.asset} is gone from {pin.file_tag}: every install of {pin.name} fails now.")
    else:
        digest = str(asset.get("digest") or "")
        if digest.startswith("sha256:") and digest[7:].lower() != pin.sha256:
            report.drift.append(f"{pin.asset} of {pin.file_tag} was replaced: GitHub publishes {digest[7:]}, the app pins "
                                f"{pin.sha256}; every install of {pin.name} fails now.")
        else:
            report.fine.append(f"{pin.asset} is the pinned file" if digest else f"{pin.asset} is there")
    return report


def markdown(reports: list[Report], failed: list[str]) -> str:
    """The issue's body: each emulator that moved with what to do, and those that could not be checked."""
    parts = [f"### {report.pin.name}\n\nPinned {report.pin.version}, "
             + ("a build daily, not compared" if report.pin.daily else f"latest stable {report.latest or 'unknown'}")
             + ".\n\n" + "\n".join(f"- {line}" for line in report.drift) for report in reports if report.drift]
    if parts and failed:
        parts.append("Not checked this week: " + "; ".join(failed))
    if parts:
        parts.insert(0, "The weekly upstream check (windows-portable/tools/check_upstream.py) found emulators that "
                        "moved since the apps pinned them. A newer emulator reaches the device only with a new "
                        "release of its app, tried first. Close this issue once they are handled; next week opens a "
                        "new one when something moved again.")
    return "\n\n".join(parts) + ("\n" if parts else "")


def main(argv: list[str] | None = None, get: Fetch = fetch, suite: Path = SUITE) -> int:
    argv = list(argv or [])
    report_file = None
    if "--report" in argv:
        at = argv.index("--report")
        if at + 1 >= len(argv):
            print("--report needs a file", file=sys.stderr)
            return 2
        report_file = Path(argv[at + 1])
        del argv[at:at + 2]
    found = {pin.app: pin for pin in pins(suite)}
    unknown = [name for name in argv if name not in found]
    if unknown:
        print(f"Unknown: {', '.join(unknown)}; known: {', '.join(found)}", file=sys.stderr)
        return 2
    code = 0
    reports, failed = [], []
    for name in argv or list(found):
        pin = found[name]
        try:
            report = check(pin, get)
        except (CheckError, ValueError) as error:
            print(f"{pin.name} could not be checked: {error}", file=sys.stderr)
            failed.append(f"{pin.name} ({error})")
            code = 2
            continue
        reports.append(report)
        text = report.text()
        print(text)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as out:
                out.write("```\n" + text + "\n```\n")
        if report.drift and code == 0:
            code = 1
    if report_file is not None:
        report_file.write_text(markdown(reports, failed), encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
