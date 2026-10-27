# SPDX-License-Identifier: GPL-3.0-or-later
"""windows-portable/tools/check_manifest.py: the portal version bump rule and the tag rules, with the suite's wp-
tags."""

from __future__ import annotations

import importlib.util
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("portable_check_manifest", TOOLS / "check_manifest.py")
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)

BASE = """
[apps.test]
name = "Windows Portable Test"
summary = "s"
tag = "wp-test-v0.1.0"
required = true
category = "sustainable"
install = ["i"]
uninstall = ["u"]
detect = ["d"]
"""

PCSX2 = """
[apps.pcsx2]
name = "Windows Portable PCSX2 Manager"
summary = "s"
tag = "wp-pcsx2-v0.2.0"
category = "gaming"
install = ["i"]
uninstall = ["u"]
detect = ["d"]
"""


def test_the_shipped_manifest_passes():
    assert cm.main([]) == 0


def test_bump_levels():
    assert cm.bump_level("0.1.0", "0.1.1") == 1
    assert cm.bump_level("0.1.4", "0.2.0") == 2
    assert cm.bump_level("0.9.0", "1.0.0") == 3
    assert cm.bump_level("0.2.0", "0.2.0") == 0
    assert cm.bump_level("0.2.0", "0.1.9") == -1


def test_an_app_bump_needs_a_portal_bump_as_large():
    new = BASE.replace("wp-test-v0.1.0", "wp-test-v0.2.0")
    assert cm.required_bump(BASE, new) == (2, "test 0.1.0 -> 0.2.0")
    assert cm.bump_errors(BASE, new, "0.1.0", "0.2.0") == []
    errors = cm.bump_errors(BASE, new, "0.1.0", "0.1.1", since="wp-portal-v0.1.0")
    assert errors and "since wp-portal-v0.1.0" in errors[0] and "minor bump" in errors[0]


def test_an_added_app_needs_a_minor_bump_and_a_checksum_a_patch():
    assert cm.required_bump(BASE, BASE + PCSX2) == (2, "pcsx2 was added")
    assert cm.required_bump(BASE, BASE.replace('required = true', 'required = true\nsha256 = "' + "a" * 64 + '"')) \
        == (1, "apps.toml changed")
    assert cm.required_bump(BASE, BASE) == (0, "")


def test_moving_back_to_an_older_release_is_refused():
    older = BASE.replace("wp-test-v0.1.0", "wp-test-v0.0.9")
    assert cm.bump_errors(BASE, older, "0.1.0", "0.2.0") == ["test moves back from wp-test-v0.1.0 to wp-test-v0.0.9"]


def test_the_latest_portal_tag_is_the_suites_by_version():
    tags = ["wp-portal-v0.9.0", "wp-portal-v0.10.0", "portal-v10.1.0", "wp-test-v0.1.0"]
    assert cm.latest_portal_tag(tags) == "wp-portal-v0.10.0"
    assert cm.latest_portal_tag(["portal-v10.1.0"]) == ""          # the BC250 suite's portal is not this one


def test_a_missing_tag_is_accepted_only_as_the_next_release(monkeypatch):
    monkeypatch.setattr(cm, "tag_exists", lambda tag: False)
    version = (cm.SUITE / "apps" / "test" / "VERSION").read_text(encoding="utf-8").strip()
    entries = cm.manifest.parse(BASE.replace("wp-test-v0.1.0", f"wp-test-v{version}"))
    assert cm.check_entries(entries, require_tags=False) == []
    assert cm.check_entries(entries, require_tags=True) == [f"wp-test-v{version} does not exist: release it "
                                                            "before the portal"]
    stale = cm.manifest.parse(BASE.replace("wp-test-v0.1.0", "wp-test-v9.9.9"))
    assert "is not the next release either" in cm.check_entries(stale, require_tags=False)[0]


def test_every_app_folder_is_listed(monkeypatch):
    monkeypatch.setattr(cm, "tag_exists", lambda tag: True)
    errors = cm.check_entries(cm.manifest.parse(BASE + PCSX2), require_tags=False)
    assert errors == [f"{cm.MANIFEST} lists pcsx2, which has no apps/pcsx2"]


def test_the_reference_reads_the_suites_files_at_the_base(monkeypatch):
    calls = []

    def fake_git(*args):
        calls.append(args)
        return "" if args[0] == "tag" else "0.1.0\n"

    monkeypatch.setattr(cm, "git", fake_git)
    ref, _, version = cm.reference("origin/main")
    assert (ref, version) == ("origin/main", "0.1.0")
    shown = [args[1] for args in calls if args[0] == "show"]
    assert shown == ["origin/main:windows-portable/portal/VERSION", "origin/main:windows-portable/portal/apps.toml"]
