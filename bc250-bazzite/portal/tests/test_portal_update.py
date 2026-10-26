# SPDX-License-Identifier: GPL-3.0-or-later
"""What a newer portal release brings: its pins compared with the running portal's."""

from __future__ import annotations

from dataclasses import replace

from bc250_core.updates import ReleaseInfo
from bc250_portal import MANIFEST
from bc250_portal import portal_update as pu
from bc250_portal.manifest import load

RELEASE = ReleaseInfo(version="99.0.0", tag="portal-v99.0.0", url="https://example.invalid/r", published="2030-01-01")


def bumped(entries, **tags):
    """The shipped entries with some apps moved to other tags."""
    return [replace(e, tag=tags[e.key]) if e.key in tags else e for e in entries]


def text_of(entries) -> str:
    """apps.toml text for *entries*: the shipped file with their tags swapped in."""
    text = MANIFEST.read_text(encoding="utf-8")
    for old, new in zip(load(MANIFEST), entries):
        text = text.replace(f'tag = "{old.tag}"', f'tag = "{new.tag}"')
    return text


def test_compare_names_the_changed_apps():
    current = load(MANIFEST)
    new = bumped(current, gpu="gpu-v9.0.0", upscaler="upscaler-v9.1.0")
    changes = pu.compare(current, new)
    assert [(c.name, c.new) for c in changes] == [("BC-250 GPU Governor Manager", "9.0.0"),
                                                  ("BC-250 Upscaler Manager", "9.1.0")]
    assert all(c.old for c in changes)
    assert pu.compare(current, current) == []


def test_compare_names_a_withdrawn_app():
    current = load(MANIFEST)
    new = [replace(e, withdrawn="Privacy: shows the account ID.") if e.key == "consoles" else e for e in current]
    changes = pu.compare(current, new)
    assert [(c.name, c.withdrawn) for c in changes] == [("Console Link", "Privacy: shows the account ID.")]
    update = pu.PortalUpdate(RELEASE, changes)
    assert update.summary() == "withdraws Console Link"
    assert update.details() == ("Console Link: not available any more (Privacy: shows the account ID.); "
                                "removed from the board")
    assert pu.compare(new, new) == []                       # withdrawn already: nothing new


def test_summary_and_details():
    two = pu.PortalUpdate(RELEASE, [pu.AppChange("BC-250 ACE Queues", "0.1.0", "0.1.1"),
                                    pu.AppChange("BC-250 Memory Manager", "0.1.0", "0.1.1")])
    assert two.summary() == "updates ACE Queues and Memory Manager"
    assert two.details() == "BC-250 ACE Queues: 0.1.0 → 0.1.1\nBC-250 Memory Manager: 0.1.0 → 0.1.1"
    many = pu.PortalUpdate(RELEASE, [pu.AppChange(f"BC-250 App {i}", "1.0.0", "1.0.1") for i in range(4)]
                           + [pu.AppChange("BC-250 New One", "", "0.1.0")])
    assert many.summary() == "updates 4 apps, adds New One"
    assert "BC-250 New One: new, 0.1.0" in many.details()
    assert pu.PortalUpdate(RELEASE, []).summary() == pu.PortalUpdate(RELEASE).summary() == ""
    tiled = pu.PortalUpdate(RELEASE, [pu.AppChange("HDMI CEC Manager", "", "0.1.0", "HDMI-CEC")])
    assert tiled.summary() == "adds HDMI-CEC"


def test_check_reads_the_pins_at_the_release_tag():
    current = load(MANIFEST)
    urls = []

    def read(url, _agent):
        urls.append(url)
        return text_of(bumped(current, gpu="gpu-v9.0.0"))

    update = pu.check("owner/repo", "portal-v", current, "ua", release_of=lambda *a, **k: RELEASE, read=read)
    assert urls == ["https://raw.githubusercontent.com/owner/repo/portal-v99.0.0/bc250-bazzite/portal/apps.toml"]
    assert update.release is RELEASE and update.summary() == "updates GPU Governor Manager"


def test_check_falls_back_to_the_manifest_at_the_root_for_a_tag_from_before_the_move():
    """A portal tagged before the suite moved into bc250-bazzite/ has its apps.toml at the root of the repository."""
    current = load(MANIFEST)
    urls = []

    def read(url, _agent):
        urls.append(url)
        if "bc250-bazzite" in url:
            raise OSError("404")
        return text_of(bumped(current, gpu="gpu-v9.0.0"))

    update = pu.check("owner/repo", "portal-v", current, "ua", release_of=lambda *a, **k: RELEASE, read=read)
    assert urls == ["https://raw.githubusercontent.com/owner/repo/portal-v99.0.0/bc250-bazzite/portal/apps.toml",
                    "https://raw.githubusercontent.com/owner/repo/portal-v99.0.0/portal/apps.toml"]
    assert update.summary() == "updates GPU Governor Manager"


def test_check_without_details_or_release():
    current = load(MANIFEST)

    def offline(_url, _agent):
        raise OSError("offline")

    assert pu.check("o/r", "portal-v", current, "ua", release_of=lambda *a, **k: RELEASE, read=offline).changes is None
    assert pu.check("o/r", "portal-v", current, "ua", release_of=lambda *a, **k: RELEASE,
                    read=lambda *_: "not toml [").changes is None
    empty = ReleaseInfo(error="no connection (offline)")
    asked = []
    result = pu.check("o/r", "portal-v", current, "ua", release_of=lambda *a, **k: empty,
                      read=lambda *a: asked.append(a) or "")
    assert result.release is empty and result.changes is None and asked == []
