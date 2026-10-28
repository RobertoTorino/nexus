# SPDX-License-Identifier: GPL-3.0-or-later
"""What a newer portal release brings: its pins compared with the running portal's."""

from __future__ import annotations

from dataclasses import replace

from bc250_core.updates import ReleaseInfo
from portable_portal import MANIFEST
from portable_portal import portal_update as pu
from portable_portal.manifest import AppEntry, load

RELEASE = ReleaseInfo(version="99.0.0", tag="wp-portal-v99.0.0", url="https://example.invalid/r",
                      published="2030-01-01")
PCSX2 = AppEntry(key="pcsx2", name="Windows Portable PCSX2 Manager", summary="s", tag="wp-pcsx2-v0.2.0",
                 category="gaming", install=("i",), uninstall=("u",), detect=("d",))


def text_of(entries) -> str:
    """apps.toml text for *entries*: the shipped file with the test app's tag swapped in."""
    text = MANIFEST.read_text(encoding="utf-8")
    return text.replace(f'tag = "{load(MANIFEST)[0].tag}"', f'tag = "{entries[0].tag}"')


def test_compare_names_the_changed_added_and_withdrawn_apps():
    current = load(MANIFEST)
    new = [replace(current[0], tag="wp-test-v9.0.0"), PCSX2]
    changes = pu.compare(current, new)
    assert [(c.name, c.old, c.new) for c in changes] == [("Windows Portable Test", current[0].version, "9.0.0"),
                                                         ("Windows Portable PCSX2 Manager", "", "0.2.0")]
    assert pu.compare(current, current) == []
    gone = pu.compare(current + [PCSX2], current + [replace(PCSX2, withdrawn="broken")])
    assert [(c.name, c.withdrawn) for c in gone] == [("Windows Portable PCSX2 Manager", "broken")]
    assert pu.compare(current + [replace(PCSX2, withdrawn="broken")],
                      current + [replace(PCSX2, withdrawn="broken")]) == []      # withdrawn already


def test_summary_and_details():
    update = pu.PortalUpdate(RELEASE, [pu.AppChange("Windows Portable Test", "0.1.0", "0.1.1"),
                                       pu.AppChange("Windows Portable PCSX2 Manager", "", "0.2.0")])
    assert update.summary() == "updates Test, adds PCSX2 Manager"
    assert update.details() == "Windows Portable Test: 0.1.0 → 0.1.1\nWindows Portable PCSX2 Manager: new, 0.2.0"
    many = pu.PortalUpdate(RELEASE, [pu.AppChange(f"Windows Portable App {i}", "1.0.0", "1.0.1") for i in range(4)]
                           + [pu.AppChange("Windows Portable Gone", "1.0.0", "1.0.0", withdrawn="broken")])
    assert many.summary() == "withdraws Gone, updates 4 apps"
    assert "Windows Portable Gone: not available any more (broken); removed" in many.details()
    assert pu.PortalUpdate(RELEASE, []).summary() == pu.PortalUpdate(RELEASE).summary() == ""
    tiled = pu.PortalUpdate(RELEASE, [pu.AppChange("Windows Portable HDMI CEC", "", "0.1.0", "HDMI-CEC")])
    assert tiled.summary() == "adds HDMI-CEC"


def test_check_reads_the_pins_at_the_release_tag():
    current = load(MANIFEST)
    urls = []

    def read(url, _agent):
        urls.append(url)
        return text_of([replace(current[0], tag="wp-test-v9.0.0")])

    update = pu.check("owner/repo", "wp-portal-v", current, "ua", release_of=lambda *a, **k: RELEASE, read=read)
    assert urls == ["https://raw.githubusercontent.com/owner/repo/wp-portal-v99.0.0/windows-portable/portal/apps.toml"]
    assert update.release is RELEASE and update.summary() == "updates Test"


def test_check_without_a_release_or_a_readable_manifest():
    current = load(MANIFEST)
    none = ReleaseInfo(error="no release tagged wp-portal-v* yet")
    assert pu.check("o/r", "wp-portal-v", current, "ua", release_of=lambda *a, **k: none).changes is None

    def offline(url, agent):
        raise OSError("offline")
    update = pu.check("o/r", "wp-portal-v", current, "ua", release_of=lambda *a, **k: RELEASE, read=offline)
    assert update.release is RELEASE and update.changes is None and update.summary() == ""
