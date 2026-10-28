# SPDX-License-Identifier: GPL-3.0-or-later
"""windows-portable/tools/build_release.py: what it hands PyInstaller, the zip, the checksum and the notes.
PyInstaller itself is not run here: it builds for the system it runs on, and CI's Windows job does that."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import time
import zipfile
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("portable_build_release", TOOLS / "build_release.py")
br = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = br
spec.loader.exec_module(br)

TEST_TAG = f"wp-test-v{(br.SUITE / 'apps' / 'test' / 'VERSION').read_text().strip()}"


@pytest.fixture(autouse=True)
def fixed_epoch(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1790000000")


PORTAL_TAG = f"wp-portal-v{(br.SUITE / 'portal' / 'VERSION').read_text().strip()}"


@pytest.fixture
def fake_pyinstaller(monkeypatch):
    """build_zip without PyInstaller: a zip that names what it was asked for."""
    def build_zip(app, tag, out, epoch, bundle=None):
        if app == "portal":
            br.bundled_test(bundle)                     # as the real one: a portal needs the pinned test release
        out.mkdir(parents=True, exist_ok=True)
        archive = out / f"{tag}.zip"
        archive.write_bytes(f"{app} {epoch}{' ' + bundle.name if bundle else ''}".encode())
        return archive
    monkeypatch.setattr(br, "build_zip", build_zip)


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    """A folder with the pinned test release's zip and its SHA256SUMS, as the release workflow downloads them, and
    the pin's sha256 set to that zip's (apps.toml's own pin is of the real release)."""
    tag, _ = br.pinned_test()
    folder = tmp_path / "bundle"
    folder.mkdir()
    (folder / f"{tag}.zip").write_bytes(b"the test release")
    digest = hashlib.sha256(b"the test release").hexdigest()
    (folder / "SHA256SUMS").write_text(f"{digest}  {tag}.zip\n", encoding="utf-8")
    monkeypatch.setattr(br, "pinned_test", lambda: (tag, digest))
    return folder


def test_an_app_gets_its_zip_checksum_and_notes(tmp_path, fake_pyinstaller):
    archive = br.build(TEST_TAG, tmp_path)
    assert archive == tmp_path / f"{TEST_TAG}.zip" and archive.read_bytes() == b"test 1790000000"
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert (tmp_path / "SHA256SUMS").read_text(encoding="utf-8") == f"{digest}  {archive.name}\n"
    notes = (tmp_path / "notes.md").read_text(encoding="utf-8")
    assert notes.startswith(f"## {TEST_TAG}\n")
    assert f"Expand-Archive {archive.name} ." in notes and "install.ps1" in notes
    # The check compares by itself, as sha256sum --check does: True or False, nothing to read by eye.
    assert f"(Get-FileHash {archive.name}).Hash -eq (-split (Get-Content SHA256SUMS))[0]" in notes
    assert "not signed" in notes and "### Changes" in notes
    assert "latest portal release" not in notes                 # no portal yet, and never the BC250 suite's
    title = f"Windows Portable Suite: Windows Portable Test {TEST_TAG.split('-v')[1]}\n"
    assert (tmp_path / "title.txt").read_text(encoding="utf-8") == title


def test_the_portal_bundles_the_pinned_test_release(tmp_path, fake_pyinstaller, bundle, monkeypatch):
    archive = br.build(PORTAL_TAG, tmp_path / "out", bundle)
    assert archive.read_bytes() == b"portal 1790000000 bundle"
    notes = (tmp_path / "out" / "notes.md").read_text(encoding="utf-8")
    tag, _ = br.pinned_test()
    assert f"with Windows Portable Test {tag.rsplit('-v', 1)[1]} bundled" in notes and "### Install" in notes
    title = f"Windows Portable Suite: Portal {PORTAL_TAG.split('-v')[1]}\n"
    assert (tmp_path / "out" / "title.txt").read_text(encoding="utf-8") == title
    with pytest.raises(SystemExit, match="--bundle"):
        br.build(PORTAL_TAG, tmp_path / "out2")
    monkeypatch.setattr(br, "pinned_test", lambda: (tag, ""))         # no sha256 pinned: SHA256SUMS checks it
    assert br.bundled_test(bundle) == (bundle / f"{tag}.zip", hashlib.sha256(b"the test release").hexdigest())
    (bundle / f"{tag}.zip").write_bytes(b"another")
    with pytest.raises(SystemExit, match="does not match its checksum"):
        br.bundled_test(bundle)
    (bundle / "SHA256SUMS").unlink()
    monkeypatch.setattr(br, "pinned_test", lambda: (tag, ""))
    with pytest.raises(SystemExit, match="no SHA256SUMS"):
        br.bundled_test(bundle)
    monkeypatch.setattr(br, "pinned_test", lambda: (tag, hashlib.sha256(b"another").hexdigest()))
    assert br.bundled_test(bundle) == (bundle / f"{tag}.zip", hashlib.sha256(b"another").hexdigest())
    monkeypatch.setattr(br, "build", lambda tag, out, bundle=None: (tmp_path / "out" / f"{tag}.zip"))
    assert br.main([PORTAL_TAG, "out", "--bundle", str(bundle)]) == 0            # --bundle parsed
    assert br.main([PORTAL_TAG, "out", "--other", str(bundle)]) == 2


def test_a_stale_version_and_another_suites_tag_are_refused(tmp_path, fake_pyinstaller):
    with pytest.raises(SystemExit, match="bump it before tagging"):
        br.build("wp-test-v9.9.9", tmp_path)
    with pytest.raises(SystemExit, match="is not wp-<app>-v"):
        br.build("check-v0.17.0", tmp_path)                      # the BC250 suite's: tools/build_release.py
    assert not (tmp_path / "SHA256SUMS").exists()


def test_it_builds_on_windows_only(monkeypatch, capsys):
    monkeypatch.setattr(br.sys, "platform", "linux")
    assert br.main([TEST_TAG, "out"]) == 1
    assert "built on Windows" in capsys.readouterr().err


def test_a_one_folder_build_with_the_logo_and_core_fonts(tmp_path):
    args = br.pyinstaller_args(tmp_path / "stage", tmp_path / "run.py", "portable_test", "Windows-Portable-Test",
                               tmp_path / "logo.webp", tmp_path / "work", tmp_path / "dist", sep=";")
    assert args[0] == str(tmp_path / "run.py")
    assert {"--onedir", "--windowed"} <= set(args) and "--onefile" not in args
    assert args[args.index("--name") + 1] == "Windows-Portable-Test"
    collected = [args[i + 1] for i, a in enumerate(args) if a in ("--collect-submodules", "--collect-all")]
    assert collected == ["portable_test", "bc250_core"]
    add_data = [args[i + 1] for i, a in enumerate(args) if a == "--add-data"]
    assert add_data == [f"{tmp_path / 'stage' / 'images'};images", f"{tmp_path / 'stage' / 'bc250_core' / 'fonts'};bc250_core/fonts"]
    (tmp_path / "stage").mkdir()
    (tmp_path / "stage" / "apps.toml").write_text("")                     # the portal: its manifest beside the package
    args = br.pyinstaller_args(tmp_path / "stage", tmp_path / "run.py", "portable_portal", "Windows-Portable-Suite",
                               tmp_path / "logo.webp", tmp_path / "work", tmp_path / "dist", sep=";")
    assert args[-2:] == ["--add-data", f"{tmp_path / 'stage' / 'apps.toml'};."]


def test_the_package_and_exe_name_come_from_the_app():
    src = br.SUITE / "apps" / "test"
    assert br.suite_package(src) == "portable_test"
    assert br.exe_name_of(src, "portable_test") == "Windows-Portable-Test"
    assert br.windows_exe.app_id(src, "portable_test") == "windows-portable-test"
    assert "Windows-Portable-Test.exe" in (src / "install.ps1").read_text(encoding="utf-8")


def test_the_zip_unpacks_into_the_tag_in_the_same_order_with_the_same_times(tmp_path):
    root = tmp_path / "root"
    (root / "program" / "_internal").mkdir(parents=True)
    for name in ("program/_internal/b.txt", "program/X.exe", "install.ps1", "LICENSE"):
        (root / name).write_text(name, encoding="utf-8")
    br.write_zip(root, "wp-test-v0.1.0", tmp_path / "a.zip", 1790000000)
    br.write_zip(root, "wp-test-v0.1.0", tmp_path / "b.zip", 1790000000)
    assert (tmp_path / "a.zip").read_bytes() == (tmp_path / "b.zip").read_bytes()
    with zipfile.ZipFile(tmp_path / "a.zip") as zf:
        assert zf.namelist() == ["wp-test-v0.1.0/LICENSE", "wp-test-v0.1.0/install.ps1",
                                 "wp-test-v0.1.0/program/X.exe", "wp-test-v0.1.0/program/_internal/b.txt"]
        assert {info.date_time for info in zf.infolist()} == {time.gmtime(1790000000)[:6]}
