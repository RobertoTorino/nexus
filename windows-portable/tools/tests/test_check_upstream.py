# SPDX-License-Identifier: GPL-3.0-or-later
"""The weekly upstream check (check_upstream.py) with GitHub stood in for: the pins read from the apps' emulator.py
(the real ones, and one made here), a newer release and a replaced or missing asset reported, all in step quiet,
and an upstream that cannot be asked."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_upstream as cu  # noqa: E402

SHA = "ab" * 32


def suite(tmp_path: Path) -> Path:
    package = tmp_path / "windows-portable" / "apps" / "emu" / "emu_manager"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('APP_NAME = "Emu Manager"\n', encoding="utf-8")
    (package / "emulator.py").write_text(
        'VERSION = "1.2.0"\nTAG = f"v{VERSION}"\nASSET = f"Emu-{TAG}-Windows-x64.zip"\n'
        f'SHA256 = "{SHA}"\nREPO = "someone/emu"\n', encoding="utf-8")
    (tmp_path / "windows-portable" / "apps" / "test").mkdir()      # an app without an emulator
    return tmp_path / "windows-portable"


def github(latest: str, digest: str = SHA, asset: str = "Emu-v1.2.0-Windows-x64.zip"):
    def get(url: str) -> bytes:
        if url.endswith("/releases/latest"):
            return json.dumps({"tag_name": latest, "published_at": "2030-01-02T00:00:00Z",
                               "html_url": f"https://github.com/someone/emu/releases/tag/{latest}"}).encode()
        if url.endswith("/releases/tags/v1.2.0"):
            return json.dumps({"assets": [{"name": asset, "digest": f"sha256:{digest}"}]}).encode()
        raise AssertionError(url)
    return get


def test_the_suites_own_pins_are_read():
    found = {pin.app: pin for pin in cu.pins()}
    assert set(found) == {"pcsx2", "ppsspp", "rpcs3", "shadps4"}
    assert found["ppsspp"].repo == "hrydgard/ppsspp" and found["ppsspp"].asset == f"PPSSPP-v{found['ppsspp'].version}-Windows-x64.zip"
    assert found["pcsx2"].repo == "PCSX2/pcsx2" and found["pcsx2"].tag == f"v{found['pcsx2'].version}"
    assert found["ppsspp"].name == "PPSSPP Manager" and len(found["pcsx2"].sha256) == 64
    assert found["ppsspp"].file_repo == "hrydgard/ppsspp" and found["ppsspp"].file_tag == found["ppsspp"].tag
    # RPCS3's landmarks are tagged in one repository, its builds published in another: the pin names both
    rpcs3 = found["rpcs3"]
    assert rpcs3.repo == "RPCS3/rpcs3" and rpcs3.tag == "v" + rpcs3.version.split("-")[0]
    assert rpcs3.file_repo == "RPCS3/rpcs3-binaries-win" and rpcs3.file_tag.startswith("build-")
    assert rpcs3.asset.endswith("_win64_msvc.7z") and rpcs3.version in rpcs3.asset
    # shadPS4 tags its releases "v.0.20.0"
    shadps4 = found["shadps4"]
    assert shadps4.repo == "shadps4-emu/shadPS4" and shadps4.tag == f"v.{shadps4.version}"
    assert shadps4.file_tag == shadps4.tag and shadps4.version in shadps4.asset


def test_a_pin_whose_file_is_in_another_repository(tmp_path):
    """The latest release from REPO, the file from BUILDS at BUILD_TAG (RPCS3's layout)."""
    package = tmp_path / "windows-portable" / "apps" / "emu" / "emu_manager"
    package.mkdir(parents=True)
    (package / "emulator.py").write_text(
        'LANDMARK = "0.0.43"\nBUILD = 20395\nVERSION = f"{LANDMARK}-20395"\nTAG = f"v{LANDMARK}"\n'
        'REPO = "someone/emu"\nBUILDS = "someone/emu-builds"\nBUILD_TAG = "build-abc"\n'
        f'ASSET = "emu-v0.0.43-20395_win64.7z"\nSHA256 = "{SHA}"\n', encoding="utf-8")
    asked = []

    def get(url: str) -> bytes:
        asked.append(url)
        if url.endswith("someone/emu/releases/latest"):
            return json.dumps({"tag_name": "v0.0.43", "published_at": "2030-01-02T00:00:00Z"}).encode()
        if url.endswith("someone/emu-builds/releases/tags/build-abc"):
            return json.dumps({"assets": [{"name": "emu-v0.0.43-20395_win64.7z", "digest": f"sha256:{SHA}"}]}).encode()
        raise AssertionError(url)
    report = tmp_path / "upstream.md"
    assert cu.main(["--report", str(report)], get, tmp_path / "windows-portable") == 0
    assert report.read_text() == "" and len(asked) == 2
    pin = cu.pins(tmp_path / "windows-portable")[0]
    assert pin.version == "0.0.43-20395" and pin.tag == "v0.0.43" and pin.file_tag == "build-abc"

    def newer(url: str) -> bytes:
        if url.endswith("/releases/latest"):
            return json.dumps({"tag_name": "v0.0.44", "published_at": "2030-02-02T00:00:00Z", "html_url": "u"}).encode()
        return get(url)
    assert cu.main(["--report", str(report)], newer, tmp_path / "windows-portable") == 1
    assert "v0.0.44 is out" in report.read_text()


def test_all_in_step_writes_an_empty_report(tmp_path, capsys):
    report = tmp_path / "upstream.md"
    assert cu.main(["--report", str(report)], github("v1.2.0"), suite(tmp_path)) == 0
    assert report.read_text() == "" and "In step." in capsys.readouterr().out


def test_a_newer_release_is_reported(tmp_path):
    report = tmp_path / "upstream.md"
    assert cu.main(["--report", str(report)], github("v1.3.0"), suite(tmp_path)) == 1
    text = report.read_text()
    assert "### Emu Manager" in text and "Pinned 1.2.0, latest stable 1.3.0" in text
    assert "v1.3.0 is out (2030-01-02): a new version of Emu Manager brings it" in text
    assert "VERSION in windows-portable/apps/emu/emu_manager/emulator.py" in text


def test_a_replaced_or_missing_asset_is_reported(tmp_path):
    report, made = tmp_path / "upstream.md", suite(tmp_path)
    assert cu.main(["--report", str(report)], github("v1.2.0", digest="cd" * 32), made) == 1
    assert "was replaced" in report.read_text()
    assert cu.main(["--report", str(report)], github("v1.2.0", asset="other.zip"), made) == 1
    assert "is gone from v1.2.0" in report.read_text()


def test_an_upstream_that_cannot_be_asked(tmp_path, capsys):
    def offline(url: str) -> bytes:
        raise cu.CheckError(f"{url}: no connection")
    made = suite(tmp_path)
    assert cu.main([], offline, made) == 2
    assert "could not be checked" in capsys.readouterr().err
    assert cu.main(["nothing"], offline, made) == 2


@pytest.mark.parametrize("argv", [["--report"]])
def test_report_needs_a_file(argv):
    assert cu.main(argv) == 2


def test_a_tag_with_a_dot_after_the_v(tmp_path):
    """shadPS4 tags its releases "v.0.20.0": the version compared and shown without the "v."."""
    report = tmp_path / "upstream.md"
    assert cu.main(["--report", str(report)], github("v.1.3.0"), suite(tmp_path)) == 1
    assert "Pinned 1.2.0, latest stable 1.3.0" in report.read_text()
    assert cu.check(cu.pins(suite(tmp_path / "again"))[0], github("v.1.2.0")).text().startswith(
        "Emu Manager: pinned 1.2.0, latest stable 1.2.0. In step.")
