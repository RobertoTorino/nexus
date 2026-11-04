# SPDX-License-Identifier: GPL-3.0-or-later
"""suite_release.py, the release workflow's plan and pin steps, with GitHub stood in for: a tag pushed by hand, a
Nexus release with some apps out already, a draft made anew, apps without a portal bump, the Windows executables'
tags, and the pins written into both copies of apps.toml."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("suite_release", TOOLS / "suite_release.py")
sr = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sr
spec.loader.exec_module(sr)

SHA = "ab" * 32
MANIFEST = """# a comment that stays
[apps.check]
name = "BC-250 Bazzite Test"
tag = "check-v3.0.1"
sha256 = "%s"
required = true

[apps.sftp]
name = "SFTP Tools"
tag = "sftp-v3.1.0"
sha256 = ""

[apps.xenia]
name = "Xenia Manager"
tag = "xenia-v1.0.1"
withdrawn = "a reason"

[apps.new]
name = "New Manager"
tag = "new-v0.1.0"
""" % SHA
WINDOWS = {"sftp"}


def test_a_tag_pushed_by_hand_is_that_release_published_at_once():
    assert sr.plan(MANIFEST, "4.1.0", tag="sftp-v3.1.0", windows=WINDOWS) == {
        "apps": ["sftp-v3.1.0"], "windows": ["sftp-v3.1.0"], "portal": "", "draft": False}
    assert sr.plan(MANIFEST, "4.1.0", tag="new-v0.1.0") == {"apps": ["new-v0.1.0"], "windows": [], "portal": "",
                                                            "draft": False}
    assert sr.plan(MANIFEST, "4.1.0", tag="portal-v4.1.0") == {"apps": [], "windows": [], "portal": "portal-v4.1.0",
                                                               "draft": False}
    with pytest.raises(ValueError, match="is not <app>-v"):
        sr.plan(MANIFEST, "4.1.0", tag="sftp-3.1.0")


def test_a_nexus_release_brings_the_unreleased_pins_and_a_draft_portal():
    out = {"check-v3.0.1", "portal-v4.0.0"}
    found = sr.plan(MANIFEST, "4.1.0", released=out.__contains__, windows=WINDOWS)
    assert found == {"apps": ["sftp-v3.1.0", "new-v0.1.0"], "windows": ["sftp-v3.1.0"], "portal": "portal-v4.1.0",
                     "draft": True}
    assert sr.output_lines(found) == ['apps=["sftp-v3.1.0", "new-v0.1.0"]', 'windows=["sftp-v3.1.0"]',
                                      "portal=portal-v4.1.0", "draft=true"]
    assert json.loads(sr.output_lines(found)[0].removeprefix("apps=")) == found["apps"]


def test_the_windows_executables_are_the_nexus_tools_list():
    """The apps with a Windows executable come from tools/build_windows_exe.py, so release.yml lists none itself."""
    assert sr.windows_apps() == {"sftp"}


def test_a_withdrawn_app_is_not_built():
    found = sr.plan(MANIFEST, "4.1.0", released=lambda tag: False)
    assert "xenia-v1.0.1" not in found["apps"]


def test_a_portal_out_already_releases_nothing_but_apps_need_a_bump():
    everything = {"check-v3.0.1", "sftp-v3.1.0", "new-v0.1.0", "portal-v4.0.0"}
    assert sr.plan(MANIFEST, "4.0.0", released=everything.__contains__) == {"apps": [], "windows": [], "portal": "",
                                                                           "draft": True}
    with pytest.raises(ValueError, match="bump portal/VERSION"):
        sr.plan(MANIFEST, "4.0.0", released={"portal-v4.0.0"}.__contains__)


def test_only_the_portal_a_withdrawal_for_instance():
    everything = {"check-v3.0.1", "sftp-v3.1.0", "new-v0.1.0"}
    assert sr.plan(MANIFEST, "4.1.0", released=everything.__contains__) == {"apps": [], "windows": [],
                                                                           "portal": "portal-v4.1.0", "draft": True}


def test_pin_sets_only_the_sha256_line_of_that_app():
    other = "cd" * 32
    text = sr.pin(MANIFEST, "sftp-v3.1.0", other)
    assert f'tag = "sftp-v3.1.0"\nsha256 = "{other}"\n' in text
    assert text.replace(other, "") == MANIFEST                      # nothing else changed, the comment included
    text = sr.pin(text, "new-v0.1.0", other)                        # an app without a sha256 line gets one
    assert text.endswith(f'tag = "new-v0.1.0"\nsha256 = "{other}"\n')


def test_pin_refuses_a_tag_the_manifest_does_not_pin():
    with pytest.raises(ValueError, match="does not pin sftp-v3.0.0"):
        sr.pin(MANIFEST, "sftp-v3.0.0", SHA)
    with pytest.raises(ValueError, match="no app for gone-v1.0.0"):
        sr.pin(MANIFEST, "gone-v1.0.0", SHA)


def test_the_checksum_comes_from_the_releases_own_sha256sums():
    sums = f"{'EF' * 32} *sftp-v3.1.0.tar.gz\n{SHA}  other.tar.gz\n"
    assert sr.sha256_of(sums, "sftp-v3.1.0.tar.gz") == "ef" * 32
    with pytest.raises(ValueError, match="does not list"):
        sr.sha256_of(sums, "new-v0.1.0.tar.gz")


def test_pin_on_the_command_line_writes_both_copies(tmp_path, monkeypatch, capsys):
    manifest, copy = tmp_path / "apps.toml", tmp_path / "root" / "apps.toml"
    copy.parent.mkdir()
    for path in (manifest, copy):
        path.write_text(MANIFEST, encoding="utf-8")
    monkeypatch.setattr(sr, "MANIFEST", manifest)
    monkeypatch.setattr(sr, "ROOT_COPY", copy)
    (tmp_path / "sums" / "sftp-v3.1.0").mkdir(parents=True)
    (tmp_path / "sums" / "sftp-v3.1.0" / "SHA256SUMS").write_text(f"{'12' * 32}  sftp-v3.1.0.tar.gz\n")
    assert sr.main(["pin", str(tmp_path / "sums"), "sftp-v3.1.0"]) == 0
    assert f'sha256 = "{"12" * 32}"' in manifest.read_text(encoding="utf-8")
    assert copy.read_bytes() == manifest.read_bytes()               # check_manifest.py wants them identical
    assert sr.main(["pin", str(tmp_path / "sums"), "new-v0.1.0"]) == 1            # no SHA256SUMS: nothing written
    assert "suite_release.py pin" in capsys.readouterr().err
    copy.unlink()                                                   # without the root's copy: the manifest alone
    assert sr.main(["pin", str(tmp_path / "sums"), "sftp-v3.1.0"]) == 0 and not copy.exists()
