# SPDX-License-Identifier: GPL-3.0-or-later
"""sources.py: a release zip downloaded, checked against the pin or SHA256SUMS and unpacked into the portal's
folder; a folder reused, older ones pruned; the records; an installed app detected through its paths."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from portable_portal.manifest import AppEntry
from portable_portal.sources import (COMPLETE, Records, SourceError, Sources, expected_sha256, fetch_release,
                                     is_installed, safe_extract)

ENTRY = AppEntry(key="test", name="Windows Portable Test", summary="s", tag="wp-test-v0.1.0", category="sustainable",
                 install=("powershell -File install.ps1",), uninstall=("powershell -File install.ps1 --uninstall",),
                 detect=("%LOCALAPPDATA%\\windows-portable-suite\\windows-portable-test\\app\\X.exe",))


def make_zip(path: Path, files: dict[str, bytes], top: str = "wp-test-v0.1.0") -> str:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(f"{top}/{name}" if top else name, data)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeRelease:
    """Serves release assets from a folder, recording the URLs asked for."""

    def __init__(self, folder: Path):
        self.folder, self.urls = folder, []

    def __call__(self, url: str, dest: Path) -> None:
        self.urls.append(url)
        src = self.folder / url.rsplit("/", 1)[1]
        if not src.is_file():
            raise OSError(f"404 {url}")
        shutil.copy(src, dest)


def test_expected_sha256():
    sums = "aa" * 32 + "  wp-test-v0.1.0.zip\n" + "bb" * 32 + " *other.zip\n"
    assert expected_sha256(sums, "wp-test-v0.1.0.zip") == "aa" * 32
    assert expected_sha256(sums, "other.zip") == "bb" * 32
    assert expected_sha256(sums, "missing.zip") == ""


def test_a_release_is_downloaded_checked_with_sha256sums_and_unpacked(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    digest = make_zip(assets / ENTRY.asset, {"install.ps1": b"Write-Host hi\n", "program/X.exe": b"x"})
    (assets / "SHA256SUMS").write_text(f"{digest}  {ENTRY.asset}\n")
    release = FakeRelease(assets)
    sources = Sources(tmp_path / "releases", repo_url="https://example.invalid/r", download=release)
    folder = sources.prepare(ENTRY)
    assert folder == tmp_path / "releases" / ENTRY.tag
    assert (folder / "install.ps1").read_bytes() == b"Write-Host hi\n" and (folder / "program" / "X.exe").is_file()
    assert (folder / COMPLETE).read_text().strip() == digest
    assert release.urls == [f"https://example.invalid/r/releases/download/{ENTRY.tag}/{ENTRY.asset}",
                            f"https://example.invalid/r/releases/download/{ENTRY.tag}/SHA256SUMS"]
    assert sources.prepare(ENTRY) == folder and len(release.urls) == 2          # reused: a tag never changes
    assert not list((tmp_path / "releases").glob(".*.part"))


def test_the_pinned_sha256_is_used_and_a_wrong_one_leaves_nothing(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    digest = make_zip(assets / ENTRY.asset, {"install.ps1": b"x"})
    release = FakeRelease(assets)
    sources = Sources(tmp_path / "releases", download=release)
    assert sources.prepare(replace(ENTRY, sha256=digest)).is_dir()
    assert len(release.urls) == 1                                                # no SHA256SUMS asked for
    shutil.rmtree(tmp_path / "releases")
    with pytest.raises(SourceError, match="does not match its checksum"):
        sources.prepare(replace(ENTRY, sha256="0" * 64))
    assert not (tmp_path / "releases" / ENTRY.tag).exists()
    with pytest.raises(SourceError, match="could not download"):
        sources.prepare(replace(ENTRY, tag="wp-test-v9.9.9"))


def test_a_zip_that_points_outside_or_lacks_the_tag_folder_is_refused(tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../escape.txt", b"x")
    with pytest.raises(SourceError, match="points outside"):
        safe_extract(bad, tmp_path / "out")
    assets = tmp_path / "assets"
    assets.mkdir()
    digest = make_zip(assets / ENTRY.asset, {"install.ps1": b"x"}, top="other-v0.1.0")
    with pytest.raises(SourceError, match="has no wp-test-v0.1.0/ folder"):
        fetch_release(FakeRelease(assets), "https://example.invalid/r", ENTRY.tag, ENTRY.asset, tmp_path / "w", digest)


def test_prune_keeps_the_installed_release_and_forget_removes_it(tmp_path):
    work = tmp_path / "releases"
    for name in ("wp-test-v0.1.0", "wp-test-v0.0.9", "wp-pcsx2-v0.1.0", ".wp-test-v0.2.0.part"):
        (work / name).mkdir(parents=True)
    sources = Sources(work)
    sources.prune(ENTRY)
    assert sorted(p.name for p in work.iterdir()) == [".wp-test-v0.2.0.part", "wp-pcsx2-v0.1.0", "wp-test-v0.1.0"]
    sources.forget(ENTRY)
    assert not (work / "wp-test-v0.1.0").exists()
    Sources(tmp_path / "nowhere").prune(ENTRY)                                    # no folder yet: nothing to do


def test_records(tmp_path):
    path = tmp_path / "installed.json"
    records = Records(path)
    assert records.get("test") == ""
    records.set("test", "wp-test-v0.1.0")
    assert json.loads(path.read_text()) == {"test": "wp-test-v0.1.0"}
    assert Records(path).get("test") == "wp-test-v0.1.0"
    records.remove("test")
    records.remove("test")
    assert json.loads(path.read_text()) == {}
    path.write_text("not json")
    assert Records(path).get("test") == ""


def test_is_installed_expands_the_detect_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert not is_installed(ENTRY)
    exe = tmp_path / "windows-portable-suite" / "windows-portable-test" / "app" / "X.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"x")
    assert is_installed(ENTRY)
