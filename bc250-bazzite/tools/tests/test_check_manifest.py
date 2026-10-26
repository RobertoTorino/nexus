# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/check_manifest.py: the portal version bump rule and the tag rules."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("check_manifest", TOOLS / "check_manifest.py")
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)

BASE = """
[apps.check]
name = "BT"
summary = "s"
tag = "check-v1.2.3"
required = true
install = ["bash install.sh"]
uninstall = ["bash install.sh --uninstall"]
detect = ["~/.local/bin/bt"]

[apps.gpu]
name = "Gov"
summary = "s"
tag = "gpu-v0.4.0"
install = ["bash install.sh"]
uninstall = ["bash install.sh --uninstall"]
detect = ["~/.local/bin/g"]
"""


@pytest.mark.parametrize("old, new, level", [
    ("1.2.3", "1.2.3", 0), ("1.2.3", "1.2.4", 1), ("1.2.3", "1.3.0", 2), ("1.2.3", "2.0.0", 3),
    ("1.9.9", "1.10.0", 2), ("1.2.3", "1.2.2", -1),
])
def test_bump_level(old, new, level):
    assert cm.bump_level(old, new) == level


def errors(new_text: str, old_portal: str, new_portal: str) -> list[str]:
    return cm.bump_errors(BASE, new_text, old_portal, new_portal)


def test_unchanged_needs_nothing():
    assert errors(BASE, "0.1.0", "0.1.0") == []


@pytest.mark.parametrize("app_tag, portal_new, ok", [
    ("gpu-v0.4.1", "0.1.1", True),         # app patch -> portal patch is enough
    ("gpu-v0.4.1", "0.1.0", False),        # ... but some bump is needed
    ("gpu-v0.5.0", "0.1.1", False),        # app minor -> portal patch is too small
    ("gpu-v0.5.0", "0.2.0", True),
    ("gpu-v1.0.0", "0.2.0", False),        # app major -> portal major
    ("gpu-v1.0.0", "1.0.0", True),
])
def test_portal_bump_at_least_app_bump(app_tag, portal_new, ok):
    result = errors(BASE.replace("gpu-v0.4.0", app_tag), "0.1.0", portal_new)
    assert (result == []) is ok, result
    if not ok:
        assert "portal/VERSION needs at least" in result[0]


def test_largest_app_bump_counts():
    new = BASE.replace("gpu-v0.4.0", "gpu-v0.4.1").replace("check-v1.2.3", "check-v1.3.0")
    assert errors(new, "0.1.0", "0.1.1")                    # minor needed because of check
    assert errors(new, "0.1.0", "0.2.0") == []


def test_other_changes_need_a_patch_bump():
    new = BASE.replace('summary = "s"\ntag = "gpu', 'summary = "changed"\ntag = "gpu')
    assert errors(new, "0.1.0", "0.1.0")
    assert errors(new, "0.1.0", "0.1.1") == []


def test_added_app_needs_minor():
    new = BASE + BASE.split("[apps.gpu]")[1].replace("gpu", "helixsr").join(["\n[apps.helixsr]", ""])
    assert errors(new, "0.1.0", "0.1.1")
    assert errors(new, "0.1.0", "0.2.0") == []


def test_withdrawn_app_needs_minor():
    new = BASE.replace('name = "Gov"', 'name = "Gov"\nwithdrawn = "Privacy: shows the account ID."')
    assert errors(new, "0.1.0", "0.1.1") and "gpu was withdrawn" in errors(new, "0.1.0", "0.1.1")[0]
    assert errors(new, "0.1.0", "0.2.0") == []
    back = cm.bump_errors(new, BASE, "0.2.0", "0.2.1")                  # taken back: a minor bump too
    assert back and "gpu was no longer withdrawn" in back[0]


def test_app_moving_back_is_refused():
    result = errors(BASE.replace("gpu-v0.4.0", "gpu-v0.3.9"), "0.1.0", "1.0.0")
    assert result and "moves back" in result[0]


def test_latest_portal_tag():
    assert cm.latest_portal_tag(["portal-v1.9.0", "ace-v0.2.0", "portal-v1.10.0", "portal-v1.10", "portal-v1.2.9"]) \
        == "portal-v1.10.0"
    assert cm.latest_portal_tag([]) == "" and cm.latest_portal_tag(["ace-v0.2.0"]) == ""


def test_bump_is_counted_since_the_last_portal_release(tmp_path, monkeypatch):
    """The owner's case of 17-10-2026: the push with the apps' releases carried the portal bump (1.12.0 -> 1.13.0),
    and the next push, with their checksums pinned, was asked for 1.13.1 against the last push. A portal version
    that is not tagged yet may still change what it pins, so the comparison is with the last portal tag; the last
    push only while there is none."""
    new_text = BASE.replace('tag = "gpu-v0.4.0"', 'tag = "gpu-v0.4.1"')
    (tmp_path / "portal").mkdir()
    (tmp_path / "portal/apps.toml").write_text(new_text + 'sha256 = ""\n')         # the checksum pinned later
    (tmp_path / "portal/VERSION").write_text("1.1.0\n")
    monkeypatch.setattr(cm, "SUITE", tmp_path)
    refs = {"pushed:portal/apps.toml": new_text, "pushed:portal/VERSION": "1.1.0\n",
            "portal-v1.0.0:portal/apps.toml": BASE}
    tags = ["portal-v0.9.0", "portal-v1.0.0"]

    def fake_git(*args):
        if args[:2] == ("tag", "--list"):
            return "".join(f"{tag}\n" for tag in tags)
        if args[0] == "show":
            return refs.get(args[1])
        raise AssertionError(args)
    monkeypatch.setattr(cm, "git", fake_git)
    assert cm.reference("pushed") == ("portal-v1.0.0", BASE, "1.0.0")
    assert cm.check_bump("pushed") == []                   # 1.0.0 -> 1.1.0 covers governor's patch and the checksum
    (tmp_path / "portal/VERSION").write_text("1.0.0\n")
    assert cm.check_bump("pushed") == ["portal/apps.toml changed since portal-v1.0.0 (apps.toml changed): "
                                       "portal/VERSION needs at least a patch bump, but goes 1.0.0 -> 1.0.0"]
    tags.clear()                                           # no portal release yet: the last push is the reference
    assert cm.reference("pushed") == ("pushed", new_text, "1.1.0")
    assert cm.check_bump("pushed") == ["portal/apps.toml changed since pushed (apps.toml changed): portal/VERSION "
                                       "needs at least a patch bump, but goes 1.1.0 -> 1.0.0"]


def test_shipped_manifest_passes_without_required_tags():
    entries = cm.manifest.load(cm.SUITE / cm.MANIFEST)
    assert cm.check_entries(entries, require_tags=False) == []
    assert {"mtool", "package"} <= {entry.key for entry in entries if entry.development}
    checkout = cm.manifest.load_checkout(cm.SUITE / cm.MANIFEST)
    assert cm.check_checkout_entries(checkout) == []
    assert [(entry.key, entry.folder) for entry in checkout] == [
        ("suite", "apps/suite"), ("installer-tests", "tools/installer-tests/gui")]


def test_every_app_needs_a_category():
    entries = [e for e in cm.manifest.load(cm.SUITE / cm.MANIFEST) if e.key != "gpu"]
    gpu = cm.manifest.AppEntry(key="gpu", name="Gov", summary="s", tag="gpu-v0.0.1")       # an older manifest's
    errors = cm.check_entries([*entries, gpu], require_tags=False)
    assert [e for e in errors if "category" in e] == [
        "[apps.gpu] needs a category: one of sustainable, graphics, gaming, utilities, development"]


def test_checkout_tables_match_the_checkout_only_folders():
    entry = cm.manifest.AppEntry(key="gpu", name="Gov", summary="s", tag="", checkout_only=True)
    errors = cm.check_checkout_entries([entry])
    assert any("suite has .checkout-only" in e for e in errors)
    assert any("[checkout.gpu]: apps/gpu has no .checkout-only" in e for e in errors)
    elsewhere = cm.manifest.AppEntry(key="gui", name="G", summary="s", tag="", checkout_only=True, folder="tools")
    assert any("[checkout.gui]: tools has no .checkout-only" in e for e in cm.check_checkout_entries([elsewhere]))


def test_checkout_table_change_needs_a_patch_bump():
    table = ('\n[checkout.suite]\nname = "SR"\nsummary = "s"\ninstall = ["bash install.sh"]\n'
             'uninstall = ["bash install.sh --uninstall"]\ndetect = ["~/.local/bin/r"]\n')
    assert errors(BASE + table, "0.1.0", "0.1.0")
    assert errors(BASE + table, "0.1.0", "0.1.1") == []
