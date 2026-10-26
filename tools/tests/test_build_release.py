# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/build_release.py: layout, modes, checksums and reproducibility of the release tarballs."""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
import sys
import tarfile
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("build_release", TOOLS / "build_release.py")
br = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = br
spec.loader.exec_module(br)

pin_spec = importlib.util.spec_from_file_location("pin_app", TOOLS.parent / "bc250-bazzite" / "tools" / "pin_app.py")
pin_app = importlib.util.module_from_spec(pin_spec)
sys.modules[pin_spec.name] = pin_app
pin_spec.loader.exec_module(pin_app)

BT_TAG = f"check-v{(br.SUITE / 'apps' / 'check' / 'VERSION').read_text().strip()}"
PORTAL_TAG = f"portal-v{(br.SUITE / 'portal' / 'VERSION').read_text().strip()}"
MEDIA_TOOL_TAG = f"mtool-v{(br.SUITE / 'apps' / 'mtool' / 'VERSION').read_text().strip()}"


@pytest.fixture(autouse=True)
def fixed_epoch(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1790000000")


@pytest.fixture(scope="module")
def bt_release(tmp_path_factory):
    import os
    os.environ["SOURCE_DATE_EPOCH"] = "1790000000"
    out = tmp_path_factory.mktemp("bt")
    br.build(BT_TAG, out)
    return out


@pytest.fixture
def pinned(bt_release, tmp_path, monkeypatch):
    """apps.toml as shipped, but with check pinned to the local build: the shipped pin is the checksum of
    the real release, which a local build (another mtime) never matches."""
    digest = hashlib.sha256((bt_release / f"{BT_TAG}.tar.gz").read_bytes()).hexdigest()
    text = (br.MANIFEST).read_text(encoding="utf-8")
    path = tmp_path / "apps.toml"
    path.write_text(pin_app.pin(text, "check", BT_TAG, digest), encoding="utf-8")
    monkeypatch.setattr(br, "MANIFEST", path)
    return path


def members(archive: Path) -> dict[str, tarfile.TarInfo]:
    with tarfile.open(archive, "r:gz") as tar:
        return {m.name: m for m in tar.getmembers()}


def read(archive: Path, name: str) -> bytes:
    with tarfile.open(archive, "r:gz") as tar:
        return tar.extractfile(name).read()


def test_bazzite_test_layout(bt_release):
    archive = bt_release / f"{BT_TAG}.tar.gz"
    names = members(archive)
    top = BT_TAG
    assert {f"{top}/install.sh", f"{top}/test-bazzite.sh", f"{top}/bazzite_check/__main__.py",
            f"{top}/bc250_core/widgets.py", f"{top}/bazzite_check/_build_info.py"} <= set(names)
    assert all(n == top or n.startswith(top + "/") for n in names)
    assert not any("/tests/" in n or "__pycache__" in n or n.endswith(".pyc") for n in names)
    engine = read(archive, f"{top}/test-bazzite.sh")
    info = read(archive, f"{top}/bazzite_check/_build_info.py").decode()
    assert hashlib.sha256(engine).hexdigest() in info              # release build: engine hash recorded
    assert 'BUILD_DATE = "2026-09-21 14:13 UTC"' in info                 # the commit time, not the clock: reproducible
    manual = (br.SUITE / "docs" / "apps" / "check.md").read_bytes()
    assert read(archive, f"{top}/MANUAL.md") == manual                # its chapter of the manual


def test_modes_and_owner(bt_release):
    names = members(bt_release / f"{BT_TAG}.tar.gz")
    top = BT_TAG
    assert names[f"{top}/install.sh"].mode == 0o755
    assert names[f"{top}/test-bazzite.sh"].mode == 0o755
    assert names[f"{top}/bazzite_check/__init__.py"].mode == 0o644
    assert names[f"{top}/bazzite_check"].mode == 0o755 and names[f"{top}/bazzite_check"].isdir()
    assert {(m.uid, m.gid, m.uname) for m in names.values()} == {(0, 0, "root")}
    assert {m.mtime for m in names.values()} == {1790000000}


def test_sums_and_notes(bt_release):
    archive = bt_release / f"{BT_TAG}.tar.gz"
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert (bt_release / "SHA256SUMS").read_text() == f"{digest}  {archive.name}\n"
    notes = (bt_release / "notes.md").read_text()
    assert f"cd {BT_TAG} && ./install.sh" in notes and digest in notes
    core = (br.ROOT / "core" / "VERSION").read_text().strip()
    assert f"Bundles the suite core `bc250_core` {core}." in notes
    assert notes.index("use the portal, not this file") < notes.index("### Install")   # an app: the portal first
    assert br.LATEST_PORTAL_URL in notes


def test_reproducible(bt_release, tmp_path):
    br.build(BT_TAG, tmp_path)
    assert (tmp_path / f"{BT_TAG}.tar.gz").read_bytes() == (bt_release / f"{BT_TAG}.tar.gz").read_bytes()


def test_version_must_match(tmp_path):
    with pytest.raises(SystemExit, match="bump it before tagging"):
        br.build("check-v9.9.9", tmp_path)
    with pytest.raises(SystemExit, match="is not <app>-v"):
        br.build("check-9.9.9", tmp_path)


def test_media_tool_release_has_the_standard_layout_and_omits_suite_marker(tmp_path):
    br.build(MEDIA_TOOL_TAG, tmp_path)
    names = members(tmp_path / f"{MEDIA_TOOL_TAG}.tar.gz")

    assert f"{MEDIA_TOOL_TAG}/install.sh" in names
    assert f"{MEDIA_TOOL_TAG}/media_tool/__main__.py" in names
    assert f"{MEDIA_TOOL_TAG}/images/media-tool.webp" in names
    assert f"{MEDIA_TOOL_TAG}/install" not in names
    assert f"{MEDIA_TOOL_TAG}/.standalone" not in names
    assert not any("/tests/" in name for name in names)


def test_native_wheel_is_required_and_named(tmp_path, monkeypatch):
    version = (br.SUITE / "apps/consoles/VERSION").read_text().strip()
    wheels = tmp_path / "wheel"
    monkeypatch.setattr(br, "NATIVE_WHEELS", {"consoles": wheels})
    with pytest.raises(SystemExit, match="exactly one .whl"):
        br.build(f"consoles-v{version}", tmp_path / "out")
    wheels.mkdir()
    (wheels / "bc250_console_link_core-0.0.1-cp310-abi3-linux_x86_64.whl").touch()
    with pytest.raises(SystemExit, match="is not version"):
        br.build(f"consoles-v{version}", tmp_path / "out")
    (wheels / "bc250_console_link_core-0.0.1-cp310-abi3-linux_x86_64.whl").unlink()
    name = f"bc250_console_link_core-{version}-cp310-abi3-linux_x86_64.whl"
    (wheels / name).touch()
    br.build(f"consoles-v{version}", tmp_path / "out")
    assert f"Includes its native core as `{name}`" in (tmp_path / "out" / "notes.md").read_text()


def test_checkout_only_app_has_no_release(tmp_path, monkeypatch):
    """An app with .checkout-only (Nexus Releases, Installer Tests) is never built: the marker is refused."""
    suite = tmp_path / "suite"
    (suite / "apps" / "x").mkdir(parents=True)
    (suite / "apps" / "x" / ".checkout-only").write_text("No releases.\n")
    (suite / "apps" / "x" / "VERSION").write_text("0.1.0\n")
    monkeypatch.setattr(br, "SUITE", suite)
    with pytest.raises(SystemExit, match="runs from the checkout"):
        br.build("x-v0.1.0", tmp_path)


def test_portal_needs_and_verifies_bundle(bt_release, pinned, tmp_path):
    with pytest.raises(SystemExit, match="needs --bundle"):
        br.build(PORTAL_TAG, tmp_path / "a")
    br.build(PORTAL_TAG, tmp_path / "b", bundle=bt_release)
    archive = tmp_path / "b" / f"{PORTAL_TAG}.tar.gz"
    names = members(archive)
    assert f"{PORTAL_TAG}/bundled/{BT_TAG}/install.sh" in names
    assert f"{PORTAL_TAG}/bundled/{BT_TAG}/bazzite_check/_build_info.py" in names
    assert f"{PORTAL_TAG}/bc250_core/platform.py" in names and f"{PORTAL_TAG}/apps.toml" in names
    notes = (tmp_path / "b" / "notes.md").read_text()
    assert BT_TAG in notes and "use the portal, not this file" not in notes
    stage, note = br.portal_stage()
    assert (f"> **{stage}:** {note}" in notes) == bool(stage)            # the suite's stage, at the top


def test_only_a_portal_release_says_the_stage(bt_release):
    stage, _note = br.portal_stage()
    assert stage == "" or f"**{stage}:**" not in (bt_release / "notes.md").read_text()


def test_wrong_pin_refused(bt_release, pinned, tmp_path):
    pinned.write_text(pin_app.pin(pinned.read_text(encoding="utf-8"), "check", BT_TAG, "ab" * 32),
                      encoding="utf-8")
    with pytest.raises(SystemExit, match="does not match"):
        br.build(PORTAL_TAG, tmp_path / "out", bundle=bt_release)


def test_tampered_bundle_refused(bt_release, pinned, tmp_path):
    bundle = tmp_path / "bundle"
    shutil.copytree(bt_release, bundle)
    data = bytearray((bundle / f"{BT_TAG}.tar.gz").read_bytes())
    data[-10] ^= 0xFF
    (bundle / f"{BT_TAG}.tar.gz").write_bytes(bytes(data))
    with pytest.raises(SystemExit, match="does not match"):
        br.build(PORTAL_TAG, tmp_path / "out", bundle=bundle)


def test_latest_changes(tmp_path):
    log = tmp_path / "CHANGELOG"
    log.write_text("Changelog: 08-10-2026\n\nNew thing.\n\nChangelog: 07-10-2026\n\nOld thing.\n")
    assert br.latest_changes(log) == "Changelog: 08-10-2026\n\nNew thing."
    log.write_text("# Changelog\n\n## 0.2.0\n\nA\n\n## 0.1.0\n\nB\n")
    assert br.latest_changes(log) == "## 0.2.0\n\nA"
