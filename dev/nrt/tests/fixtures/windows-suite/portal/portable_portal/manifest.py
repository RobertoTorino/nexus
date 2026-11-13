# SPDX-License-Identifier: GPL-3.0-or-later
"""apps.toml: the apps of this portal release, each pinned to one release tag (see the comment in apps.toml)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

TAG_PREFIX = "wp-"                              # the suite's tags (windows-portable/TAG_PREFIX)
_TAG = re.compile(r"^wp-(?P<app>[a-z0-9-]+)-v(?P<version>\d+\.\d+\.\d+)$")
_SHA256 = re.compile(r"^([0-9a-f]{64})?$")
# category = "<key>": the portal's tab for the app, in this order. No development tab (owner, 27-10-2026), so no
# [checkout.*] apps either: the Nexus apps in dev/ are the BC250 portal's.
CATEGORIES = {"sustainable": "Sustainable", "graphics": "Graphics", "gaming": "Gaming", "utilities": "Utilities"}
FIELDS = {"name", "summary", "short", "tag", "sha256", "required", "category", "withdrawn", "install", "uninstall",
          "detect", "launch"}


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class AppEntry:
    key: str                                    # "test": folder under apps/; the tag is wp-<key>-v<x.y.z>
    name: str
    summary: str
    tag: str
    sha256: str = ""
    required: bool = False
    category: str = ""                          # a key of CATEGORIES
    install: tuple[str, ...] = ()
    uninstall: tuple[str, ...] = ()
    detect: tuple[str, ...] = ()
    launch: tuple[tuple[str, str], ...] = ()
    short: str = ""                             # the name on its tile; "": the name without "Windows Portable "
    # withdrawn = "<reason>": the pinned release was withdrawn; the portal removes the app. Not for the required app.
    withdrawn: str = ""

    @property
    def version(self) -> str:
        return self.tag.rsplit("-v", 1)[1]

    @property
    def asset(self) -> str:
        """The release asset: <tag>.zip, which unpacks into a folder named <tag>."""
        return f"{self.tag}.zip"


def version_tuple(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(p) for p in version.split("."))
    return major, minor, patch


def _strings(key: str, field: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
        raise ManifestError(f"[apps.{key}] {field} must be a list of non-empty strings")
    return tuple(value)


def _entry(key: str, raw: dict) -> AppEntry:
    unknown = sorted(set(raw) - FIELDS)
    if unknown:
        raise ManifestError(f"[apps.{key}] has unknown fields: {', '.join(unknown)}")
    for field in ("name", "summary", "tag"):
        if not isinstance(raw.get(field), str) or not raw[field].strip():
            raise ManifestError(f"[apps.{key}] needs a non-empty {field}")
    match = _TAG.match(raw["tag"])
    if not match or match["app"] != key:
        raise ManifestError(f"[apps.{key}] tag {raw['tag']!r} is not {TAG_PREFIX}{key}-v<x.y.z>")
    sha = str(raw.get("sha256", "")).lower()
    if not _SHA256.match(sha):
        raise ManifestError(f"[apps.{key}] sha256 must be empty or 64 hex digits")
    short = raw.get("short", "")
    if not isinstance(short, str):
        raise ManifestError(f"[apps.{key}] short must be a string")
    withdrawn = raw.get("withdrawn", "")
    if "withdrawn" in raw and (not isinstance(withdrawn, str) or not withdrawn.strip()):
        raise ManifestError(f"[apps.{key}] withdrawn must say why the release was withdrawn")
    if raw.get("category") not in CATEGORIES:
        raise ManifestError(f"[apps.{key}] category must be one of {', '.join(CATEGORIES)}")
    launch = raw.get("launch", [])
    if not isinstance(launch, list) or not all(isinstance(item, list) and len(item) == 2 and
                                               all(isinstance(s, str) and s for s in item) for item in launch):
        raise ManifestError(f"[apps.{key}] launch must be a list of [label, command] pairs")
    entry = AppEntry(key=key, name=raw["name"], summary=raw["summary"], tag=raw["tag"], sha256=sha,
                     required=bool(raw.get("required", False)), category=raw["category"],
                     install=_strings(key, "install", raw.get("install")),
                     uninstall=_strings(key, "uninstall", raw.get("uninstall")),
                     detect=_strings(key, "detect", raw.get("detect")),
                     launch=tuple((label, command) for label, command in launch), short=short.strip(),
                     withdrawn=withdrawn.strip())
    if entry.required and entry.withdrawn:
        raise ManifestError(f"[apps.{key}] the required app cannot be withdrawn: pin a release that works")
    return entry


def parse(text: str) -> list[AppEntry]:
    """The pinned apps in display order: the required one first, the rest in file order."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"apps.toml is not valid TOML: {exc}") from exc
    if "checkout" in data:
        raise ManifestError("apps.toml: this suite has no development tab, so no [checkout.<name>] apps")
    apps = data.get("apps")
    if not isinstance(apps, dict) or not apps:
        raise ManifestError("apps.toml has no [apps.<name>] tables")
    entries = [_entry(key, raw) for key, raw in apps.items()]
    if [e.key for e in entries if e.required] != ["test"]:
        raise ManifestError("apps.toml: test, and only test, is the required app")
    return sorted(entries, key=lambda e: not e.required)        # stable: file order within each group


def load(path: Path) -> list[AppEntry]:
    return parse(path.read_text(encoding="utf-8"))
