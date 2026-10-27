# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from bc250_portal import MANIFEST
from bc250_portal.manifest import CATEGORIES, LEGACY_CATEGORIES, ManifestError, load, parse
from conftest import SUITE

MINIMAL = """
[apps.compute]
name = "CU"
summary = "s"
tag = "compute-v1.2.3"
install = ["bash a.sh"]
uninstall = ["bash b.sh"]
detect = ["~/.local/bin/x"]
launch = [["Bisect", "~/.local/bin/x"], ["Unlock", "~/.local/bin/y"]]

[apps.check]
name = "BT"
summary = "s"
tag = "check-v0.1.0"
required = true
install = ["bash install.sh"]
uninstall = ["bash install.sh --uninstall"]
detect = ["~/.local/bin/bt"]
"""


def test_required_first_then_file_order():
    entries = parse(MINIMAL)
    assert [e.key for e in entries] == ["check", "compute"]
    cu = entries[1]
    assert (cu.version, cu.asset) == ("1.2.3", "compute-v1.2.3.tar.gz")
    assert cu.launch == (("Bisect", "~/.local/bin/x"), ("Unlock", "~/.local/bin/y"))
    assert not cu.required and not cu.changes_board and cu.sha256 == ""


@pytest.mark.parametrize("change, message", [
    (('tag = "compute-v1.2.3"', 'tag = "cores-bisect-v1.2.3"'), "is not compute-v"),
    (('tag = "compute-v1.2.3"', 'tag = "compute-v1.2"'), "is not compute-v"),
    (('install = ["bash a.sh"]', 'install = []'), "must not be empty"),
    (('install = ["bash a.sh"]', 'install = "bash a.sh"'), "list of non-empty strings"),
    (('launch = [["Bisect", "~/.local/bin/x"], ["Unlock", "~/.local/bin/y"]]', 'launch = [["Bisect"]]'), "pairs"),
    (("required = true", "required = false"), "required app"),
    (('name = "CU"', 'name = ""'), "non-empty name"),
])
def test_rejects(change, message):
    with pytest.raises(ManifestError, match=message):
        parse(MINIMAL.replace(*change, 1))


def test_a_withdrawn_release():
    assert parse(MINIMAL)[1].withdrawn == ""
    withdrawn = parse(MINIMAL.replace('name = "CU"', 'name = "CU"\nwithdrawn = " Shows the account ID. "', 1))
    assert withdrawn[1].withdrawn == "Shows the account ID." and withdrawn[1].tag == "compute-v1.2.3"
    with pytest.raises(ManifestError, match="must say why"):
        parse(MINIMAL.replace('name = "CU"', 'name = "CU"\nwithdrawn = ""', 1))
    with pytest.raises(ManifestError, match="required app cannot be withdrawn"):
        parse(MINIMAL.replace('name = "BT"', 'name = "BT"\nwithdrawn = "broken"', 1))


def test_a_category_for_its_tab():
    assert parse(MINIMAL)[1].category == ""                                # a manifest from before categories
    cu = parse(MINIMAL.replace('name = "CU"', 'name = "CU"\ncategory = "gaming"', 1))[1]
    assert cu.category == "gaming"
    with pytest.raises(ManifestError, match="category must be one of sustainable, graphics, gaming, utilities$"):
        parse(MINIMAL.replace('name = "CU"', 'name = "CU"\ncategory = "games"', 1))


def test_no_development_tab_but_earlier_manifests_still_read():
    """The Development tab went with the checkout-only apps (owner, 27-10-2026). A manifest of an earlier portal
    release, which the tools compare with, still reads: its development apps, and its [checkout.*] tables unread."""
    assert "development" not in CATEGORIES and LEGACY_CATEGORIES == ("development",)
    earlier = parse(MINIMAL.replace('name = "CU"', 'name = "CU"\ncategory = "development"', 1) + CHECKOUT)
    assert [(e.key, e.category) for e in earlier] == [("check", ""), ("compute", "development")]


def test_shipped_manifest_has_a_category_for_every_app():
    entries = load(MANIFEST)
    assert all(e.category in CATEGORIES for e in entries)
    assert {"mtool", "package", "ncgui"} <= {e.key for e in entries if e.category == "utilities"}
    assert "[checkout." not in MANIFEST.read_text(encoding="utf-8")           # only released apps


def test_short_name_for_the_tile():
    assert parse(MINIMAL)[1].short == ""
    assert parse(MINIMAL.replace('name = "CU"', 'name = "CU"\nshort = "C-U"', 1))[1].short == "C-U"
    with pytest.raises(ManifestError, match="short must be a string"):
        parse(MINIMAL.replace('name = "CU"', 'name = "CU"\nshort = 1', 1))


def test_bad_sha_and_toml():
    with pytest.raises(ManifestError, match="sha256"):
        parse(MINIMAL.replace('summary = "s"\ntag = "co', 'summary = "s"\nsha256 = "abc"\ntag = "co', 1))
    with pytest.raises(ManifestError, match="not valid TOML"):
        parse("[apps")


def test_shipped_manifest_lists_every_app_with_bazzite_test_first():
    entries = load(MANIFEST)
    assert entries[0].key == "check" and entries[0].required
    assert sum(e.required for e in entries) == 1
    apps = {p.name for p in (SUITE / "apps").iterdir() if p.is_dir() and not (p / ".standalone").is_file()}
    assert {e.key for e in entries} == apps


def test_shipped_manifest_install_scripts_exist():
    for entry in load(MANIFEST):
        for command in (*entry.install, *entry.uninstall):
            script = command.split()[-1] if command.split()[-1].endswith(".sh") else \
                [w for w in command.split() if w.endswith(".sh")][0]
            assert (SUITE / "apps" / entry.key / script).is_file(), f"{entry.key}: {command}"


def test_board_changing_apps_are_marked():
    marked = {e.key for e in load(MANIFEST) if e.changes_board}
    assert {"compute", "cores", "oc", "acpi", "gpu"} <= marked
    assert "check" not in marked


CHECKOUT = """
[checkout.gui]
name = "GUI"
summary = "s"
install = ["bash install.sh"]
uninstall = ["bash install.sh --uninstall"]
detect = ["~/.local/bin/gui"]
"""
