# SPDX-License-Identifier: GPL-3.0-or-later
"""acquire.py with file:// URLs, a fake helixsr-setup.sh and a fake builder: no network, no Proton."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import urllib.error
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest import mock

import pytest

from upscaler import acquire, backend
from upscaler.acquire import (
    Pin, ReleaseInfo, SetupRequest, SetupWorker, UpdateStatus, download, extract_zip, find_dlss_dlls, latest_release,
    needed_pins, parse_pins, unpack_dxc, unpack_python,
)
from tests.conftest import FAKE_DLL

DLSS_BYTES = b"MZ-fake-nvngx-dlss-310.7.0"
DLSS_SHA = hashlib.sha256(DLSS_BYTES).hexdigest()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_dxc_zip(path: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("bin\\x64\\dxc.exe", b"MZ-dxc")
        zf.writestr("bin\\x64\\dxcompiler.dll", b"MZ-dxcompiler")
        zf.writestr("inc\\dxcapi.h", b"// header")
    path.write_bytes(buf.getvalue())
    return buf.getvalue()


def make_python_tgz(path: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("python/bin/python3")
        info.size, info.mode = 5, 0o755
        tar.addfile(info, io.BytesIO(b"#!py\n"))
    path.write_bytes(buf.getvalue())
    return buf.getvalue()


def make_release_zip(tmp_path: Path, pins: dict[str, tuple[str, str]], script_body: str) -> tuple[Path, bytes]:
    """A HelixSR-like release zip whose scripts pin the given (url, sha) per key and whose setup script is ours."""
    setup_sh = (
        "#!/usr/bin/env bash\n"
        f"PY_URL='{pins['python'][0]}'\nPY_SHA='{pins['python'][1]}'\n"
        f"DXCWIN_URL='{pins['dxc'][0]}'\nDXCWIN_SHA='{pins['dxc'][1]}'\n"
        + script_body)
    setup_py = f"DLSS_URL = '{pins['dlss'][0]}'\nDLSS_SHA256 = '{pins['dlss'][1]}'\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("HelixSR-1.2.0/helixsr-setup.sh", setup_sh)
        zf.writestr("HelixSR-1.2.0/setup/helixsr_setup.py", setup_py)
        zf.writestr("HelixSR-1.2.0/amd_fidelityfx_dx12.dll", FAKE_DLL)
        zf.writestr("HelixSR-1.2.0/helixsr.ini", backend.DEFAULT_INI_TEXT)
        zf.writestr("HelixSR-1.2.0/README.md", "**Version 1.2.0**\n")
    path = tmp_path / "HelixSR-1.2.0.zip"
    path.write_bytes(buf.getvalue())
    return path, buf.getvalue()


# The fake script records its arguments and writes the network files, like the real one does on success.
GOOD_SCRIPT = """
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo "[fake-setup] args: $*"
echo "[fake-setup] XDG_DATA_HOME=$XDG_DATA_HOME"
printf '%s\\n' "$*" > "$HERE/args.txt"
for a in "$@"; do if [ "$prev" = "--dlss" ]; then cp "$a" "$HERE/dlss-used.bin"; fi; prev=$a; done
echo weights > "$HERE/helixsr_weights.bin"
echo kernels > "$HERE/helixsr_kernels.pak"
"""
BAD_SCRIPT = "echo '[fake-setup] boom' >&2\nexit 3\n"


# ------------------------------------------------------------------------------------------ releases
def test_latest_release_parses_github_json():
    payload = {"tag_name": "v1.2.0", "html_url": "https://x/rel", "published_at": "2026-10-06T23:04:52Z",
               "assets": [{"name": "HelixSR-1.2.0.zip", "browser_download_url": "https://x/z.zip", "size": 2315352}]}
    with mock.patch.object(acquire, "_get_json", return_value=payload):
        info = latest_release("api", "page")
    assert info == ReleaseInfo("1.2.0", "v1.2.0", "https://x/rel", "2026-10-06", "HelixSR-1.2.0.zip", "https://x/z.zip",
                               2315352)
    with mock.patch.object(acquire, "_get_json", side_effect=OSError("no route")):
        assert "no connection" in latest_release("api", "page").error
    with mock.patch.object(acquire, "_get_json", return_value={"tag_name": "latest"}):
        assert "unexpected tag" in latest_release("api", "page").error


def test_latest_release_takes_helixsrs_own_zip():
    """From 1.9.0 on a release also has HelixSR Scaler's zip, whichever comes first."""
    assets = [{"name": "HelixSR-Scaler-1.0.3.zip", "browser_download_url": "https://x/scaler.zip", "size": 132504212},
              {"name": "HelixSR-Scaler-1.0.3-linux.tar.gz", "browser_download_url": "https://x/s.tgz", "size": 1},
              {"name": "HelixSR-1.9.0.zip", "browser_download_url": "https://x/z.zip", "size": 3803249}]
    with mock.patch.object(acquire, "_get_json", return_value={"tag_name": "v1.9.0", "assets": assets}):
        info = latest_release("api", "page")
    assert (info.asset_name, info.asset_url, info.asset_size) == ("HelixSR-1.9.0.zip", "https://x/z.zip", 3803249)


def test_update_status():
    latest = ReleaseInfo("1.2.0", "v1.2.0", "u", "2026-10-06")
    assert UpdateStatus("x", "1.1.0", latest).update_available and UpdateStatus("x", "1.1.0", latest).kind == "warn"
    assert not UpdateStatus("x", "1.2.0", latest).update_available and UpdateStatus("x", "1.2.0", latest).kind == "ok"
    assert UpdateStatus("x", "", latest).kind == "info"
    assert "unknown" in UpdateStatus("x", "1.0.0", ReleaseInfo(error="GitHub answered 403")).summary
    assert "→ 1.2.0" in UpdateStatus("x", "1.1.0", latest).summary


# ------------------------------------------------------------------------------------------ download
def test_download_verifies_checksum(tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"x" * 1000)
    seen = []
    out = download(src.as_uri(), tmp_path / "out" / "dst.bin", sha(b"x" * 1000), progress=lambda *a: seen.append(a))
    assert out.read_bytes() == b"x" * 1000 and seen[-1][1] == 1000
    with pytest.raises(backend.HelixError, match="checksum"):
        download(src.as_uri(), tmp_path / "bad.bin", "0" * 64)
    assert not (tmp_path / "bad.bin").exists() and not (tmp_path / "bad.bin.part").exists()
    with pytest.raises(backend.HelixError):
        download((tmp_path / "missing").as_uri(), tmp_path / "x.bin")
    with pytest.raises(acquire.Aborted):
        download(src.as_uri(), tmp_path / "c.bin", cancelled=lambda: True)



def http_error(code):
    return urllib.error.HTTPError("https://h/f.bin", code, "error", {}, None)


def test_download_retries_a_busy_server(tmp_path, monkeypatch):
    monkeypatch.setattr(acquire, "RETRY_PAUSE", 0)
    src = tmp_path / "src.bin"
    src.write_bytes(b"y" * 10)
    real = acquire.urllib.request.urlopen
    answers = [http_error(502), http_error(503)]

    def urlopen(request, timeout):
        if answers:
            raise answers.pop(0)
        return real(src.as_uri(), timeout=timeout)
    with mock.patch.object(acquire.urllib.request, "urlopen", urlopen):
        out = download("https://h/f.bin", tmp_path / "ok.bin", sha(b"y" * 10))
    assert out.read_bytes() == b"y" * 10 and not answers


def test_download_gives_up_after_five_tries(tmp_path, monkeypatch):
    monkeypatch.setattr(acquire, "RETRY_PAUSE", 0)
    calls = []

    def busy(request, timeout):
        calls.append(request)
        raise http_error(502)
    with mock.patch.object(acquire.urllib.request, "urlopen", busy):
        with pytest.raises(backend.HelixError, match=r"^NVIDIA DLSS DLL: Server currently not available\. "
                                                     r"Try again later\.$"):
            download("https://h/f.bin", tmp_path / "f.bin", name="NVIDIA DLSS DLL")
    assert len(calls) == 5 and not (tmp_path / "f.bin.part").exists()

    calls.clear()

    def missing(request, timeout):
        calls.append(request)
        raise http_error(404)
    with mock.patch.object(acquire.urllib.request, "urlopen", missing):
        with pytest.raises(backend.HelixError, match="server answered 404"):
            download("https://h/f.bin", tmp_path / "f.bin")
    assert len(calls) == 1


def test_download_cancel_during_the_pause(tmp_path, monkeypatch):
    monkeypatch.setattr(acquire, "RETRY_PAUSE", 60)
    tries = []

    def busy(request, timeout):
        tries.append(request)
        raise http_error(504)
    with mock.patch.object(acquire.urllib.request, "urlopen", busy):
        with pytest.raises(acquire.Aborted):
            download("https://h/f.bin", tmp_path / "f.bin", cancelled=lambda: bool(tries))
    assert len(tries) == 1


def test_parse_pins_and_extract(tmp_path):
    pins = {"dlss": ("https://n/nvngx_dlss.dll", "a" * 64), "dxc": ("https://m/dxc_1.zip", "b" * 64),
            "python": ("https://p/cpython-3.12%2Bx.tar.gz", "c" * 64)}
    archive, _ = make_release_zip(tmp_path, pins, GOOD_SCRIPT)
    release_dir = extract_zip(archive, tmp_path / "extracted")
    assert release_dir.name == "HelixSR-1.2.0" and (release_dir / "helixsr-setup.sh").stat().st_mode & 0o100
    parsed = parse_pins(release_dir)
    assert {k: (p.url, p.sha256) for k, p in parsed.items()} == pins
    assert parsed["python"].filename == "cpython-3.12+x.tar.gz"
    assert parse_pins(tmp_path / "nowhere") == {}


def test_extract_zip_rejects_traversal(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.sh", "x")
    (tmp_path / "evil.zip").write_bytes(buf.getvalue())
    with pytest.raises(backend.HelixError):
        extract_zip(tmp_path / "evil.zip", tmp_path / "out")


def test_unpack_prerequisites(tmp_path):
    data = tmp_path / "HelixSR"
    make_dxc_zip(tmp_path / "dxc.zip")
    unpack_dxc(tmp_path / "dxc.zip", data)
    assert (data / "dxc-win" / "bin" / "x64" / "dxc.exe").read_bytes() == b"MZ-dxc"
    assert not (data / "dxc-win" / "inc").exists()
    assert acquire.dxc_present(data)
    make_python_tgz(tmp_path / "py.tgz")
    unpack_python(tmp_path / "py.tgz", data)
    assert acquire.portable_python_present(data)


def test_needed_pins(tmp_path):
    pins = {k: Pin(k, f"https://x/{k}", "0" * 64, k) for k in ("dlss", "dxc", "python")}
    data = tmp_path / "HelixSR"
    with mock.patch.object(acquire, "system_python_has_numpy", return_value=True):
        assert [p.key for p in needed_pins(pins, data, None, immutable=False)] == ["dlss", "dxc"]
        assert [p.key for p in needed_pins(pins, data, None, immutable=True)] == ["dlss", "dxc", "python"]
        assert [p.key for p in needed_pins(pins, data, tmp_path / "nvngx_dlss.dll", True)] == ["dxc", "python"]
    with mock.patch.object(acquire, "system_python_has_numpy", return_value=False):
        assert "python" in [p.key for p in needed_pins(pins, data, None, immutable=False)]
    make_dxc_zip(tmp_path / "dxc.zip")
    unpack_dxc(tmp_path / "dxc.zip", data)
    make_python_tgz(tmp_path / "py.tgz")
    unpack_python(tmp_path / "py.tgz", data)
    assert needed_pins(pins, data, tmp_path / "d.dll", True) == []
    assert needed_pins({}, data, None, True) == []


def test_find_dlss_dlls(tmp_path):
    lib = tmp_path / "steamapps"
    good = lib / "common" / "GameA" / "nvngx_dlss.dll"
    other = lib / "common" / "GameB" / "bin" / "nvngx_dlss.dll"
    for p, data in ((good, DLSS_BYTES), (other, b"older dlss")):
        p.parent.mkdir(parents=True)
        p.write_bytes(data)
    assert find_dlss_dlls([lib], DLSS_SHA) == [good]
    assert find_dlss_dlls([lib], "f" * 64) == []
    assert find_dlss_dlls([tmp_path / "missing"], DLSS_SHA) == []


# ------------------------------------------------------------------------------------- the whole run
def run_worker(qapp, request: SetupRequest):
    from PyQt6.QtCore import QEventLoop, QTimer
    worker = SetupWorker(request)
    log, outcome = [], []
    worker.log.connect(log.append)
    worker.stage.connect(log.append)
    worker.finished_with.connect(outcome.append)
    loop = QEventLoop()
    worker.finished_with.connect(loop.quit)
    QTimer.singleShot(20000, loop.quit)
    worker.start()
    loop.exec()
    worker.wait(5000)
    assert outcome, "worker did not finish"
    return outcome[0], log


def prepared(tmp_path, script_body=GOOD_SCRIPT):
    dlss = tmp_path / "srv" / "nvngx_dlss.dll"
    dlss.parent.mkdir()
    dlss.write_bytes(DLSS_BYTES)
    dxc = make_dxc_zip(tmp_path / "srv" / "dxc.zip")
    py = make_python_tgz(tmp_path / "srv" / "py.tgz")
    pins = {"dlss": (dlss.as_uri(), DLSS_SHA), "dxc": ((tmp_path / "srv" / "dxc.zip").as_uri(), sha(dxc)),
            "python": ((tmp_path / "srv" / "py.tgz").as_uri(), sha(py))}
    archive, data = make_release_zip(tmp_path / "srv", pins, script_body)
    release = ReleaseInfo("1.2.0", "v1.2.0", "u", "2026-10-06", archive.name, archive.as_uri(), len(data))
    return release, dlss


def test_setup_worker_end_to_end(qapp, tmp_path):
    release, _ = prepared(tmp_path)
    request = SetupRequest(release, tmp_path / "work", tmp_path / "data" / "HelixSR")
    with mock.patch.object(acquire, "is_immutable_system", return_value=True):
        outcome, log = run_worker(qapp, request)
    assert outcome.ok, outcome.message
    rd = outcome.release_dir
    assert rd is not None and (rd / backend.WEIGHTS).is_file() and (rd / backend.KERNELS).is_file()
    args = (rd / "args.txt").read_text()
    assert "--yes" in args and "--dlss" in args
    assert (rd / "dlss-used.bin").read_bytes() == DLSS_BYTES          # the downloaded DLL was handed to the script
    assert not (tmp_path / "work" / "nvngx_dlss.dll").exists()        # and deleted afterwards
    assert acquire.dxc_present(request.helix_data) and acquire.portable_python_present(request.helix_data)
    assert any("XDG_DATA_HOME=" + str(tmp_path / "data") in line for line in log)
    assert any("in parallel" in line for line in log)
    assert backend.import_payload(rd, tmp_path / "payload").missing == []
    assert acquire.latest_work_release(tmp_path / "work") == rd


def test_setup_worker_uses_local_dlss_and_cached_tools(qapp, tmp_path):
    release, dlss = prepared(tmp_path)
    local = tmp_path / "GameA" / "nvngx_dlss.dll"
    local.parent.mkdir()
    local.write_bytes(DLSS_BYTES)
    data = tmp_path / "data" / "HelixSR"
    make_dxc_zip(tmp_path / "d.zip")
    unpack_dxc(tmp_path / "d.zip", data)
    make_python_tgz(tmp_path / "p.tgz")
    unpack_python(tmp_path / "p.tgz", data)
    with mock.patch.object(acquire, "download", wraps=acquire.download) as dl, \
            mock.patch.object(acquire, "is_immutable_system", return_value=True):
        outcome, log = run_worker(qapp, SetupRequest(release, tmp_path / "work", data, local))
    assert outcome.ok, outcome.message
    assert dl.call_count == 1                                          # only the release zip
    assert f"--dlss {local}" in (outcome.release_dir / "args.txt").read_text()
    assert local.exists()                                              # the user's file is never deleted


def test_setup_worker_reports_script_failure(qapp, tmp_path):
    release, _ = prepared(tmp_path, BAD_SCRIPT)
    with mock.patch.object(acquire, "is_immutable_system", return_value=True):
        outcome, log = run_worker(qapp, SetupRequest(release, tmp_path / "work", tmp_path / "data" / "HelixSR"))
    assert not outcome.ok and "code 3" in outcome.message
    assert any("boom" in line for line in log)
    assert not (tmp_path / "work" / "nvngx_dlss.dll").exists()


def test_setup_worker_checksum_failure_keeps_nothing(qapp, tmp_path):
    release, dlss = prepared(tmp_path)
    dlss.write_bytes(b"tampered")
    with mock.patch.object(acquire, "is_immutable_system", return_value=True):
        outcome, _ = run_worker(qapp, SetupRequest(release, tmp_path / "work", tmp_path / "data" / "HelixSR"))
    assert not outcome.ok and "checksum" in outcome.message
    assert not list((tmp_path / "work").glob("*.part")) and not (tmp_path / "work" / "nvngx_dlss.dll").exists()


def test_setup_worker_release_error(qapp, tmp_path):
    outcome, _ = run_worker(qapp, SetupRequest(ReleaseInfo(error="no connection (x)"), tmp_path / "work",
                                               tmp_path / "data"))
    assert not outcome.ok and "no connection" in outcome.message


def gh_release(version: str, prerelease: bool = False, zip_name: str | None = None) -> dict:
    name = f"HelixSR-{version}.zip" if zip_name is None else zip_name
    return {"tag_name": f"v{version}", "prerelease": prerelease, "draft": False, "published_at": "2026-10-16T08:00:00Z",
            "assets": [{"name": "HelixSR-Scaler-1.1.0.zip", "browser_download_url": "https://x/s.zip", "size": 1},
                       {"name": name, "browser_download_url": f"https://x/{name}", "size": 3,
                        "digest": "sha256:" + "AB" * 32}]}


# GitHub's list as it was on 19-10-2026, newest first: 2.0.0 changed its setup, 1.9.2 was a pre-release.
RELEASES = [gh_release("2.0.0"), gh_release("1.9.3"), gh_release("1.9.2", prerelease=True), gh_release("1.9.0"),
            gh_release("1.8.1")]


def test_update_check_covers_only_helixsr():
    with mock.patch.object(acquire, "_get_json", return_value=RELEASES) as lookup:
        statuses = acquire.check_updates("1.7.0")
    assert list(statuses) == ["helixsr"] and statuses["helixsr"].update_available       # the portal updates this app
    assert lookup.call_args.args[0] == acquire.HELIXSR_API


def test_the_newest_release_of_the_supported_major():
    """The app sets up 1.x and 2.x (owner, 20-10-2026) and says when a later major is out that it does not."""
    with mock.patch.object(acquire, "_get_json", return_value=RELEASES):
        latest, unsupported = acquire.supported_release()
    assert (latest.version, latest.asset_name, unsupported) == ("2.0.0", "HelixSR-2.0.0.zip", "")
    assert latest.asset_sha256 == "ab" * 32
    assert UpdateStatus("HelixSR", "1.9.3", latest, unsupported).summary == "1.9.3 → 2.0.0 available (2026-10-16)"
    with mock.patch.object(acquire, "_get_json", return_value=[gh_release("3.0.0"), *RELEASES]):
        latest, unsupported = acquire.supported_release()
    assert (latest.version, unsupported) == ("2.0.0", "3.0.0")
    status = UpdateStatus("HelixSR", "2.0.0", latest, unsupported)
    assert not status.update_available and status.kind == "ok"
    assert status.summary.endswith("; HelixSR 3.0.0 is out, this app does not support it yet")
    with mock.patch.object(acquire, "_get_json", return_value=RELEASES[1:]):
        assert acquire.supported_release()[0].version == "1.9.3"
    no_zip = [gh_release("3.0.0"), gh_release("2.0.0", zip_name="x.zip")]
    with mock.patch.object(acquire, "_get_json", return_value=no_zip):
        latest, unsupported = acquire.supported_release()
    assert "no HelixSR release up to 2.x" in latest.error and unsupported == "3.0.0"
    with mock.patch.object(acquire, "_get_json", side_effect=OSError("no route")):
        assert "no connection" in acquire.supported_release()[0].error
    with mock.patch.object(acquire, "_get_json", return_value={"message": "rate limit"}):
        assert "unexpected answer" in acquire.supported_release()[0].error


def test_setup_worker_refuses_another_major(qapp, tmp_path):
    release = ReleaseInfo("3.0.0", "v3.0.0", "u", "2026-10-19", "HelixSR-3.0.0.zip", "file:///nowhere.zip", 1)
    with mock.patch.object(acquire, "download") as dl:
        outcome, _ = run_worker(qapp, SetupRequest(release, tmp_path / "work", tmp_path / "data"))
    assert not outcome.ok and "HelixSR 3.0.0 is not supported yet" in outcome.message and not dl.called


def test_setup_worker_needs_free_space(qapp, tmp_path):
    release, _ = prepared(tmp_path)
    with mock.patch.object(acquire, "free_mb", return_value=100), mock.patch.object(acquire, "download") as dl:
        outcome, _ = run_worker(qapp, SetupRequest(release, tmp_path / "work", tmp_path / "data"))
    assert not outcome.ok and "Only 100 MB free" in outcome.message and not dl.called
    assert acquire.free_mb(tmp_path / "not" / "there" / "yet") > 0


def test_setup_worker_checks_the_release_zip(qapp, tmp_path):
    release, _ = prepared(tmp_path)
    release.asset_sha256 = "0" * 64
    with mock.patch.object(acquire, "is_immutable_system", return_value=True):
        outcome, _ = run_worker(qapp, SetupRequest(release, tmp_path / "work", tmp_path / "data" / "HelixSR"))
    assert not outcome.ok and "checksum" in outcome.message and not (tmp_path / "work" / release.asset_name).exists()
    release.asset_sha256 = backend.file_digest(Path(release.asset_url[len("file://"):]))
    with mock.patch.object(acquire, "is_immutable_system", return_value=True):
        outcome, _ = run_worker(qapp, SetupRequest(release, tmp_path / "work", tmp_path / "data" / "HelixSR"))
    assert outcome.ok, outcome.message


# HelixSR 1.7's script ends with its game installer, which asks per Steam game and writes manual-install/.
INSTALLER_SCRIPT = GOOD_SCRIPT + """
echo "[helixsr-setup] {installer_line}"
echo "  f = FSR   o = OptiScaler   n = skip"
printf 'GodOfWar: install? [o/n] '
if read -r answer; then echo "answered: $answer" > "$HERE/stdin.txt"; else echo "no input" > "$HERE/stdin.txt"; fi
mkdir -p "$HERE/manual-install/HelixSR" "$HERE/fsr3-drop-in"
echo weights > "$HERE/manual-install/HelixSR/helixsr_weights.bin"
cp "$HERE/amd_fidelityfx_dx12.dll" "$HERE/fsr3-drop-in/"
"""


@pytest.mark.parametrize("installer_line", ["looking for games with DLSS, XeSS or FSR ...",      # 1.7.0 to 1.8.1
                                            "looking for games with FSR 3.1 ..."])             # 1.9.0
def test_setup_worker_gives_the_script_no_input(qapp, tmp_path, installer_line):
    release, _ = prepared(tmp_path, INSTALLER_SCRIPT.replace("{installer_line}", installer_line))
    with mock.patch.object(acquire, "is_immutable_system", return_value=True):
        outcome, log = run_worker(qapp, SetupRequest(release, tmp_path / "work", tmp_path / "data" / "HelixSR"))
    assert outcome.ok, outcome.message
    assert (outcome.release_dir / "stdin.txt").read_text() == "no input\n"
    assert not any("GodOfWar" in line for line in log)                                     # the questions are hidden
    assert any("game installer is skipped" in line for line in log)
    assert "[fake-setup] args: --yes --dlss " + str(tmp_path / "work" / "nvngx_dlss.dll") in log    # the build is shown
    assert not any((outcome.release_dir / name).exists() for name in acquire.UNUSED_OUTPUT)
    assert (outcome.release_dir / backend.WEIGHTS).is_file()


@pytest.mark.parametrize("version, no_fg", [("1.2.0", False), ("1.8.1", False), ("1.9.0", True), ("1.9.3", True)])
def test_setup_worker_skips_frame_generation_from_1_9(qapp, tmp_path, version, no_fg):
    release, _ = prepared(tmp_path)
    with mock.patch.object(acquire, "is_immutable_system", return_value=True):
        outcome, _ = run_worker(qapp, SetupRequest(replace(release, version=version), tmp_path / "work",
                                                   tmp_path / "data" / "HelixSR"))
    assert outcome.ok, outcome.message
    assert ("--no-fg" in (outcome.release_dir / "args.txt").read_text()) == no_fg


def test_setup_worker_fallback_looks_up_the_pinned_tag(qapp, tmp_path):
    assert acquire.FALLBACK_TAG == "v1.8.1"
    with mock.patch.object(acquire, "latest_release", return_value=ReleaseInfo(error="GitHub answered 404")) as lookup:
        outcome, _ = run_worker(qapp, SetupRequest(None, tmp_path / "work", tmp_path / "data", fallback=True))
    assert lookup.call_args.args[0] == "https://api.github.com/repos/lonewolf0622/HelixSR/releases/tags/v1.8.1"
    assert not outcome.ok and "1.8.1" in outcome.message and "404" in outcome.message


# HelixSR 1.8's setup appends the network to its DLL and leaves no separate network files.
ONE_FILE_SCRIPT = """
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
printf 'weightskernels' >> "$HERE/amd_fidelityfx_dx12.dll"
printf 'HXSRNET1' >> "$HERE/amd_fidelityfx_dx12.dll"
printf '\\x07\\0\\0\\0\\0\\0\\0\\0\\x07\\0\\0\\0\\0\\0\\0\\0\\x01\\0\\0\\0\\0\\0\\0\\0' >> "$HERE/amd_fidelityfx_dx12.dll"
"""


def test_setup_worker_accepts_a_one_file_dll(qapp, tmp_path):
    release, _ = prepared(tmp_path, ONE_FILE_SCRIPT)
    with mock.patch.object(acquire, "is_immutable_system", return_value=True):
        outcome, log = run_worker(qapp, SetupRequest(release, tmp_path / "work", tmp_path / "data" / "HelixSR"))
    assert outcome.ok, outcome.message
    rd = outcome.release_dir
    assert backend.network_embedded(rd / backend.HELIXSR_DLL) and not (rd / backend.WEIGHTS).exists()
    assert backend.import_payload(rd, tmp_path / "payload").missing == []
    assert backend.payload_status(tmp_path / "payload").ready



# HelixSR 2's package: the DLL in HelixSR-fsrfg/, a setup script that ends with its game installer (here it leaves a
# mark when it runs at all), and the builder, which appends the network to the DLL, writes fsr3-drop-in/ and answers
# --status as the real one does.
SCRIPT_2X = """
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo ran > "$HERE/setup-script-ran.txt"
"""
BUILDER_2X = """
import sys
from pathlib import Path
a = sys.argv[1:]
out = Path(a[0])
dll = out / 'amd_fidelityfx_dx12.dll'
footer = b'HXSRNET1' + (7).to_bytes(8, 'little') * 2 + (1).to_bytes(8, 'little')
if '--status' in a:
    print('network=%d fg=0' % dll.read_bytes().endswith(footer))
    sys.exit(0)
(out.parent / 'args.txt').write_text(' '.join(a))
print('[helixsr-setup] building the network ({0})'.format(BUILD))
if BUILD != 'fail':
    if BUILD == 'ok':
        with dll.open('ab') as f:
            f.write(b'weightskernels' + footer)
    (out.parent / 'fsr3-drop-in').mkdir()
sys.exit(4 if BUILD == 'fail' else 0)
"""


def prepared_2x(tmp_path, build="ok"):
    """A HelixSR 2.0.0 release zip with the fake script and builder, and the same pinned downloads as prepared()."""
    release, dlss = prepared(tmp_path)
    one_x = Path(release.asset_url[len("file://"):])
    buf = io.BytesIO()
    with zipfile.ZipFile(one_x) as old, zipfile.ZipFile(buf, "w") as zf:
        setup_sh = old.read("HelixSR-1.2.0/helixsr-setup.sh").decode().split(GOOD_SCRIPT)[0] + SCRIPT_2X
        pins_py = old.read("HelixSR-1.2.0/setup/helixsr_setup.py").decode()
        zf.writestr("HelixSR-2.0.0/helixsr-setup.sh", setup_sh)
        zf.writestr("HelixSR-2.0.0/setup/helixsr_setup.py", pins_py + f"BUILD = {build!r}\n" + BUILDER_2X)
        zf.writestr("HelixSR-2.0.0/HelixSR-fsrfg/amd_fidelityfx_dx12.dll", FAKE_DLL)
        zf.writestr("HelixSR-2.0.0/HelixSR-fsrfg/helixsr.ini", backend.DEFAULT_INI_TEXT)
        zf.writestr("HelixSR-2.0.0/helixsr-scaler/README.txt", "HelixSR Scaler\n")
        zf.writestr("HelixSR-2.0.0/README.md", "# HelixSR 2.0.0\n")
    archive = tmp_path / "srv" / "HelixSR-2.0.0.zip"
    archive.write_bytes(buf.getvalue())
    return ReleaseInfo("2.0.0", "v2.0.0", "u", "2026-10-19", archive.name, archive.as_uri(), len(buf.getvalue())), dlss


def run_2x(qapp, tmp_path, build="ok", wine="/opt/wine/bin/wine"):
    release, _ = prepared_2x(tmp_path, build)
    request = SetupRequest(release, tmp_path / "work", tmp_path / "data" / "HelixSR")
    with mock.patch.object(acquire, "is_immutable_system", return_value=True), \
            mock.patch.object(acquire, "find_wine", return_value=wine), \
            mock.patch.object(SetupWorker, "_python", return_value=sys.executable):
        return run_worker(qapp, request)


def test_setup_worker_builds_2x_without_its_game_installer(qapp, tmp_path):
    """HelixSR 2's setup script installs into every game with --yes: the app runs its builder instead, on
    HelixSR-fsrfg, without frame generation, and takes the DLL from there (owner, 20-10-2026)."""
    (tmp_path / "data" / "HelixSR" / "wineprefix").mkdir(parents=True)
    outcome, log = run_2x(qapp, tmp_path)
    assert outcome.ok, outcome.message
    rd = outcome.release_dir
    assert not (rd / "setup-script-ran.txt").exists()                  # never its setup script, so never its games
    args = (rd / "args.txt").read_text().split()
    assert args[0] == str(rd / backend.FSRFG) and args[args.index("--dxc") + 1] == str(tmp_path / "work" /
                                                                                        acquire.DXC_WRAPPER)
    assert {"--yes", "--no-fg"} <= set(args) and args[args.index("--dlss") + 1] == str(tmp_path / "work" /
                                                                                       "nvngx_dlss.dll")
    assert not (tmp_path / "work" / "nvngx_dlss.dll").exists()        # NVIDIA's DLL is deleted afterwards
    assert not (rd / "fsr3-drop-in").exists() and not (tmp_path / "data" / "HelixSR" / "wineprefix").exists()
    assert any("building the network" in line for line in log) and "HelixSR-fsrfg: network=1 fg=0" in log
    assert backend.payload_folder(rd) == rd / backend.FSRFG
    result = backend.import_payload(rd, tmp_path / "payload")
    assert result.missing == [] and backend.payload_status(tmp_path / "payload").ready
    assert (tmp_path / "payload" / backend.HELIXSR_DLL).read_bytes() == (rd / backend.FSRFG / backend.HELIXSR_DLL
                                                                         ).read_bytes()
    assert acquire.latest_work_release(tmp_path / "work") == rd


@pytest.mark.parametrize("build, wine, says", [("fail", "/opt/wine/bin/wine", "exited with code 4"),
                                               ("no-network", "/opt/wine/bin/wine", "does not carry the network"),
                                               ("ok", "", "No Proton or Wine found")])
def test_setup_worker_2x_failures(qapp, tmp_path, build, wine, says):
    outcome, _ = run_2x(qapp, tmp_path, build, wine)
    assert not outcome.ok and says in outcome.message
    assert not (tmp_path / "work" / "nvngx_dlss.dll").exists()


def test_the_dxc_wrapper_runs_the_compiler_through_wine(tmp_path):
    """Absolute Linux paths become Z:\\ paths; Wine runs in its own prefix; a Proton folder may have spaces."""
    wine = tmp_path / "Proton - Experimental" / "wine"
    wine.parent.mkdir()
    wine.write_text('#!/usr/bin/env bash\necho "$WINEPREFIX|$WINEDEBUG"\nprintf "%s\\n" "$@"\n')
    wine.chmod(0o755)
    wrapper = acquire.write_dxc_wrapper(tmp_path / "work" / "dxc-wine.sh", str(wine), tmp_path / "data")
    out = subprocess.run([str(wrapper), "-T", "cs_6_6", "/tmp/a b/k4.hlsl", "-Fo", "/out/k4.cso"],
                         capture_output=True, text=True, check=True).stdout.splitlines()
    assert out == [f"{tmp_path / 'data' / 'wineprefix'}|-all", str(tmp_path / "data" / "dxc-win" / "bin" / "x64" /
                                                                    "dxc.exe"),
                   "-T", "cs_6_6", "Z:\\tmp\\a b\\k4.hlsl", "-Fo", "Z:\\out\\k4.cso"]


def test_find_wine_takes_proton_first(tmp_path, monkeypatch):
    monkeypatch.setattr(acquire.shutil, "which", lambda name: "/usr/bin/wine" if name == "wine" else None)
    assert acquire.find_wine(tmp_path) == "/usr/bin/wine"
    for folder in (".local/share/Steam/compatibilitytools.d/GE-Proton10-1", ".steam/steam/steamapps/common/Proton 9.0",
                   ".steam/steam/steamapps/common/Proton - Experimental"):
        wine = tmp_path / folder / "files" / "bin" / "wine"
        wine.parent.mkdir(parents=True)
        wine.write_text("#!/bin/sh\n")
        wine.chmod(0o755)
    assert acquire.find_wine(tmp_path) == str(tmp_path / ".steam/steam/steamapps/common/Proton - Experimental/files/"
                                                         "bin/wine")


def test_the_builders_python(qapp, tmp_path, monkeypatch):
    """As HelixSR's script: the portable Python with numpy, else the system's with numpy, else numpy by pip into
    the portable one."""
    data = tmp_path / "data"
    portable = str(data / "python" / "bin" / "python3")
    worker = SetupWorker(SetupRequest(None, tmp_path / "work", data))
    monkeypatch.setattr(acquire.shutil, "which", lambda name: "/usr/bin/python3")
    numpy = {"/usr/bin/python3"}
    monkeypatch.setattr(acquire, "python_has_numpy", lambda python: python in numpy)
    assert worker._python() == "/usr/bin/python3"                      # no portable Python
    make_python_tgz(tmp_path / "p.tgz")
    unpack_python(tmp_path / "p.tgz", data)
    numpy.add(portable)
    assert worker._python() == portable
    numpy.clear()
    pip = []
    monkeypatch.setattr(worker, "_stream", lambda command, *a, **k: pip.append(command) or numpy.add(portable) or 0)
    assert worker._python() == portable and pip[0][:4] == [portable, "-m", "pip", "install"]
    numpy.clear()
    monkeypatch.setattr(worker, "_stream", lambda *a, **k: 1)
    with pytest.raises(acquire.HelixError, match="numpy could not be installed"):
        worker._python()
