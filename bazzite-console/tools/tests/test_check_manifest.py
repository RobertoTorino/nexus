# SPDX-License-Identifier: GPL-3.0-or-later
"""The suite's manifest checker understands its prefixed tags and required app."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SUITE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("console_check_manifest", SUITE / "tools" / "check_manifest.py")
check_manifest = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = check_manifest
spec.loader.exec_module(check_manifest)


def test_manifest_checker_accepts_the_suite_manifest_without_releases():
    entries = check_manifest.manifest.load(SUITE / "portal" / "apps.toml")
    assert not check_manifest.check_entries(entries, require_tags=False)


def test_manifest_checker_requires_a_portal_version_bump_for_app_pin_changes():
    old = (SUITE / "portal" / "apps.toml").read_text(encoding="utf-8")
    tag = check_manifest.manifest.load(SUITE / "portal" / "apps.toml")[0].tag   # the pin of the day: a patch on it
    major, minor, patch = tag.rpartition("-v")[2].split(".")
    new = old.replace(tag, f"ps5-bazzite-v{major}.{minor}.{int(patch) + 1}")
    errors = check_manifest.bump_errors(old, new, "0.1.0", "0.1.0")
    assert len(errors) == 1
    assert "patch bump" in errors[0]
    assert check_manifest.bump_errors(old, new, "0.1.0", "0.1.1") == []
