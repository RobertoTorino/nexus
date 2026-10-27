# SPDX-License-Identifier: GPL-3.0-or-later
"""portable_portal/manifest.py: the suite's apps.toml and the rules each entry must follow."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORTAL))

from portable_portal import manifest  # noqa: E402

TEST = """
[apps.test]
name = "Windows Portable Test"
summary = "s"
tag = "wp-test-v0.1.0"
required = true
category = "sustainable"
install = ["powershell -File install.ps1"]
uninstall = ["powershell -File install.ps1 --uninstall"]
detect = ["%LOCALAPPDATA%\\\\x\\\\app\\\\X.exe"]
launch = [["Open", "X.exe"]]
"""

OTHER = """
[apps.pcsx2]
name = "Windows Portable PCSX2 Manager"
summary = "s"
tag = "wp-pcsx2-v0.2.0"
category = "gaming"
install = ["i"]
uninstall = ["u"]
detect = ["d"]
"""


def test_the_shipped_manifest_parses_with_test_first():
    entries = manifest.load(PORTAL / "apps.toml")
    assert entries[0].key == "test" and entries[0].required
    assert all(entry.category in manifest.CATEGORIES for entry in entries)


def test_the_required_app_comes_first_and_the_asset_is_a_zip():
    entries = manifest.parse(OTHER + TEST)
    assert [e.key for e in entries] == ["test", "pcsx2"]
    assert entries[1].version == "0.2.0"
    assert entries[1].asset == "wp-pcsx2-v0.2.0.zip"
    assert entries[0].launch == (("Open", "X.exe"),)


def test_a_tag_carries_the_suites_prefix_and_the_apps_key():
    with pytest.raises(manifest.ManifestError, match="is not wp-test-v"):
        manifest.parse(TEST.replace("wp-test-v0.1.0", "test-v0.1.0"))
    with pytest.raises(manifest.ManifestError, match="is not wp-test-v"):
        manifest.parse(TEST.replace("wp-test-v0.1.0", "wp-check-v0.1.0"))


def test_there_is_no_development_tab():
    assert "development" not in manifest.CATEGORIES
    with pytest.raises(manifest.ManifestError, match="category must be one of"):
        manifest.parse(TEST.replace('"sustainable"', '"development"'))
    with pytest.raises(manifest.ManifestError, match="no development tab"):
        manifest.parse(TEST + '\n[checkout.releases]\nname = "r"\n')


def test_test_and_only_test_is_required():
    with pytest.raises(manifest.ManifestError, match="only test, is the required app"):
        manifest.parse(TEST.replace("required = true", "required = false"))
    with pytest.raises(manifest.ManifestError, match="only test, is the required app"):
        manifest.parse(TEST + OTHER.replace('category = "gaming"', 'category = "gaming"\nrequired = true'))


@pytest.mark.parametrize("change, message", [
    (("install = [\"powershell -File install.ps1\"]", "install = []"), "install must be a list"),
    (("detect = [", "detect = [\"\", "), "detect must be a list"),
    (('summary = "s"', 'summary = ""'), "non-empty summary"),
    (('required = true', 'required = true\nsha256 = "abc"'), "sha256 must be"),
    (('required = true', 'required = true\nchanges_board = true'), "unknown fields: changes_board"),
    (('launch = [["Open", "X.exe"]]', 'launch = [["Open"]]'), "launch must be"),
    (('required = true', 'required = true\nwithdrawn = "broken"'), "cannot be withdrawn"),
])
def test_bad_entries_are_refused(change, message):
    with pytest.raises(manifest.ManifestError, match=message):
        manifest.parse(TEST.replace(*change))


def test_invalid_toml_and_an_empty_manifest_are_refused():
    with pytest.raises(manifest.ManifestError, match="not valid TOML"):
        manifest.parse("[apps.test")
    with pytest.raises(manifest.ManifestError, match="no \\[apps"):
        manifest.parse("")
