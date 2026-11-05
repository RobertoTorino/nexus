# SPDX-License-Identifier: GPL-3.0-or-later
"""acquire.py with GitHub's recorded answer (tests/data/helixsr-releases.json, trimmed to what the app reads),
file:// URLs and a fake builder: no network, nothing of NVIDIA's, no real HelixSR run. The whole Get HelixSR run
downloads a fake release and the pinned files its helixsr-setup.ps1 names, checks every SHA-256, unpacks Python,
numpy and the shader compiler as the script does, and runs the release's builder with the arguments the app gives
it."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

from conftest import DATA
from upscale_boost import acquire, backend
from upscale_boost.acquire import (Pin, ReleaseInfo, Setup, SetupRequest, UpdateStatus, download, needed_pins,
                                   parse_pins, release_info, supported_release, unpack_dxc, unpack_numpy,
                                   unpack_python)
from upscale_boost.backend import HelixError

RECORDED = DATA / "helixsr-releases.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buffer.getvalue()


# GitHub's answer

def test_the_newest_2_x_release_and_the_3_x_this_app_does_not_take():
    best, newer = supported_release(RECORDED.as_uri(), "https://example.invalid/releases")
    assert best.version == "2.0.0" and best.asset_name == "HelixSR-2.0.0.zip"
    assert best.asset_sha256 == "0d60686eddbb0abd680b27d12a088344b212464ebf0a2dc18d10387e1c817f52"
    assert best.asset_size == 136997025 and best.published == "2026-10-19"
    assert newer == "3.1.0"                             # 3.2.0 is a pre-release: never offered


def test_the_fallback_release_is_read_by_its_tag():
    releases = json.loads(RECORDED.read_text(encoding="utf-8"))
    fallback = release_info(next(r for r in releases if r["tag_name"] == acquire.FALLBACK_TAG), "")
    assert fallback.version == acquire.FALLBACK_VERSION and fallback.asset_name == "HelixSR-1.8.1.zip"
    assert len(fallback.asset_sha256) == 64


def test_a_failed_lookup_says_why(tmp_path):
    best, newer = supported_release((tmp_path / "missing.json").as_uri(), "page")
    assert best.error.startswith("no connection") and newer == ""
    (tmp_path / "odd.json").write_text("{}", encoding="utf-8")
    assert supported_release((tmp_path / "odd.json").as_uri(), "page")[0].error == "unexpected answer from GitHub"


def test_the_update_status_texts():
    latest = ReleaseInfo("2.0.0", "v2.0.0", "", "2026-10-19")
    assert UpdateStatus("HelixSR", "1.9.3", latest).summary == "1.9.3 → 2.0.0 available (2026-10-19)"
    assert UpdateStatus("HelixSR", "1.9.3", latest).update_available
    current = UpdateStatus("HelixSR", "2.0.0", latest, "3.1.0")
    assert not current.update_available and current.kind == "ok"
    assert current.summary.endswith("HelixSR 3.1.0 is out, this app does not support it yet")


# Downloads and the pinned files

def test_a_download_is_checked(tmp_path):
    source = tmp_path / "file.bin"
    source.write_bytes(b"payload")
    seen = []
    download(source.as_uri(), tmp_path / "out" / "file.bin", sha(b"payload"), lambda *a: seen.append(a))
    assert (tmp_path / "out" / "file.bin").read_bytes() == b"payload" and seen[-1] == ("file.bin", 7, 7)
    with pytest.raises(HelixError, match="checksum mismatch"):
        download(source.as_uri(), tmp_path / "bad.bin", sha(b"other"))
    assert not (tmp_path / "bad.bin").exists() and not (tmp_path / "bad.bin.part").exists()


PS1 = """$Downloads = @{{
    python = @{{ url = '{python}'
                sha = '{python_sha}' }}
    numpy  = @{{ url = '{numpy}'
                sha = '{numpy_sha}' }}
    dxc    = @{{ url = '{dxc}'
                sha = '{dxc_sha}' }}
}}
"""


def test_the_pins_are_read_as_helixsr_setup_ps1_writes_them(tmp_path):
    (tmp_path / "setup").mkdir()
    (tmp_path / acquire.SETUP_SCRIPT).write_text(PS1.format(
        python="https://www.python.org/ftp/python/3.14.8/python-3.14.8-embed-amd64.zip", python_sha="a" * 64,
        numpy="https://files.pythonhosted.org/x/numpy-2.5.3-cp314-cp314-win_amd64.whl", numpy_sha="b" * 64,
        dxc="https://github.com/microsoft/DirectXShaderCompiler/releases/download/v1.9.2607/dxc_2026_07_29.zip",
        dxc_sha="C" * 64), encoding="utf-8")
    (tmp_path / acquire.BUILDER).write_text(
        "DLSS_URL = 'https://raw.githubusercontent.com/NVIDIA/DLSS/v310.7.0/lib/Windows_x86_64/rel/nvngx_dlss.dll'\n"
        f"DLSS_SHA256 = '{'d' * 64}'\n", encoding="utf-8")
    pins = parse_pins(tmp_path)
    assert sorted(pins) == ["dlss", "dxc", "numpy", "python"]
    assert pins["python"].filename == "python-3.14.8-embed-amd64.zip" and pins["dxc"].sha256 == "c" * 64
    assert pins["dlss"].filename == "nvngx_dlss.dll"
    assert acquire.pinned_dlss_sha(tmp_path) == "d" * 64


def test_python_numpy_and_the_compiler_unpack_as_the_script_lays_them_out(tmp_path):
    data = tmp_path / "HelixSR"
    (tmp_path / "py.zip").write_bytes(zip_bytes({"python.exe": b"MZ", "python314._pth": b"python314.zip\n.\n"}))
    (tmp_path / "np.whl").write_bytes(zip_bytes({"numpy/__init__.py": b"", "numpy-2.5.3.dist-info/METADATA": b""}))
    (tmp_path / "dxc.zip").write_bytes(zip_bytes({"bin\\x64\\dxc.exe": b"MZ", "bin\\x64\\dxcompiler.dll": b"MZ",
                                                  "inc\\dxcapi.h": b"//"}))
    unpack_python(tmp_path / "py.zip", data)
    unpack_numpy(tmp_path / "np.whl", data)
    unpack_dxc(tmp_path / "dxc.zip", data)
    assert acquire.python_present(data) and acquire.numpy_present(data) and acquire.dxc_present(data)
    assert (data / "dxc" / "dxcompiler.dll").is_file() and not (data / "dxc" / "inc").exists()
    (tmp_path / "evil.zip").write_bytes(zip_bytes({"../evil.txt": b"x"}))
    with pytest.raises(HelixError, match="unsafe path"):
        unpack_python(tmp_path / "evil.zip", data)


def test_needed_pins_leave_out_what_is_here(tmp_path):
    pins = {key: Pin(key, f"https://x/{key}", "0" * 64, key) for key in ("dlss", "python", "numpy", "dxc")}
    data = tmp_path / "HelixSR"
    assert [p.key for p in needed_pins(pins, data, None)] == ["dlss", "python", "numpy", "dxc"]
    (data / "python" / "numpy").mkdir(parents=True)
    (data / "python" / "python.exe").write_bytes(b"MZ")
    (data / "dxc").mkdir()
    (data / "dxc" / "dxc.exe").write_bytes(b"MZ")
    assert needed_pins(pins, data, tmp_path / "nvngx_dlss.dll") == []


def test_find_dlss_takes_only_the_pinned_build(tmp_path):
    common = tmp_path / "steamapps" / "common"
    (common / "A" / "bin").mkdir(parents=True)
    (common / "B").mkdir(parents=True)
    (common / "A" / "bin" / "nvngx_dlss.dll").write_bytes(b"the pinned")
    (common / "B" / "nvngx_dlss.dll").write_bytes(b"another build")
    assert acquire.find_dlss_dlls([tmp_path / "steamapps"], sha(b"the pinned")) == [common / "A" / "bin" /
                                                                                   "nvngx_dlss.dll"]


# The whole run

BUILDER = r'''
import json, struct, sys
from pathlib import Path
DLSS_URL = '{dlss_url}'
DLSS_SHA256 = '{dlss_sha}'
args = sys.argv[1:]
out = Path(args[0])
dll = out / "amd_fidelityfx_dx12.dll"
if "--status" in args:
    built = dll.read_bytes()[-32:-24] == b"HXSRNET1"
    print("network=%d fg=0" % built)
    sys.exit(0)
(Path(__file__).resolve().parent.parent / "builder-args.json").write_text(json.dumps(args))
print("[helixsr-setup] building the network")
print("compiling 1 of 2\rcompiling 2 of 2")
if {fail}:
    sys.exit(2)
if {build}:
    dll.write_bytes(dll.read_bytes() + b"wk" + b"HXSRNET1" + struct.pack("<QQQ", 1, 1, 1))
'''


class Run:
    """A fake HelixSR release (2.x layout unless *version* is 1.x) on file:// URLs, with its pinned downloads."""

    def __init__(self, tmp_path: Path, version: str = "2.0.0", fail: bool = False, build: bool = True):
        self.tmp = tmp_path
        server = tmp_path / "server"
        server.mkdir(parents=True)
        files = {
            "python": ("python-3.14.8-embed-amd64.zip", zip_bytes({"python.exe": b"MZ", "python314._pth": b".\n"})),
            "numpy": ("numpy-2.5.3-cp314-cp314-win_amd64.whl", zip_bytes({"numpy/__init__.py": b""})),
            "dxc": ("dxc_2026_07_29.zip", zip_bytes({"bin\\x64\\dxc.exe": b"MZ"})),
            "dlss": ("nvngx_dlss.dll", b"MZ-fake-nvngx-dlss-310.7.0"),
        }
        urls = {}
        for key, (name, data) in files.items():
            (server / name).write_bytes(data)
            urls[key] = ((server / name).as_uri(), sha(data))
        two = version.startswith("2")
        out = f"HelixSR-{version}/{backend.FSRFG}/" if two else f"HelixSR-{version}/"
        members = {
            f"HelixSR-{version}/{acquire.SETUP_SCRIPT}": PS1.format(
                python=urls["python"][0], python_sha=urls["python"][1], numpy=urls["numpy"][0],
                numpy_sha=urls["numpy"][1], dxc=urls["dxc"][0], dxc_sha=urls["dxc"][1]).encode(),
            f"HelixSR-{version}/{acquire.BUILDER}": BUILDER.format(
                dlss_url=urls["dlss"][0], dlss_sha=urls["dlss"][1], fail=fail, build=build).encode(),
            f"HelixSR-{version}/README.md": (f"# HelixSR {version}\n" if two else f"**Version {version}.**").encode(),
            f"{out}{backend.HELIXSR_DLL}": f"MZ-HelixSR {version}".encode(),
            f"{out}{backend.INI}": b"[Log]\nEnabled = true\n",
        }
        data = zip_bytes(members)
        archive = server / f"HelixSR-{version}.zip"
        archive.write_bytes(data)
        self.release = ReleaseInfo(version, f"v{version}", "page", "2026-10-19", archive.name, archive.as_uri(),
                                   len(data), sha(data))
        self.lines: list[str] = []
        self.stages: list[str] = []

    def setup(self, **more) -> Setup:
        request = SetupRequest(self.tmp / "work", self.tmp / "HelixSR", self.release, python=sys.executable, **more)
        return Setup(request, self.lines.append, self.stages.append)

    def args(self) -> list[str]:
        return json.loads((self.tmp / "work" / f"HelixSR-{self.release.version}" / f"HelixSR-{self.release.version}"
                           / "builder-args.json").read_text())


def test_get_helixsr_2_downloads_checks_and_builds(tmp_path):
    run = Run(tmp_path)
    outcome = run.setup().run()
    assert outcome.ok, outcome.message
    assert outcome.version == "2.0.0" and outcome.release_dir.name == "HelixSR-2.0.0"
    data = tmp_path / "HelixSR"
    assert acquire.python_present(data) and acquire.numpy_present(data) and acquire.dxc_present(data)
    args = run.args()
    assert Path(args[0]).name == backend.FSRFG
    assert args[1:5] == ["--dxc", str(data / "dxc" / "dxc.exe"), "--yes", "--no-fg"]
    assert args[5] == "--dlss" and Path(args[6]).name == "nvngx_dlss.dll" and not Path(args[6]).exists()
    assert "compiling 2 of 2" in run.lines and "HelixSR-fsrfg: network=1 fg=0" in run.lines
    assert run.stages[0] == "Downloading HelixSR 2.0.0" and any("at the same time" in s for s in run.stages)
    payload = backend.payload_folder(outcome.release_dir)
    assert backend.payload_status(payload).ready
    result = backend.import_payload(outcome.release_dir, tmp_path / "payload")
    assert result.missing == [] and backend.payload_status(tmp_path / "payload").version == "2.0.0"


def test_a_second_run_reuses_the_download_and_the_prerequisites(tmp_path):
    run = Run(tmp_path)
    assert run.setup().run().ok
    run.lines.clear()
    assert run.setup().run().ok
    assert "Using the already downloaded HelixSR-2.0.0.zip" in run.lines
    assert not any(line.startswith(("Python:", "numpy:", "DirectX")) for line in run.lines)


def test_a_1_x_release_builds_in_its_own_folder_without_no_fg(tmp_path):
    run = Run(tmp_path, "1.8.1")
    outcome = run.setup().run()
    assert outcome.ok, outcome.message
    args = run.args()
    assert Path(args[0]).name == "HelixSR-1.8.1" and "--no-fg" not in args
    assert not any("network=" in line for line in run.lines)        # 1.x knows no --status


def test_a_local_dlss_dll_is_used_and_kept(tmp_path):
    local = tmp_path / "game" / "nvngx_dlss.dll"
    local.parent.mkdir()
    local.write_bytes(b"MZ local dlss")
    run = Run(tmp_path)
    assert run.setup(dlss_file=local).run().ok
    assert run.args()[-2:] == ["--dlss", str(local)] and local.is_file()
    assert not any(line.startswith("NVIDIA DLSS DLL:") for line in run.lines)


def test_a_failing_build_and_a_build_without_the_network(tmp_path):
    outcome = Run(tmp_path / "a", fail=True).setup().run()
    assert not outcome.ok and "exited with code 2" in outcome.message
    outcome = Run(tmp_path / "b", build=False).setup().run()
    assert not outcome.ok and "does not carry the network (network=0 fg=0)" in outcome.message


def test_a_damaged_download_and_an_unsupported_major(tmp_path):
    run = Run(tmp_path)
    run.release.asset_sha256 = "0" * 64
    outcome = run.setup().run()
    assert not outcome.ok and "checksum mismatch" in outcome.message
    run.release.version = "3.1.0"
    outcome = run.setup().run()
    assert not outcome.ok and "not supported yet" in outcome.message


def test_cancel_stops_it(tmp_path):
    setup = Run(tmp_path).setup()
    setup.cancel()
    outcome = setup.run()
    assert not outcome.ok and outcome.message == "Canceled."


def test_the_newest_built_release_in_the_work_folder(tmp_path):
    for version in ("1.8.1", "2.0.0"):
        folder = tmp_path / f"HelixSR-{version}" / f"HelixSR-{version}"
        folder.mkdir(parents=True)
        (folder / acquire.SETUP_SCRIPT).write_text("#", encoding="utf-8")
    assert acquire.latest_work_release(tmp_path).name == "HelixSR-2.0.0"
    assert acquire.latest_work_release(tmp_path / "none") is None
