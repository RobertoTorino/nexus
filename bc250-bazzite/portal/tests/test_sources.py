# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json

import hashlib
import io
import shutil
import tarfile
from dataclasses import replace
from pathlib import Path

import pytest

import bc250_portal
from bc250_portal.manifest import AppEntry
from bc250_portal.sources import (
    Records, SourceError, Sources, expected_sha256, is_installed, safe_extract,
)
from conftest import SUITE

CHECKOUT = SUITE.parent                 # the repository: what the portal records as the checkout

ENTRY = AppEntry(key="compute", name="CU", summary="s", tag="compute-v1.0.0", install=("bash install.sh",),
                 uninstall=("bash install.sh --uninstall",), detect=("~/.local/bin/bc250-bisect-gui",))


def make_tarball(path: Path, files: dict[str, bytes], top: str = "compute-v1.0.0") -> str:
    with tarfile.open(path, "w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(f"{top}/{name}" if top else name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
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
    sums = "aa" * 32 + "  compute-v1.0.0.tar.gz\n" + "bb" * 32 + " *other.tar.gz\n"
    assert expected_sha256(sums, "compute-v1.0.0.tar.gz") == "aa" * 32
    assert expected_sha256(sums, "other.tar.gz") == "bb" * 32
    assert expected_sha256(sums, "missing.tar.gz") == ""


def test_release_download_verified_with_sha256sums(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    digest = make_tarball(assets / ENTRY.asset, {"install.sh": b"echo hi\n"})
    (assets / "SHA256SUMS").write_text(f"{digest}  {ENTRY.asset}\n")
    fake = FakeRelease(assets)
    sources = Sources(tmp_path / "work", repo_url="https://github.com/o/r", download=fake)
    folder = sources.prepare(ENTRY)
    assert (folder / "install.sh").read_bytes() == b"echo hi\n"
    assert fake.urls == ["https://github.com/o/r/releases/download/compute-v1.0.0/compute-v1.0.0.tar.gz",
                         "https://github.com/o/r/releases/download/compute-v1.0.0/SHA256SUMS"]
    fake.urls.clear()
    assert sources.prepare(ENTRY) == folder and fake.urls == []        # a tag never changes: reused
    sources.forget(ENTRY)
    assert not folder.exists()


def test_pinned_sha256_wins_and_mismatch_refuses(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    digest = make_tarball(assets / ENTRY.asset, {"install.sh": b"x"})
    pinned = replace(ENTRY, sha256=digest)
    fake = FakeRelease(assets)
    Sources(tmp_path / "w1", download=fake).prepare(pinned)
    assert not any(u.endswith("SHA256SUMS") for u in fake.urls)
    wrong = replace(ENTRY, sha256="0" * 64)
    with pytest.raises(SourceError, match="does not match its checksum"):
        Sources(tmp_path / "w2", download=fake).prepare(wrong)
    assert not (tmp_path / "w2" / ENTRY.tag).exists()


def test_download_errors(tmp_path):
    with pytest.raises(SourceError, match="could not download"):
        Sources(tmp_path / "w", download=FakeRelease(tmp_path)).prepare(ENTRY)


def test_wrong_top_folder(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    digest = make_tarball(assets / ENTRY.asset, {"install.sh": b"x"}, top="something-else")
    pinned = replace(ENTRY, sha256=digest)
    with pytest.raises(SourceError, match="has no compute-v1.0.0/ folder"):
        Sources(tmp_path / "w", download=FakeRelease(assets)).prepare(pinned)


@pytest.mark.parametrize("name", ["../evil.sh", "/tmp/evil.sh"])
def test_safe_extract_refuses_escapes(tmp_path, name):
    archive = tmp_path / "a.tar.gz"
    make_tarball(archive, {name: b"x"}, top="")
    with pytest.raises(SourceError, match="outside"):
        safe_extract(archive, tmp_path / "out")
    assert not (tmp_path / "evil.sh").exists()


def test_safe_extract_refuses_links_out(tmp_path):
    archive = tmp_path / "a.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        link = tarfile.TarInfo("top/passwd")
        link.type, link.linkname = tarfile.SYMTYPE, "../../../etc/passwd"
        tar.addfile(link)
    with pytest.raises(SourceError, match="link"):
        safe_extract(archive, tmp_path / "out")


def test_checkout_stages_app_with_core(tmp_path):
    sources = Sources(tmp_path / "work", checkout=CHECKOUT)
    bt = AppEntry(key="check", name="BT", summary="s", tag="check-v0.1.0", install=("x",),
                  uninstall=("y",), detect=("z",))
    folder = sources.prepare(bt)
    assert folder.name == "local-check"
    assert (folder / "install.sh").is_file() and (folder / "bazzite_check" / "__init__.py").is_file()
    assert (folder / "bc250_core" / "widgets.py").is_file()                 # bundled: check uses core
    assert not (folder / "bc250_core" / "__pycache__").exists()
    acpi = AppEntry(key="acpi", name="A", summary="s", tag="acpi-v0.1.0", install=("x",),
                    uninstall=("y",), detect=("z",))
    acpi_folder = sources.prepare(acpi)
    assert (acpi_folder / "tables" / "acpi_override.cpio").is_file()
    assert not (acpi_folder / "bc250_core").exists()                         # shell only: no core


def test_prune_keeps_only_the_installed_release(tmp_path):
    work = tmp_path / "work"
    for name in ("compute-v0.9.0", "compute-v1.0.0", "local-compute", "cores-bisect-v0.1.0", ".x.part"):
        (work / name).mkdir(parents=True)
    Sources(work).prune(ENTRY)                                              # installed compute-v1.0.0
    assert sorted(p.name for p in work.iterdir()) == [".x.part", "compute-v1.0.0", "cores-bisect-v0.1.0"]
    Sources(work, checkout=CHECKOUT).prune(ENTRY)                           # then from the checkout
    assert sorted(p.name for p in work.iterdir()) == [".x.part", "cores-bisect-v0.1.0"]   # local-compute not made
    Sources(tmp_path / "none").prune(ENTRY)                                 # no folder yet: nothing to do


def test_checkout_only_app_runs_in_its_checkout_folder(tmp_path):
    entry = AppEntry(key="installer-tests", name="IT", summary="s", tag="", checkout_only=True, install=("x",),
                     uninstall=("y",), detect=("z",), folder="tools/installer-tests/gui")
    sources = Sources(tmp_path / "work", checkout=CHECKOUT)
    assert sources.prepare(entry) == SUITE / "tools/installer-tests/gui"   # in the suite's folder of the checkout
    sources.forget(entry)
    assert (SUITE / "tools/installer-tests/gui/install.sh").is_file()      # never removed
    with pytest.raises(SourceError, match="no"):
        Sources(tmp_path / "work").prepare(entry)                          # a portal from a release has no checkout
    (SUITE / "apps" / "x").mkdir()
    try:
        assert sources.prepare(replace(entry, key="x", folder="")) == SUITE / "apps" / "x"   # the default folder
    finally:
        (SUITE / "apps" / "x").rmdir()
    releases = replace(entry, key="releases", folder="dev/releases", nexus=True)
    assert sources.prepare(releases) == CHECKOUT / "dev/releases"          # a Nexus app: in the repository


def test_suite_checkout(tmp_path, monkeypatch):
    import bc250_portal
    assert bc250_portal.suite_checkout() == CHECKOUT                        # running from the checkout
    installed = tmp_path / "opt" / "bc250-bazzite-suite"
    installed.mkdir(parents=True)
    monkeypatch.setattr(bc250_portal, "ROOT", installed)
    assert bc250_portal.suite_checkout() is None                            # a release install
    (installed / bc250_portal.CHECKOUT_FILE).write_text(f"{CHECKOUT}\n")
    assert bc250_portal.suite_checkout() == CHECKOUT                        # installed from the checkout
    (installed / bc250_portal.CHECKOUT_FILE).write_text(f"{tmp_path}\n")
    assert bc250_portal.suite_checkout() is None                            # a moved or deleted checkout


def test_is_installed(home):
    assert not is_installed(ENTRY)
    (home / ".local" / "bin" / "bc250-bisect-gui").write_text("#!/bin/sh\n")
    assert is_installed(ENTRY)


def test_records_round_trip(tmp_path):
    path = tmp_path / "state" / "installed.json"
    records = Records(path)
    assert records.get("compute") == ""
    records.set("compute", "compute-v1.0.0")
    records.set("gpu", "local")
    again = Records(path)
    assert (again.get("compute"), again.get("gpu")) == ("compute-v1.0.0", "local")
    again.remove("compute")
    assert Records(path).get("compute") == ""
    path.write_text("not json")
    assert Records(path).get("gpu") == ""


def test_records_follow_an_app_renamed_in_the_suite(tmp_path):
    """A copy installed under an app's old key (ace-queues) is recorded under its new key (ace) with its tag's
    prefix renamed, so the portal neither asks for a reinstall nor offers the version it has as an update."""
    path = tmp_path / "installed.json"
    path.write_text('{"ace-queues": "ace-queues-v0.2.0", "bazzite-netcatgui": "local", "gpu": "gpu-v0.4.0"}')
    records = Records(path)
    assert (records.get("ace"), records.get("ncgui"), records.get("ace-queues")) == ("ace-v0.2.0", "local", "")
    assert json.loads(path.read_text()) == {"ace": "ace-v0.2.0", "ncgui": "local", "gpu": "gpu-v0.4.0"}
    path.write_text('{"ace-queues": "ace-queues-v0.1.9", "ace": "ace-v0.2.1"}')
    assert Records(path).get("ace") == "ace-v0.2.1"                  # a record under the new key stays


def test_records_follow_an_app_renamed_twice(tmp_path):
    """demo-tool became dtool, then mtool: a record under either earlier key moves to mtool."""
    path = tmp_path / "installed.json"
    path.write_text('{"dtool": "dtool-v0.1.13"}')
    assert Records(path).get("mtool") == "mtool-v0.1.13"
    path.write_text('{"demo-tool": "demo-tool-v0.1.9"}')
    assert Records(path).get("mtool") == "mtool-v0.1.9"


def test_a_release_portal_runs_checkout_apps_from_the_checkout_it_was_shown(tmp_path):
    entry = AppEntry(key="installer-tests", name="IT", summary="s", tag="", checkout_only=True, install=("x",),
                     uninstall=("y",), detect=("z",), folder="tools/installer-tests/gui")
    sources = Sources(tmp_path / "work", apps_checkout=CHECKOUT)
    assert not sources.local                                                # released apps still from releases
    assert sources.prepare(entry) == SUITE / "tools/installer-tests/gui"
    releases = replace(entry, key="releases", folder="dev/releases", nexus=True)
    assert sources.prepare(releases) == CHECKOUT / "dev/releases"           # a Nexus app: in the repository
    with pytest.raises(SourceError):
        Sources(tmp_path / "work").folder(entry)


def test_remembered_checkout(tmp_path, monkeypatch):
    import bc250_portal
    monkeypatch.setattr(bc250_portal, "state_dir", lambda: tmp_path / "state")
    assert bc250_portal.remembered_checkout() is None
    bc250_portal.remember_checkout(CHECKOUT)
    assert bc250_portal.remembered_checkout() == CHECKOUT
    bc250_portal.remember_checkout(tmp_path)                                # no longer a checkout: forgotten
    assert bc250_portal.remembered_checkout() is None


def fake_suite(folder: Path) -> Path:
    """A checkout: the suite's apps in its folder, core and the Nexus tools at the root."""
    for sub in (f"{bc250_portal.SUITE_DIR}/apps", "core", "tools"):
        (folder / sub).mkdir(parents=True)
    (folder / "tools/stage_app.py").touch()
    return folder


def test_find_checkout(tmp_path):
    from bc250_portal import find_checkout
    home = tmp_path / "home"
    (home / ".local/bin").mkdir(parents=True)
    assert find_checkout(home) is None
    fake_suite(home / ".cache/old/bc250-bazzite-suite")                      # hidden folders are not searched
    fake_suite(home / "a/b/c/bc250-bazzite-suite")                          # too deep
    assert find_checkout(home) is None
    found = fake_suite(home / "IdeaProjects/bc250-bazzite-suite")
    assert find_checkout(home) == found
    elsewhere = fake_suite(tmp_path / "mnt/work/suite")                     # outside home: a launcher points there
    (home / ".local/bin/nexus-releases").write_text(f'#!/bin/sh\nexec "{elsewhere}/dev/releases/run.sh"\n')
    assert find_checkout(home) == elsewhere
    (home / ".local/bin/nexus-releases").unlink()
    (home / ".local/bin/bc250-installer-test-gui").write_text(
        f'#!/bin/sh\nexec "{elsewhere}/bc250-bazzite/tools/installer-tests/gui/run.sh"\n')
    assert find_checkout(home) == elsewhere                                 # the suite's own launchers too


def test_the_record_of_a_checkout_install(tmp_path):
    from bc250_portal.sources import installed_from, is_local, local_record, local_version
    assert local_record("1.2.3") == "local-v1.2.3" and local_record() == "local" and local_record("dev") == "local"
    assert is_local("local") and is_local("local-v1.2.3")
    assert not is_local("local-v1") and not is_local("gpu-v1.0.0") and not is_local("")
    assert local_version("local-v1.2.3") == "1.2.3" and local_version("local") == "" == local_version("gpu-v1.0.0")
    assert installed_from("gpu-v1.0.0") == "from gpu-v1.0.0"
    assert installed_from("local") == "from the suite checkout"
    assert installed_from("local-v1.2.3") == "from the suite checkout (v1.2.3)"
    path = tmp_path / "installed.json"                                      # a renamed app keeps it
    path.write_text('{"gpu-oc-bisect": "local-v0.1.9"}')
    assert Records(path).get("oc") == "local-v0.1.9"
