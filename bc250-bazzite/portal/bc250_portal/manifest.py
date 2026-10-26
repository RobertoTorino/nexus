# SPDX-License-Identifier: GPL-3.0-or-later
"""apps.toml: the apps of this portal release, each pinned to one release tag (see the comment in apps.toml), and
the checkout-only apps a portal that runs from a suite checkout also lists."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_TAG = re.compile(r"^(?P<app>[a-z0-9-]+)-v(?P<version>\d+\.\d+\.\d+)$")
_SHA256 = re.compile(r"^([0-9a-f]{64})?$")
# category = "<key>": the app's category (its icon, icons/categories.toml) and the portal's tab for it, in this order.
CATEGORIES = {"sustainable": "Sustainable", "graphics": "Graphics", "gaming": "Gaming", "utilities": "Utilities",
              "development": "Development"}
# Apps renamed in the suite (old key: new key), for the record of a copy installed under the old key.
RENAMED = {"ace-queues": "ace", "bazzite-netcatgui": "ncgui", "bazzite-datstation": "datstation",
           "bazzite-test": "check", "bios-reader": "bios",
           "console-link": "consoles", "cores-bisect": "cores", "cu-bisect": "compute",
           "decky-manager": "decky", "fan-control": "fan",
           "governor": "gpu", "gpu-oc-bisect": "oc",
           "hdmi-cec": "cec", "memory-manager": "vram",
           "mesh-shaders": "mesh", "pcsx2-manager": "pcsx2",
           "ppsspp-manager": "ppsspp", "rpcs3-manager": "rpcs3",
           "shadps4-manager": "shadps4", "vita3k-manager": "vita3k",
           "demo-tool": "mtool", "dtool": "mtool", "dependency-checker": "package",
           "persistent-acpi": "acpi", "sftp-tools": "sftp",
           "suite-releases": "suite", "suite": "releases", "usb-wifi": "wdriver",
           "system-overlay": "overlay", "helixsr": "upscaler"}


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class AppEntry:
    key: str                                    # "compute": folder under apps/, tag prefix
    name: str
    summary: str
    tag: str                                    # "" for a checkout-only app: it is never released
    sha256: str = ""
    required: bool = False
    changes_board: bool = False
    category: str = ""                          # a key of CATEGORIES; "" only in a manifest from before categories
    checkout_only: bool = False                 # [checkout.<key>]: installs from its folder in the suite checkout
    folder: str = ""                            # checkout-only: that folder, relative to the checkout (apps/<key>)
    nexus: bool = False                         # checkout-only: a Nexus app, its folder relative to the repository
    install: tuple[str, ...] = ()
    uninstall: tuple[str, ...] = ()
    detect: tuple[str, ...] = ()
    launch: tuple[tuple[str, str], ...] = ()
    short: str = ""                             # the name on its tile; "": the name without the suite prefix
    # withdrawn = "<reason>" in apps.toml: the release was withdrawn (privacy, security or another problem). The
    # portal shows the app as not available, offers no install, and removes it from a board that has it; the GitHub
    # release stays, marked withdrawn (a pre-release named "Withdrawn: ...", which no update check offers). Not for
    # the required app, nor for [checkout.*] apps. "": not withdrawn.
    withdrawn: str = ""

    @property
    def development(self) -> bool:
        """A tool for working on the suite, not for using the board."""
        return self.category == "development"

    @property
    def version(self) -> str:
        return self.tag.rsplit("-v", 1)[1] if self.tag else ""

    @property
    def asset(self) -> str:
        """The release asset: <tag>.tar.gz, which unpacks into a folder named <tag>."""
        return f"{self.tag}.tar.gz"


def version_tuple(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(p) for p in version.split("."))
    return major, minor, patch


def _strings(key: str, field: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ManifestError(f"[apps.{key}] {field} must be a list of non-empty strings")
    return tuple(value)


def _entry(key: str, raw: dict, table: str = "apps") -> AppEntry:
    checkout_only = table == "checkout"
    for field in ("name", "summary") + (() if checkout_only else ("tag",)):
        if not isinstance(raw.get(field), str) or not raw[field].strip():
            raise ManifestError(f"[{table}.{key}] needs a non-empty {field}")
    folder = ""
    nexus = False
    if checkout_only:
        if any(field in raw for field in ("tag", "sha256", "required")):
            raise ManifestError(f"[{table}.{key}] is never released: no tag, sha256 or required")
        folder = raw.get("folder", f"apps/{key}")
        if not isinstance(folder, str) or not folder.strip() or folder.startswith("/") or ".." in folder.split("/"):
            raise ManifestError(f"[{table}.{key}] folder must be a path inside the checkout, like apps/{key}")
        nexus = raw.get("nexus", False)
        if not isinstance(nexus, bool):
            raise ManifestError(f"[{table}.{key}] nexus must be true or false")
        if nexus and "folder" not in raw:
            raise ManifestError(f"[{table}.{key}] a Nexus app names its folder in the repository (dev/{key})")
    elif "folder" in raw or "nexus" in raw:
        raise ManifestError(f"[{table}.{key}] folder and nexus are only for [checkout.*] apps")
    else:
        match = _TAG.match(raw["tag"])
        if not match or match["app"] != key:
            raise ManifestError(f"[{table}.{key}] tag {raw['tag']!r} is not {key}-v<x.y.z>")
    sha = str(raw.get("sha256", "")).lower()
    if not _SHA256.match(sha):
        raise ManifestError(f"[{table}.{key}] sha256 must be empty or 64 hex digits")
    short = raw.get("short", "")
    if not isinstance(short, str):
        raise ManifestError(f"[{table}.{key}] short must be a string")
    withdrawn = raw.get("withdrawn", "")
    if "withdrawn" in raw and (not isinstance(withdrawn, str) or not withdrawn.strip()):
        raise ManifestError(f"[{table}.{key}] withdrawn must say why the release was withdrawn")
    if withdrawn and checkout_only:
        raise ManifestError(f"[{table}.{key}] is never released, so it cannot be withdrawn")
    category = raw.get("category", "development" if checkout_only else "")
    if category not in ("", *CATEGORIES):
        raise ManifestError(f"[{table}.{key}] category must be one of {', '.join(CATEGORIES)}")
    if checkout_only and category != "development":
        raise ManifestError(f"[{table}.{key}] runs from the checkout: its category is development")
    launch = raw.get("launch", [])
    if not isinstance(launch, list) or not all(isinstance(item, list) and len(item) == 2 and
                                               all(isinstance(s, str) and s for s in item) for item in launch):
        raise ManifestError(f"[{table}.{key}] launch must be a list of [label, command] pairs")
    entry = AppEntry(key=key, name=raw["name"], summary=raw["summary"], tag=raw.get("tag", ""), sha256=sha,
                     required=bool(raw.get("required", False)), changes_board=bool(raw.get("changes_board", False)),
                     category=category, checkout_only=checkout_only, folder=folder, nexus=nexus,
                     install=_strings(key, "install", raw.get("install")),
                     uninstall=_strings(key, "uninstall", raw.get("uninstall")),
                     detect=_strings(key, "detect", raw.get("detect")),
                     launch=tuple((label, command) for label, command in launch), short=short.strip(),
                     withdrawn=withdrawn.strip())
    if not entry.install or not entry.uninstall or not entry.detect:
        raise ManifestError(f"[{table}.{key}] install, uninstall and detect must not be empty")
    if entry.required and entry.development:
        raise ManifestError(f"[{table}.{key}] the required app cannot be a development app")
    if entry.required and entry.withdrawn:
        raise ManifestError(f"[{table}.{key}] the required app cannot be withdrawn: pin a release that works")
    return entry


def _load_toml(text: str) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"apps.toml is not valid TOML: {exc}") from exc


def parse(text: str) -> list[AppEntry]:
    """The pinned apps in display order: the required one(s) first, the rest in file order."""
    apps = _load_toml(text).get("apps")
    if not isinstance(apps, dict) or not apps:
        raise ManifestError("apps.toml has no [apps.<name>] tables")
    entries = [_entry(key, raw) for key, raw in apps.items()]
    if not any(e.required for e in entries):
        raise ManifestError("apps.toml must have a required app (check)")
    return sorted(entries, key=lambda e: not e.required)        # stable: file order within each group


def parse_checkout(text: str) -> list[AppEntry]:
    """The checkout-only apps ([checkout.<key>]), in file order: never released, so never pinned; only a portal
    that runs from a suite checkout can install them (without one their tiles are grayed)."""
    apps = _load_toml(text).get("checkout", {})
    if not isinstance(apps, dict):
        raise ManifestError("apps.toml: checkout must hold [checkout.<name>] tables")
    return [_entry(key, raw, "checkout") for key, raw in apps.items()]


def load(path: Path) -> list[AppEntry]:
    return parse(path.read_text(encoding="utf-8"))


def load_checkout(path: Path) -> list[AppEntry]:
    return parse_checkout(path.read_text(encoding="utf-8"))
