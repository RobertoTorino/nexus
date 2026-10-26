# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/check_upstream.py on a fake GitHub: in step, a newer Decky release, a replaced asset, a changed service unit
(at the pinned tag or only on main), no network; the same for shadPS4's pin, read from emulator.py; and HelixSR
against what acquire.py knows (a newer release, another fallback in the notes, a fallback without its zip); the pins
of PPSSPP, PCSX2, RPCS3 and DirectMesh against a newer release; and the report for the Upstream review
issue."""

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


@pytest.mark.parametrize("latest, moved", [("v3.3.1", True), ("v3.4.0", True), ("v4.0.0", True),
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
             {"tag_name": "directmesh-v9.0", "prerelease": True, "published_at": ""}]
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
