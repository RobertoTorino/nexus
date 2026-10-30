# SPDX-License-Identifier: GPL-3.0-or-later
"""suite_release.py, the release workflow's plan and pin steps, with GitHub stood in for: a tag pushed by hand, a
Nexus release with some apps out already, a draft made anew, apps without a portal bump, and the pins written."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import suite_release as sr  # noqa: E402

SHA = "ab" * 32
MANIFEST = """# a comment that stays
[apps.test]
name = "Windows Portable Test"
tag = "wp-test-v3.0.1"
sha256 = "%s"
required = true

[apps.pcsx2]
name = "PCSX2 Manager"
tag = "wp-pcsx2-v3.1.0"
sha256 = ""

[apps.xenia]
name = "Xenia Manager"
tag = "wp-xenia-v1.0.1"
withdrawn = "a reason"

[apps.new]
name = "New Manager"
tag = "wp-new-v0.1.0"
""" % SHA


def test_a_tag_pushed_by_hand_is_that_release_published_at_once():
    assert sr.plan(MANIFEST, "4.1.0", tag="wp-pcsx2-v3.1.0") == {"apps": ["wp-pcsx2-v3.1.0"], "portal": "",
                                                                 "draft": False}
    assert sr.plan(MANIFEST, "4.1.0", tag="wp-portal-v4.1.0") == {"apps": [], "portal": "wp-portal-v4.1.0",
                                                                  "draft": False}
    with pytest.raises(ValueError, match="is not wp-"):
        sr.plan(MANIFEST, "4.1.0", tag="pcsx2-v3.1.0")


def test_a_nexus_release_brings_the_unreleased_pins_and_a_draft_portal():
    out = {"wp-test-v3.0.1", "wp-portal-v4.0.0"}
    found = sr.plan(MANIFEST, "4.1.0", released=out.__contains__)
    assert found == {"apps": ["wp-pcsx2-v3.1.0", "wp-new-v0.1.0"], "portal": "wp-portal-v4.1.0", "draft": True}
    assert sr.output_lines(found) == ['apps=["wp-pcsx2-v3.1.0", "wp-new-v0.1.0"]', "portal=wp-portal-v4.1.0",
                                      "draft=true"]
    assert json.loads(sr.output_lines(found)[0].removeprefix("apps=")) == found["apps"]


def test_a_withdrawn_app_is_not_built():
    found = sr.plan(MANIFEST, "4.1.0", released=lambda tag: False)
    assert "wp-xenia-v1.0.1" not in found["apps"]


def test_a_portal_out_already_releases_nothing_but_apps_need_a_bump():
    everything = {"wp-test-v3.0.1", "wp-pcsx2-v3.1.0", "wp-new-v0.1.0", "wp-portal-v4.0.0"}
    assert sr.plan(MANIFEST, "4.0.0", released=everything.__contains__) == {"apps": [], "portal": "",
                                                                           "draft": True}
    with pytest.raises(ValueError, match="bump portal/VERSION"):
        sr.plan(MANIFEST, "4.0.0", released={"wp-portal-v4.0.0"}.__contains__)


def test_only_the_portal_a_withdrawal_for_instance():
    everything = {"wp-test-v3.0.1", "wp-pcsx2-v3.1.0", "wp-new-v0.1.0"}
    assert sr.plan(MANIFEST, "4.1.0", released=everything.__contains__) == {"apps": [], "portal": "wp-portal-v4.1.0",
                                                                           "draft": True}


def test_pin_sets_only_the_sha256_line_of_that_app():
    other = "cd" * 32
    text = sr.pin(MANIFEST, "wp-pcsx2-v3.1.0", other)
    assert f'tag = "wp-pcsx2-v3.1.0"\nsha256 = "{other}"\n' in text
    assert text.replace(other, "") == MANIFEST                      # nothing else changed, the comment included
    text = sr.pin(text, "wp-new-v0.1.0", other)                     # an app without a sha256 line gets one
    assert text.endswith(f'tag = "wp-new-v0.1.0"\nsha256 = "{other}"\n')


def test_pin_refuses_a_tag_the_manifest_does_not_pin():
    with pytest.raises(ValueError, match="does not pin wp-pcsx2-v3.0.0"):
        sr.pin(MANIFEST, "wp-pcsx2-v3.0.0", SHA)
    with pytest.raises(ValueError, match="no app for wp-gone-v1.0.0"):
        sr.pin(MANIFEST, "wp-gone-v1.0.0", SHA)


def test_the_checksum_comes_from_the_releases_own_sha256sums():
    sums = f"{'EF' * 32} *wp-pcsx2-v3.1.0.zip\n{SHA}  other.zip\n"
    assert sr.sha256_of(sums, "wp-pcsx2-v3.1.0.zip") == "ef" * 32
    with pytest.raises(ValueError, match="does not list"):
        sr.sha256_of(sums, "wp-new-v0.1.0.zip")


def test_pin_on_the_command_line(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "apps.toml"
    manifest.write_text(MANIFEST, encoding="utf-8")
    monkeypatch.setattr(sr, "MANIFEST", manifest)
    (tmp_path / "sums" / "wp-pcsx2-v3.1.0").mkdir(parents=True)
    (tmp_path / "sums" / "wp-pcsx2-v3.1.0" / "SHA256SUMS").write_text(f"{'12' * 32}  wp-pcsx2-v3.1.0.zip\n")
    assert sr.main(["pin", str(tmp_path / "sums"), "wp-pcsx2-v3.1.0"]) == 0
    assert f'sha256 = "{"12" * 32}"' in manifest.read_text(encoding="utf-8")
    assert sr.main(["pin", str(tmp_path / "sums"), "wp-new-v0.1.0"]) == 1            # no SHA256SUMS: nothing written
    assert "suite_release.py pin" in capsys.readouterr().err
