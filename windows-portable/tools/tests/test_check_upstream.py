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
    assert set(found) == {"pcsx2", "ppsspp"}
    assert found["ppsspp"].repo == "hrydgard/ppsspp" and found["ppsspp"].asset == f"PPSSPP-v{found['ppsspp'].version}-Windows-x64.zip"
    assert found["pcsx2"].repo == "PCSX2/pcsx2" and found["pcsx2"].tag == f"v{found['pcsx2'].version}"
    assert found["ppsspp"].name == "PPSSPP Manager" and len(found["pcsx2"].sha256) == 64


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
