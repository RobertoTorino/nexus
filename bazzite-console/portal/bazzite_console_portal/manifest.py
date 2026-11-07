# SPDX-License-Identifier: GPL-3.0-or-later
"""The apps listed by the Bazzite Console Suite portal."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_TAG = re.compile(r"^ps5-(?P<app>[a-z0-9-]+)-v(?P<version>\d+\.\d+\.\d+)$")
CATEGORIES = {"sustainable": "Sustainable", "graphics": "Graphics", "gaming": "Gaming", "utilities": "Utilities",
              "media": "Media"}
RENAMED: dict[str, str] = {}


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class AppEntry:
    key: str
    name: str
    summary: str
    tag: str
    sha256: str = ""
    required: bool = False
    category: str = ""
    install: tuple[str, ...] = ()
    uninstall: tuple[str, ...] = ()
    detect: tuple[str, ...] = ()
    launch: tuple[tuple[str, str], ...] = ()
    withdrawn: str = ""
    changes_board: bool = False
    board_change: str = ""
    short: str = ""

    @property
    def version(self) -> str:
        return _TAG.fullmatch(self.tag)["version"]

    @property
    def asset(self) -> str:
        return f"{self.tag}.tar.gz"


@dataclass(frozen=True)
class CardEntry:
    key: str
    name: str
    summary: str
    category: str
    icon: str
    flatpak_id: str
    flatpak_name: str
    launch: tuple[str, ...]


def version_tuple(version: str) -> tuple[int, int, int]:
    return tuple(map(int, version.split(".")))


def parse(text: str) -> list[AppEntry]:
    try:
        apps = tomllib.loads(text).get("apps", {})
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"apps.toml is not valid TOML: {exc}") from exc
    if not isinstance(apps, dict) or not apps:
        raise ManifestError("apps.toml has no [apps.<name>] tables")
    entries = []
    for key, raw in apps.items():
        match = _TAG.fullmatch(raw.get("tag", "")) if isinstance(raw, dict) else None
        if not match or match["app"] != key:
            raise ManifestError(f"[apps.{key}] tag must be ps5-{key}-v<x.y.z>")
        if not all(isinstance(raw.get(field), str) and raw[field].strip() for field in ("name", "summary")):
            raise ManifestError(f"[apps.{key}] needs a name and summary")
        if raw.get("category") not in CATEGORIES:
            raise ManifestError(f"[apps.{key}] needs a valid category")
        for field in ("install", "uninstall", "detect"):
            values = raw.get(field)
            if not isinstance(values, list) or not values or not all(isinstance(item, str) and item for item in values):
                raise ManifestError(f"[apps.{key}] {field} must be a non-empty list of strings")
        required = raw.get("required", False)
        sha256 = raw.get("sha256", "")
        launch = raw.get("launch", [])
        changes_board = raw.get("changes_board", False)
        board_change = raw.get("board_change", "")
        withdrawn = raw.get("withdrawn", "")
        short = raw.get("short", "")
        if not isinstance(required, bool) or not isinstance(changes_board, bool) or \
                not all(isinstance(value, str) for value in (sha256, board_change, withdrawn, short)):
            raise ManifestError(f"[apps.{key}] has an invalid boolean or text field")
        if sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
            raise ManifestError(f"[apps.{key}] sha256 must be 64 hexadecimal characters")
        if not isinstance(launch, list) or any(
                not isinstance(item, list) or len(item) != 2 or not all(isinstance(part, str) for part in item)
                for item in launch):
            raise ManifestError(f"[apps.{key}] launch must be a list of two-string lists")
        entries.append(AppEntry(key=key, name=raw["name"], summary=raw["summary"], tag=raw["tag"],
                                sha256=sha256, required=required,
                                category=raw["category"], install=tuple(raw["install"]),
                                uninstall=tuple(raw["uninstall"]), detect=tuple(raw["detect"]),
                                launch=tuple(tuple(item) for item in launch),
                                withdrawn=withdrawn, changes_board=changes_board, short=short.strip(),
                                board_change=board_change))
    if sum(entry.required for entry in entries) != 1:
        raise ManifestError("apps.toml must have exactly one required app")
    return sorted(entries, key=lambda entry: not entry.required)


def load(path: Path) -> list[AppEntry]:
    return parse(path.read_text(encoding="utf-8"))


def parse_cards(text: str) -> list[CardEntry]:
    try:
        cards = tomllib.loads(text).get("cards", {})
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"cards.toml is not valid TOML: {exc}") from exc
    if not isinstance(cards, dict):
        raise ManifestError("cards.toml has no [cards.<name>] tables")
    entries = []
    for key, raw in cards.items():
        if not re.fullmatch(r"[a-z0-9-]+", key) or not isinstance(raw, dict):
            raise ManifestError(f"[cards.{key}] is invalid")
        if not all(isinstance(raw.get(field), str) and raw[field].strip() for field in ("name", "summary")):
            raise ManifestError(f"[cards.{key}] needs a name and summary")
        category, icon = raw.get("category"), raw.get("icon")
        flatpak_id, flatpak_name, launch = raw.get("flatpak_id"), raw.get("flatpak_name"), raw.get("launch")
        if not isinstance(category, str) or category not in CATEGORIES:
            raise ManifestError(f"[cards.{key}] needs a valid category")
        if not isinstance(icon, str) or Path(icon).name != icon or not icon.endswith(".webp"):
            raise ManifestError(f"[cards.{key}] icon must be a WebP filename")
        if not isinstance(flatpak_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]+", flatpak_id) or \
                not isinstance(flatpak_name, str) or not flatpak_name.strip():
            raise ManifestError(f"[cards.{key}] needs a Flatpak ID and name")
        if not isinstance(launch, list) or not launch or \
                not all(isinstance(part, str) and part for part in launch):
            raise ManifestError(f"[cards.{key}] launch must be a non-empty list of strings")
        if launch[:3] != ["flatpak", "run", flatpak_id]:
            raise ManifestError(f"[cards.{key}] launch must run its required Flatpak")
        entries.append(CardEntry(key, raw["name"], raw["summary"], category, icon, flatpak_id, flatpak_name.strip(),
                                 tuple(launch)))
    return entries


def load_cards(path: Path) -> list[CardEntry]:
    cards = parse_cards(path.read_text(encoding="utf-8"))
    for card in cards:
        if not (path.parent / "images" / "cards" / card.icon).is_file():
            raise ManifestError(f"[cards.{card.key}] icon does not exist: {card.icon}")
    return cards
