# SPDX-License-Identifier: GPL-3.0-or-later
"""The wiki's navigation lists the apps the portal lists, by category and by name within each."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

SUITE = Path(__file__).resolve().parents[2]
APPS = tomllib.loads((SUITE / "portal" / "apps.toml").read_text(encoding="utf-8"))["apps"]
CATEGORIES = ("sustainable", "graphics", "gaming", "utilities")     # the navigation's headers, in the portal's order


def test_the_navigation_lists_the_apps_by_category_in_alphabetical_order():
    nav = (SUITE / "mkdocs.yml").read_text(encoding="utf-8")
    found: dict[str, list[str]] = {}
    for line in nav.splitlines():
        if header := re.fullmatch(r" {6}- (\w+):", line):
            found[header[1].lower()] = []
        elif entry := re.fullmatch(r" {10}- (.+): apps/([a-z0-9]+)\.md", line):
            found[list(found)[-1]].append(entry[2])
            assert entry[1].strip('"') == APPS[entry[2]]["name"], line
    assert tuple(found) == CATEGORIES
    for category, listed in found.items():
        apps = [key for key, app in APPS.items() if app["category"] == category]
        assert listed == sorted(apps, key=lambda key: APPS[key]["name"].casefold()), category
