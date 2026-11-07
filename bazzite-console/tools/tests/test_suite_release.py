# SPDX-License-Identifier: GPL-3.0-or-later
"""The Bazzite Console Suite's release planner and manifest pinning."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SUITE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("console_suite_release", SUITE / "tools" / "suite_release.py")
suite_release = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = suite_release
spec.loader.exec_module(suite_release)


def test_plans_hand_tagged_app_and_portal_releases():
    assert suite_release.plan("", "0.1.0", tag="ps5-bazzite-v0.1.0") == {
        "apps": ["ps5-bazzite-v0.1.0"], "portal": "", "draft": False}
    assert suite_release.plan("", "0.1.0", tag="ps5-portal-v0.1.0") == {
        "apps": [], "portal": "ps5-portal-v0.1.0", "draft": False}


def test_nexus_release_builds_unreleased_apps_and_a_draft_portal():
    text = (SUITE / "portal" / "apps.toml").read_text(encoding="utf-8")
    found = suite_release.plan(text, "0.1.0", released=lambda tag: tag == "ps5-old-v0.1.0")
    assert found == {
        "apps": [
            "ps5-bazzite-v0.1.0",
            "ps5-rpcs3-v0.1.0",
            "ps5-consoles-v0.1.0",
            "ps5-clb-v0.1.0",
            "ps5-shadps4-v0.1.0",
            "ps5-decky-v0.1.0",
            "ps5-datstation-v0.1.0",
            "ps5-ppsspp-v0.1.0",
            "ps5-pcsx2-v0.1.0",
            "ps5-vita3k-v0.1.0",
            "ps5-xenia-v0.1.0",
            "ps5-sftp-v0.1.0",
            "ps5-hdcam-v0.1.0",
            "ps5-hdcontrol-v0.1.0",
            "ps5-ssd-v0.1.0",
        ],
        "portal": "ps5-portal-v0.1.0",
        "draft": True,
    }


def test_pin_changes_only_the_matching_apps_checksum():
    text = (SUITE / "portal" / "apps.toml").read_text(encoding="utf-8")
    digest = "a" * 64
    result = suite_release.pin(text, "ps5-bazzite-v0.1.0", digest)
    assert f'sha256 = "{digest}"' in result
    assert suite_release.pin(result, "ps5-bazzite-v0.1.0", "b" * 64).replace(
        'sha256 = "' + "b" * 64 + '"', 'sha256 = "' + digest + '"') == result


def test_checksum_lookup_requires_the_requested_asset():
    sums = f'{"c" * 64}  ps5-bazzite-v0.1.0.tar.gz\n'
    assert suite_release.sha256_of(sums, "ps5-bazzite-v0.1.0.tar.gz") == "c" * 64
    try:
        suite_release.sha256_of(sums, "other.tar.gz")
    except ValueError as exc:
        assert "does not list" in str(exc)
    else:
        raise AssertionError("an absent asset checksum was accepted")
