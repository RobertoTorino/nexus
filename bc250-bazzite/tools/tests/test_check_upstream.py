# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/check_upstream.py on a fake GitHub: in step, a newer Decky release, a replaced asset, a changed service unit
(at the pinned tag or only on main), no network; the same for shadPS4's pin, read from emulator.py; and HelixSR
against what acquire.py knows (a newer release, another fallback in the notes, a fallback without its zip); the pins
of PPSSPP, PCSX2, RPCS3 and DirectMesh against a newer release; the builds of Vita3K and Xenia (a later build, a
replaced or vanished AppImage); the USB Wi-Fi driver's pinned commits (branches past them, the mirror); and the report
for the Upstream review issue."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_upstream  # noqa: E402

LOADER = check_upstream.load_loader()
UNIT = LOADER.unit_text(check_upstream.TEMPLATE).encode()
API = check_upstream.API.format(repo=LOADER.REPO)
PIN = check_upstream.load_shadps4_pin()
SHAD_API = check_upstream.API.format(repo=PIN.REPO)
HELIX = check_upstream.load_helixsr_pin()
HELIX_API = check_upstream.API.format(repo=check_upstream.HELIXSR_REPO)


def github(latest: str = LOADER.TAG, digest: str = f"sha256:{LOADER.SHA256}", unit_at_tag: bytes = UNIT,
           unit_on_main: bytes = UNIT):
    answers = {
        f"{API}/releases/latest": json.dumps({"tag_name": latest, "published_at": "2026-11-02T10:00:00Z",
                                              "html_url": f"https://github.com/{LOADER.REPO}/releases/tag/{latest}"}),
        f"{API}/releases/tags/{LOADER.TAG}": json.dumps({"assets": [{"name": "PluginLoader", "digest": digest}]}),
        check_upstream.RAW.format(repo=LOADER.REPO, ref=LOADER.TAG): unit_at_tag,
        check_upstream.RAW.format(repo=LOADER.REPO, ref="main"): unit_on_main,
    }

    def get(url: str) -> bytes:
        answer = answers[url]
        return answer if isinstance(answer, bytes) else answer.encode()
    return get


def test_the_template_is_deckys_file():
    """unit_text() with ${HOMEBREW_FOLDER} as the folder is Decky's file before its installer fills it in."""
    assert b"ExecStart=${HOMEBREW_FOLDER}/services/PluginLoader\n" in UNIT


def test_in_step():
    report = check_upstream.check(LOADER, github())
    assert report.drift == [] and len(report.fine) == 4
    assert report.text().startswith(f"Decky Loader: pinned {LOADER.TAG}, latest stable {LOADER.TAG}. In step.")


@pytest.mark.parametrize("latest, moved", [("v3.3.2", True), ("v3.4.0", True), ("v4.0.0", True),
                                           ("v3.2.10", False), (LOADER.TAG, False)])
def test_a_newer_release(latest, moved):
    report = check_upstream.check(LOADER, github(latest=latest))
    assert bool(report.drift) == moved
    if moved:
        assert report.drift[0].startswith(f"{latest} is out (2026-11-02)") and "Decky moved:" in report.text()


def test_a_replaced_asset():
    report = check_upstream.check(LOADER, github(digest="sha256:" + "0" * 64))
    assert len(report.drift) == 1 and "the asset was replaced" in report.drift[0]


def test_a_changed_unit_on_main_only():
    changed = UNIT.replace(b"LOG_LEVEL=INFO", b"LOG_LEVEL=INFO\nEnvironment=NEW=1")
    report = check_upstream.check(LOADER, github(unit_on_main=changed))
    assert len(report.drift) == 1 and report.drift[0].startswith("main's (Decky's updater installs it)")
    report = check_upstream.check(LOADER, github(unit_at_tag=changed, unit_on_main=changed))
    assert len(report.drift) == 2


def test_exit_codes(monkeypatch, capsys, tmp_path):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    real = check_upstream.check
    monkeypatch.setattr(check_upstream, "check", lambda loader: real(loader, github()))
    assert check_upstream.main(["decky"]) == 0 and "In step." in summary.read_text()
    monkeypatch.setattr(check_upstream, "check", lambda loader: real(loader, github("v3.4.0")))
    assert check_upstream.main(["decky"]) == 1

    def offline(loader):
        raise check_upstream.CheckError("https://api.github.com/...: GitHub answered 403")
    monkeypatch.setattr(check_upstream, "check", offline)
    assert check_upstream.main(["decky"]) == 2 and "could not be checked" in capsys.readouterr().err
    assert check_upstream.main(["nothing"]) == 2 and "Unknown: nothing" in capsys.readouterr().err


# --- shadPS4 ----------------------------------------------------------------------------------------------------

def shad_github(latest: str = PIN.TAG, digest: str = f"sha256:{PIN.SHA256}",
                new_digest: str | None = "sha256:" + "ab" * 32):
    version = latest.lstrip("v.")
    new_assets = [{"name": PIN.ASSET.replace(PIN.VERSION, version), "digest": new_digest},
                  {"name": f"shadps4-win64-sdl-{version}.zip", "digest": "sha256:" + "cd" * 32}]
    answers = {
        f"{SHAD_API}/releases/latest": {"tag_name": latest, "published_at": "2026-11-20T10:00:00Z",
                                         "html_url": f"https://github.com/{PIN.REPO}/releases/tag/{latest}",
                                         "assets": new_assets},
        f"{SHAD_API}/releases/tags/{PIN.TAG}": {"assets": [{"name": PIN.ASSET, "digest": digest}]},
    }
    return lambda url: json.dumps(answers[url]).encode()


def test_the_shadps4_pin_is_read_from_emulator_py():
    assert PIN.REPO == "shadps4-emu/shadPS4" and PIN.TAG == f"v.{PIN.VERSION}" and PIN.VERSION in PIN.ASSET
    assert len(PIN.SHA256) == 64


def test_shadps4_in_step():
    report = check_upstream.check_shadps4(PIN, shad_github())
    assert report.drift == [] and len(report.fine) == 2
    assert report.text().startswith(f"shadPS4: pinned {PIN.TAG}, latest stable {PIN.TAG}. In step.")


@pytest.mark.parametrize("bump", [(0, 0, 1), (0, 1, 0), (1, 0, 0)])
def test_a_newer_shadps4_gives_what_the_pin_needs(bump):
    major, minor, patch = (int(p) for p in PIN.VERSION.split("."))
    latest = f"v.{major + bump[0]}.{minor + bump[1]}.{patch + bump[2]}"
    report = check_upstream.check_shadps4(PIN, shad_github(latest))
    assert len(report.drift) == 1 and "shadPS4 moved:" in report.text()
    assert report.drift[0].startswith(f"{latest} is out (2026-11-20)")
    assert f"for the pin: {PIN.ASSET.replace(PIN.VERSION, latest[2:])}, sha256:{'ab' * 32}" in report.drift[0]
    report = check_upstream.check_shadps4(PIN, shad_github(latest, new_digest=None))
    assert "published without a SHA-256" in report.drift[0]


def test_an_older_shadps4_is_not_newer():
    assert check_upstream.check_shadps4(PIN, shad_github("v.0.18.0")).drift == []


def test_a_replaced_shadps4_zip():
    report = check_upstream.check_shadps4(PIN, shad_github(digest="sha256:" + "0" * 64))
    assert len(report.drift) == 1 and "the asset was replaced" in report.drift[0]


# --- HelixSR ----------------------------------------------------------------------------------------------------

def helix_github(latest: str = f"v{HELIX.KNOWN_VERSION}", body: str | None = None, fallback_zip: bool = True,
                 fallback_gone: bool = False):
    version = latest.lstrip("v")
    body = (f"If {version} does not work for you, use [HelixSR {HELIX.FALLBACK_VERSION}]"
            f"(https://github.com/lonewolf0622/HelixSR/releases/tag/v{HELIX.FALLBACK_VERSION})."
            if body is None else body)
    answers = {
        f"{HELIX_API}/releases/latest": {"tag_name": latest, "published_at": "2026-10-15T10:06:18Z", "body": body,
                                          "html_url": f"https://github.com/lonewolf0622/HelixSR/releases/tag/{latest}",
                                          "assets": [{"name": "HelixSR-Scaler-1.0.3.zip"},
                                                     {"name": f"HelixSR-{version}.zip"}]},
        f"{HELIX_API}/releases/tags/v{HELIX.FALLBACK_VERSION}": {
            "assets": [{"name": f"HelixSR-{HELIX.FALLBACK_VERSION}.zip"}] if fallback_zip else []},
    }

    def get(url: str) -> bytes:
        if fallback_gone and url.endswith(f"/v{HELIX.FALLBACK_VERSION}"):
            raise check_upstream.CheckError(f"{url}: GitHub answered 404")
        return json.dumps(answers[url]).encode()
    return get


def test_the_helixsr_constants_are_read_from_acquire_py():
    assert HELIX.KNOWN_VERSION.count(".") == 2 and HELIX.FALLBACK_VERSION.count(".") == 2
    assert HELIX.SUPPORTED_MAJOR == int(HELIX.KNOWN_VERSION.split(".")[0])
    assert f"repos/{check_upstream.HELIXSR_REPO}/" in check_upstream.ACQUIRE.read_text(encoding="utf-8")


def test_helixsr_in_step():
    report = check_upstream.check_helixsr(HELIX, helix_github())
    assert report.drift == [] and len(report.fine) == 3
    assert report.text().startswith(f"HelixSR: known v{HELIX.KNOWN_VERSION}, latest stable v{HELIX.KNOWN_VERSION}. "
                                     "In step.")


def test_a_newer_helixsr():
    newer = f"v{HELIX.SUPPORTED_MAJOR}.99.0"
    report = check_upstream.check_helixsr(HELIX, helix_github(newer))
    assert len(report.drift) == 1 and "HelixSR moved:" in report.text()
    assert report.drift[0].startswith(f"{newer} is out (2026-10-15)")
    assert f"HelixSR-{newer[1:]}.zip is there" in report.drift[0] and f"set KNOWN_VERSION to {newer[1:]}" in report.drift[0]
    assert check_upstream.check_helixsr(HELIX, helix_github("v1.0.0")).drift == []


def test_a_new_helixsr_major_is_not_offered():
    report = check_upstream.check_helixsr(HELIX, helix_github(f"v{HELIX.SUPPORTED_MAJOR + 1}.0.0"))
    assert len(report.drift) == 1 and "a new major version" in report.drift[0]
    assert f"stays on {HELIX.SUPPORTED_MAJOR}.x" in report.drift[0] and "KNOWN_VERSION" not in report.drift[0]


@pytest.mark.parametrize("body, moved", [("If it does not work for you, use HelixSR 1.4.3.", True),
                                         ("use [HelixSR v9.9.9](https://x)", True),
                                         ("No fallback this time.", False), ("", False)])
def test_the_fallback_the_notes_name(body, moved):
    report = check_upstream.check_helixsr(HELIX, helix_github(body=body))
    assert bool(report.drift) == moved
    if moved:
        assert "as the fallback, the app offers" in report.drift[0]


def test_a_fallback_without_its_zip():
    assert "has no zip any more" in check_upstream.check_helixsr(HELIX, helix_github(fallback_zip=False)).drift[0]
    assert "is gone from GitHub" in check_upstream.check_helixsr(HELIX, helix_github(fallback_gone=True)).drift[0]


# --- PPSSPP, PCSX2, RPCS3 and DirectMesh: a pin a newer release moves -------------------------------------

@pytest.mark.parametrize("name, constant", [("ppsspp", "VERSION"), ("pcsx2", "VERSION"), ("rpcs3", "LANDMARK"),
                                            ("directmesh", "DIRECTMESH")])
def test_the_pins_are_read_from_the_apps(name, constant):
    pin = check_upstream.load_release(name)
    assert pin.pinned and pin.repo.count("/") == 1 and pin.where.startswith(constant)
    assert bool(pin.prefix) == (name == "directmesh")


def latest_github(pin, tag: str):
    answer = {"tag_name": tag, "published_at": "2026-11-20T10:00:00Z", "html_url": f"https://github.com/x/{tag}"}
    return {f"{check_upstream.API.format(repo=pin.repo)}/releases/latest": answer}


@pytest.mark.parametrize("name", ["ppsspp", "pcsx2", "rpcs3"])
def test_a_newer_release_moves_a_pin(name):
    pin = check_upstream.load_release(name)
    answers = latest_github(pin, f"v{pin.pinned}")
    report = check_upstream.check_release(pin, lambda url: json.dumps(answers[url]).encode())
    assert report.drift == [] and "In step." in report.text()
    newer = ".".join(pin.pinned.split(".")[:-1] + [str(int(pin.pinned.split(".")[-1]) + 1)])
    answers = latest_github(pin, f"v{newer}")
    report = check_upstream.check_release(pin, lambda url: json.dumps(answers[url]).encode())
    assert report.drift[0].startswith(f"v{newer} is out (2026-11-20): a new version of the")
    assert pin.where in report.drift[0]


def test_directmesh_takes_its_own_tags_only():
    pin = check_upstream.load_release("directmesh")
    url = f"{check_upstream.API.format(repo=pin.repo)}/releases?per_page=100"

    def get(releases):
        return lambda asked: json.dumps({url: releases}[asked]).encode()
    same = {"tag_name": f"directmesh-{pin.pinned}", "published_at": "2026-10-01T00:00:00Z"}
    other = [{"tag_name": "v99.0", "published_at": ""},                                   # not DirectMesh's tag
             {"tag_name": "directmesh-v9.0", "prerelease": True, "published_at": ""},
             {"tag_name": "directmesh-v131-auto-rdna1-975ec91", "published_at": ""}]     # a candidate, not v131
    assert check_upstream.check_release(pin, get([same, *other])).drift == []
    newer = {"tag_name": "directmesh-v9.1", "published_at": "2026-11-01T00:00:00Z", "html_url": "u"}
    report = check_upstream.check_release(pin, get([same, newer, *other]))
    assert report.latest == "v9.1" and report.drift[0].startswith("v9.1 is out (2026-11-01)")
    assert check_upstream.check_release(pin, get([])).latest == ""


def test_the_report_for_the_issue(monkeypatch, tmp_path):
    moved = check_upstream.Report("v1.0", name="PPSSPP", short="PPSSPP", latest="v1.1", drift=["v1.1 is out"])
    fine = check_upstream.Report("v2.0", name="RPCS3", short="RPCS3", latest="v2.0", fine=["in step"])
    calls = {"ppsspp": lambda: moved, "rpcs3": lambda: fine}

    def offline():
        raise check_upstream.CheckError("GitHub answered 403")
    calls["pcsx2"] = offline
    monkeypatch.setattr(check_upstream, "CHECKS", {k: (k.upper(), v) for k, v in calls.items()})
    report = tmp_path / "upstream.md"
    assert check_upstream.main(["--report", str(report), "ppsspp", "rpcs3"]) == 1
    text = report.read_text()
    assert "### PPSSPP\n\nPinned v1.0, latest stable v1.1.\n\n- v1.1 is out" in text and "RPCS3" not in text
    assert check_upstream.main(["--report", str(report), "rpcs3"]) == 0 and report.read_text() == ""
    assert check_upstream.main(["--report", str(report), "ppsspp", "pcsx2"]) == 2
    assert "Not checked this week: PCSX2 (GitHub answered 403)" in report.read_text()
    assert check_upstream.main(["--report"]) == 2


# --- Vita3K and Xenia: the build each manager brings --------------------------------------------------------------

def build_github(pin, latest: str, published: str, digest: str | None = "pinned", gone: bool = False):
    api = check_upstream.API.format(repo=pin.repo)
    asset = {"name": pin.asset, "digest": f"sha256:{pin.sha256}" if digest == "pinned" else digest}
    answers = {f"{api}/releases/latest": {"tag_name": latest, "published_at": published, "html_url": f"u/{latest}"},
               f"{api}/releases/tags/{pin.build}": {"assets": [] if digest == "no asset" else [asset]}}

    def get(url: str) -> bytes:
        if gone and url.endswith(f"/tags/{pin.build}"):
            raise check_upstream.CheckError(f"{url}: GitHub answered 404")
        return json.dumps(answers[url]).encode()
    return get


@pytest.mark.parametrize("name", ["vita3k", "xenia"])
def test_the_builds_are_read_from_the_apps(name):
    pin = check_upstream.load_build(name)
    assert pin.build and len(pin.sha256) == 64 and pin.asset.endswith(".AppImage") and pin.repo.count("/") == 1
    assert bool(pin.published) == (name == "xenia") and pin.where.startswith("BUILD, SHA256 in apps/")


def test_vita3k_a_higher_build_number_is_newer():
    pin = check_upstream.load_build("vita3k")
    report = check_upstream.check_build(pin, build_github(pin, pin.build, "2026-10-01T00:00:00Z"))
    assert report.drift == [] and "newest build" in report.text() and "In step." in report.text()
    later = str(int(pin.build) + 3)
    report = check_upstream.check_build(pin, build_github(pin, later, "2026-11-04T12:00:00Z"))
    assert report.drift[0].startswith(f"build {later} is out (2026-11-04, 3 builds later): a new version of the Vita3K")
    assert check_upstream.check_build(pin, build_github(pin, "continuous", "2026-11-04T12:00:00Z")).drift == []


def test_xenia_a_build_published_later_is_newer():
    pin = check_upstream.load_build("xenia")
    assert check_upstream.check_build(pin, build_github(pin, pin.build, pin.published)).drift == []
    assert check_upstream.check_build(pin, build_github(pin, "0000001", "2020-01-01T00:00:00Z")).drift == []
    report = check_upstream.check_build(pin, build_github(pin, "abc1234", "2099-01-01T00:00:00Z"))
    assert report.drift[0].startswith("build abc1234 is out (2099-01-01): a new version of the Xenia Manager")


@pytest.mark.parametrize("name", ["vita3k", "xenia"])
def test_the_pinned_appimage(name):
    pin = check_upstream.load_build(name)
    same = (pin.build, pin.published or "2026-10-01T00:00:00Z")
    assert "still the pinned file" in check_upstream.check_build(pin, build_github(pin, *same)).fine[-1]
    assert "without a SHA-256" in check_upstream.check_build(pin, build_github(pin, *same, digest=None)).fine[-1]
    replaced = check_upstream.check_build(pin, build_github(pin, *same, digest="sha256:" + "0" * 64))
    assert "the asset was replaced" in replaced.drift[0]
    assert "any more" in check_upstream.check_build(pin, build_github(pin, *same, digest="no asset")).drift[0]
    assert "is gone from GitHub" in check_upstream.check_build(pin, build_github(pin, *same, gone=True)).drift[0]


# --- BC-250 USB Wi-Fi: the driver's pinned commits ----------------------------------------------------------------

BUILDER = check_upstream.load_loader(check_upstream.BUILDER, "wdriver_builder_pin")
UPSTREAM_API = check_upstream.API.format(repo="shenmintao/aic8800d80")
MIRROR_API = check_upstream.API.format(repo="RobertoTorino/aic8800d80")


def driver_github(ahead: dict[str, int] | None = None, mirror: str = "all"):
    """*ahead*: commits past the pin per branch; *mirror*: "all", "none" (the repository missing) or a branch it
    lacks."""
    ahead = ahead or {}

    def get(url: str) -> bytes:
        for branch, pin in BUILDER.PINS.items():
            if url == f"{UPSTREAM_API}/compare/{pin.commit}...{branch}":
                n = ahead.get(branch, 0)
                commits = [{"sha": f"{i:07d}" + "f" * 33, "commit": {"committer": {"date": "2026-11-02T06:38:11Z"}}}
                           for i in range(n)]
                return json.dumps({"ahead_by": n, "commits": commits, "html_url": f"c/{branch}"}).encode()
            if url == f"{MIRROR_API}/commits/{pin.commit}":
                if mirror == branch:
                    raise check_upstream.CheckError(f"{url}: GitHub answered 422")
                return b"{}"
        if url == MIRROR_API:
            if mirror == "none":
                raise check_upstream.CheckError(f"{url}: GitHub answered 404")
            return b"{}"
        raise AssertionError(url)
    return get


def test_the_driver_pins_are_read_from_builder_py():
    assert set(BUILDER.PINS) == {"main", "legacy-mcu1"}
    assert all(len(p.commit) == 40 for p in BUILDER.PINS.values())


def test_the_driver_in_step():
    report = check_upstream.check_wdriver(BUILDER, driver_github())
    assert report.drift == [] and "branch heads main " in report.text()
    assert "the mirror has legacy-mcu1's pinned commit" in report.fine


def test_a_branch_past_its_pin():
    report = check_upstream.check_wdriver(BUILDER, driver_github({"legacy-mcu1": 24}))
    [line] = report.drift
    pin = BUILDER.PINS["legacy-mcu1"].commit[:7]
    assert line.startswith(f"legacy-mcu1 is 24 commits past the pin {pin} (newest 0000023, 2026-11-02): a new "
                           "version of BC-250 USB Wi-Fi could move PINS")
    assert "legacy-mcu1 0000023" in report.latest and f"main {BUILDER.PINS['main'].commit[:7]}" in report.latest


def test_the_mirror():
    [line] = check_upstream.check_wdriver(BUILDER, driver_github(mirror="none")).drift
    assert "is not on GitHub (missing, or private)" in line
    [line] = check_upstream.check_wdriver(BUILDER, driver_github(mirror="main")).drift
    assert "lacks main's pinned commit" in line


# --- Mesa, FFmpeg and libva, USB HD Cam's firmware, the speedtest CLI (Bazzite/Windows 2, 05-11-2026) ---------------

def test_the_new_pins_are_read_from_the_apps():
    assert check_upstream.shell_value(check_upstream.MESH, "MESA_VER").count(".") == 2
    assert check_upstream.shell_value(check_upstream.FFMPEG_BUILD, "FFMPEG_VERSION").startswith("7.1.")
    assert check_upstream.shell_value(check_upstream.FFMPEG_BUILD, "LIBVA_VERSION").count(".") == 2
    assert check_upstream.shell_value(check_upstream.SPEEDTEST_TOOL, "SPEEDTEST_VERSION") == "1.2.0"   # ${..:-1.2.0}
    firmware = check_upstream.load_firmware()
    assert {f.model for f in firmware} == {"cfi-zey1", "ps4-camera"}
    assert all(len(f.commit) == 40 and len(f.sha256) == 64 and f.path.endswith(".bin") for f in firmware)
    assert "+++ b/src/amd/common/ac_gpu_info.c" in check_upstream.ACE_PATCH.read_text(encoding="utf-8")


def mesa(tags: list[str]):
    def get(url: str) -> bytes:
        if url == check_upstream.MESA_TAGS:
            return json.dumps([{"name": t} for t in tags]).encode()
        if url.startswith("https://gitlab.freedesktop.org/mesa/mesa/-/raw/"):
            return b"the file\n"
        raise AssertionError(url)
    return get


def test_mesa_a_newer_release_and_the_ace_patch():
    """A release candidate is no release; the ACE patch is tried on the files it touches at the newest release."""
    tried = []
    patch = "--- a/src/x.c\n+++ b/src/x.c\n@@ -1 +1 @@\n-the file\n+a file\n"

    def applies(text: str, files: dict[str, bytes]) -> bool:
        tried.append(sorted(files))
        return True
    report = check_upstream.check_mesa("26.2.1", patch, mesa(["mesa-26.3.0-rc3", "mesa-26.2.6", "mesa-26.2.1"]), applies)
    [line] = report.drift
    assert line.startswith("Mesa 26.2.6 is out: a new version of BC-250 Mesh Shaders could build it")
    assert report.latest == "26.2.6" and tried == [["src/x.c"]]
    assert "BC-250 ACE Queues' patch applies to Mesa 26.2.6" in report.fine
    stale = check_upstream.check_mesa("26.2.6", patch, mesa(["mesa-26.2.6"]), lambda text, files: False)
    [line] = stale.drift
    assert "does not apply to Mesa 26.2.6: once Bazzite ships it, the app cannot build for it" in line


@pytest.mark.skipif(not __import__("shutil").which("patch"), reason="needs patch")
def test_patch_applies_tries_it_for_real():
    patch = "--- a/src/x.c\n+++ b/src/x.c\n@@ -1 +1 @@\n-the file\n+a file\n"
    assert check_upstream.patch_applies(patch, {"src/x.c": b"the file\n"})
    assert not check_upstream.patch_applies(patch, {"src/x.c": b"another file\n"})


def ffmpeg(tags: list[str], libva: str):
    def get(url: str) -> bytes:
        if url.endswith("FFmpeg/FFmpeg/git/matching-refs/tags/n"):
            return json.dumps([{"ref": f"refs/tags/{t}"} for t in tags]).encode()
        if url.endswith("intel/libva/releases/latest"):
            return json.dumps({"tag_name": libva}).encode()
        raise AssertionError(url)
    return get


def test_ffmpeg_and_libva():
    """A point release on the pinned branch, a newer branch and a newer libva are each a line; a development tag
    (n8.1-dev) is no release."""
    report = check_upstream.check_ffmpeg("7.1.2", "2.22.0", ffmpeg(["n7.1.2", "n7.1.5", "n8.1-dev", "n9.0.2"], "2.24.1"))
    assert report.latest == "FFmpeg 9.0.2 (7.1.x: 7.1.5), libva 2.24.1"
    assert [line.split(":")[0] for line in report.drift] == [
        "FFmpeg 7.1.5 is out, on the pinned 7.1 branch", "FFmpeg 9.0.2 is a newer branch than 7.1",
        "libva 2.24.1 is out"]
    still = check_upstream.check_ffmpeg("7.1.2", "2.22.0", ffmpeg(["n7.0.3", "n7.1.2"], "2.22.0"))
    assert still.drift == [] and still.fine == ["no FFmpeg release newer than 7.1.2", "no libva release newer than 2.22.0"]


def test_hdcam_firmware():
    """The file at the pinned commit, and the same file on the default branch: changed or gone there is a line."""
    import hashlib
    firmware = [check_upstream.Firmware("cam", "someone/fw", "a" * 40, "fw/cam.bin", hashlib.sha256(b"fw").hexdigest())]

    def raw(head: bytes | None, pinned: bytes = b"fw"):
        def get(url: str) -> bytes:
            if url == f"https://raw.githubusercontent.com/someone/fw/{'a' * 40}/fw/cam.bin":
                return pinned
            if url == "https://raw.githubusercontent.com/someone/fw/HEAD/fw/cam.bin":
                if head is None:
                    raise check_upstream.CheckError(f"{url}: GitHub answered 404")
                return head
            raise AssertionError(url)
        return get
    same = check_upstream.check_hdcam(firmware, raw(b"fw"))
    assert same.drift == [] and same.latest == "the same files"
    [line] = check_upstream.check_hdcam(firmware, raw(b"new")).drift
    assert line.startswith("cam's fw/cam.bin changed on someone/fw's default branch: a new version of USB HD Cam")
    [line] = check_upstream.check_hdcam(firmware, raw(None)).drift
    assert "is gone from someone/fw's default branch" in line
    replaced = check_upstream.check_hdcam(firmware, raw(b"fw", pinned=b"other")).drift
    assert "is not the pinned file" in replaced[0]


def test_speedtest():
    def formula(version: str):
        return lambda url: f'class Speedtest < Formula\n  version "{version}"\nend\n'.encode()
    assert check_upstream.check_speedtest("1.2.0", formula("1.2.0")).drift == []
    [line] = check_upstream.check_speedtest("1.2.0", formula("1.3.0")).drift
    assert line.startswith("speedtest 1.3.0 is out: the development tool could install it")
