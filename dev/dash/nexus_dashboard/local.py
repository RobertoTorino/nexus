# SPDX-License-Identifier: GPL-3.0-or-later
"""Test local apps: the suite's windows as they are in the checkout, to try them before their release (the suite's
portal, then every app with a __main__.py), and the wikis served from the checkout with mkdocs serve. Each is
`python -m <module>` with the dev venv's python and the checkout's core on the path, as run.sh starts an app. It
moved here from Nexus Release Tool's Test on this board (owner, 04-11-2026: the release tool is the release)."""

from __future__ import annotations

import os
import re
import socket
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .checkout import suites

CHECKOUT_ONLY = ".checkout-only"        # an app folder with this marker runs from the checkout and is never released
DOCS_HOST = "127.0.0.1"
DOCS_PORT = 8765                        # not mkdocs' default 8000, which other dev servers like to take
NETWORK_HOST = "0.0.0.0"                # every address of this computer, for the other devices
NETWORK_PORT = 8785                     # ports of their own, so a wiki can be served both ways at once
_CONSTANT = re.compile(r'^(APP_NAME|APP_ID)\s*=\s*"([^"]+)"', re.M)


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


def suite_dir(root: Path, suite: str | None = None) -> Path:
    """The suite's folder in the checkout, or the first suite's when none is named; *root* itself when it is laid
    out as a suite (the repositories the tests make)."""
    if suite:
        return root / suite
    names = suites(root)
    return root / names[0] if names else root


def changes_board(root: Path, suite: str | None = None) -> dict[str, bool]:
    """Each app of the suite's portal/apps.toml and whether it is marked changes_board; {} without a manifest."""
    try:
        with open(suite_dir(root, suite) / "portal" / "apps.toml", "rb") as file:
            apps = tomllib.load(file).get("apps", {})
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return {key: bool(card.get("changes_board", False)) for key, card in apps.items() if isinstance(card, dict)}


def launch_targets(root: Path, suite: str | None = None) -> list[Launch]:
    """Every app window of the suite in the checkout: each package with a __main__.py (one or two levels below the
    app folder, tests left out). The checkout-only apps are not listed."""
    board = changes_board(root, suite)
    found = []
    apps = suite_dir(root, suite) / "apps"
    for app in sorted(apps.iterdir()) if apps.is_dir() else ():
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


def wiki_icon(folder: Path) -> Path | None:
    """The icon of the wiki in *folder*: its suite's portal icon (bc250-bazzite/portal/images/bc250-bazzite-suite.webp),
    else its own drawing at 256 px (nexus/images/nexus-256.png); None without either."""
    for icon in (folder / "portal" / "images" / f"{folder.name}-suite.webp", folder / "images" / f"{folder.name}-256.png"):
        if icon.is_file():
            return icon
    return None


def portal_target(root: Path, suite: str | None = None) -> Launch | None:
    """The suite's portal, started from the checkout as `python -m <its package>` in portal/ (bc250_portal, the
    Windows Portable Suite's portable_portal): it takes its apps from the checkout, as it does when it runs from
    one. None when the suite has no portal window."""
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
    return Launch("portal", package.name, consts.get("APP_NAME", package.name), folder, version, False,
                  wiki_icon(suite_dir(root, suite)), app_id=consts.get("APP_ID", ""))


def network_addresses() -> list[str]:
    """This computer's IPv4 addresses that other devices can reach (no loopback), the one with the default route
    first. Read from the system; nothing is sent."""
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


def wiki_configs(root: Path) -> list[Path]:
    """Each wiki in the checkout: mkdocs.yml at the root (none since the suites moved into their folders), then one
    in a folder directly below it (bc250-bazzite/, nexus/, and a new suite's), by folder name."""
    return [p for p in (root / "mkdocs.yml", *sorted(root.glob("*/mkdocs.yml"))) if p.is_file()]


def docs_targets(root: Path, network: bool = False, addresses: list[str] | None = None,
                 suite: str | None = None) -> list[Launch]:
    """Each wiki, served from the checkout with `mkdocs serve` (the dev venv has it), each on a port of its own: it
    rebuilds on every save, and its page opens with the design panel. The page is under the path of site_url, as on
    GitHub Pages. With *network* it is served on every address of this computer, for the other devices on the
    network; the browser here still opens it at 127.0.0.1. With *suite*, that suite's wiki and the ones that are no
    suite's (the Nexus page), never another suite's (owner, 29-10-2026); a wiki keeps its port whichever suite is
    chosen."""
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


def targets(root: Path, suite: str | None, network: bool = False) -> list[Launch]:
    """The icons under Test local apps, in their order: the suite's portal, its apps, the wikis."""
    portal = portal_target(root, suite)
    return ([portal] if portal else []) + launch_targets(root, suite) + docs_targets(root, network, suite=suite)


def launch_command(root: Path, target: Launch, python: str = sys.executable) -> tuple[list[str], dict[str, str]]:
    """The command and environment that start *target* from the checkout: the dev venv's python, with the
    checkout's core on the path as run.sh does it (a release bundles core instead)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(root / "core"), env.get("PYTHONPATH"))))
    return [python, "-m", target.module, *target.args], env
