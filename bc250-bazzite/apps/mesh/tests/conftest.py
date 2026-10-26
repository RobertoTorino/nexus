# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings in a temp folder, and a fake board for bc250-mesh-shaders.sh:
a folder that stands in for / (BC250_MESH_ROOT), a home folder with a finished build, and stub commands (id, uname,
rpm, journalctl, ldd, podman, curl) first on PATH. Nothing here touches /usr/local or the GPU."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it

APP = Path(__file__).resolve().parent.parent
SCRIPT = APP / "bc250-mesh-shaders.sh"
PREFIX = "usr/local/lib/bc250-mesh-shaders"
KERNEL = "7.2.8-ogc5.1.fc44.x86_64"
# The suite's patch as a build names it: the start of its SHA-256.
SUITE_PATCH = hashlib.sha256((APP / "mesa" / "bc250-suite-mesa-26.2.1.patch").read_bytes()).hexdigest()[:8]
BUILT = f"DirectMesh v1.3.1, Mesa 26.2.1, suite patch {SUITE_PATCH}, 2026-10-13 19:42 UTC"

needs_bash = pytest.mark.skipif(sys.platform == "win32", reason="runs the bash script with stub commands")

# The mesh test as the build makes it: prints the driver files it got and PASS, unless FAKE_TEST_RC asks for another
# exit code; FAKE_TEST_FAULT adds a ring timeout to the kernel log.
FAKE_TEST = '''#!/bin/sh
echo "Device: fake $*"
echo "$VK_DRIVER_FILES" > "$HOME/test-env"
rc=${FAKE_TEST_RC:-0}
if [ "$rc" = 0 ]; then echo PASS; else echo "FAIL: wrong pixels or data"; fi
[ -n "$FAKE_TEST_FAULT" ] && echo "amdgpu 0000:01:00.0: ring gfx_0.0.0 timeout" >> "$FAKE_KLOG_FILE"
exit "$rc"
'''


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path):
    """The app keeps an .ini (AppInfo.settings_ini), so this also keeps the tests out of the Windows registry."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    return tmp_path / "settings"


@dataclass
class Board:
    root: Path
    home: Path
    env: dict

    @property
    def driver(self) -> Path:
        return self.root / PREFIX

    @property
    def stage(self) -> Path:
        return self.home / ".cache/bc250-mesh-shaders/stage" / PREFIX

    @property
    def state(self) -> Path:
        return self.home / ".local/state/bc250-mesh-shaders"

    def run(self, *args: str, uid: int = 1000) -> subprocess.CompletedProcess:
        env = {**self.env, "FAKE_UID": str(uid)}
        return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL)

    def status(self) -> dict[str, str]:
        r = self.run("--status")
        assert r.returncode == 0, r.stdout + r.stderr
        return dict(line.split(": ", 1) for line in r.stdout.splitlines())

    def make_build(self, directmesh: str = "v1.3.1", built: str = "2026-10-13 19:42 UTC",
                   library: bytes = b"radv", suite_patch: str | None = SUITE_PATCH) -> None:
        """What a finished --build leaves in the cache (suite_patch None: a build from before the suite's patch)."""
        stage = self.stage
        for d in ("lib64", "share/vulkan/icd.d", "share/drirc.d", "libexec"):
            (stage / d).mkdir(parents=True, exist_ok=True)
        (stage / "lib64/libvulkan_radeon.so").write_bytes(library)
        (stage / "share/vulkan/icd.d/radeon_icd.x86_64.json").write_text(
            '{"ICD": {"library_path": "/usr/local/lib/bc250-mesh-shaders/lib64/libvulkan_radeon.so"}}\n')
        (stage / "share/drirc.d/00-radv-defaults.conf").write_text("<driconf/>\n")
        test = stage / "libexec/bc250-mesh-test"
        test.write_text(FAKE_TEST)
        test.chmod(0o755)
        suite = f"suite_patch={suite_patch}\n" if suite_patch else ""
        (stage / "BUILD-INFO").write_text(f"directmesh={directmesh}\nmesa=26.2.1\npatch=abc\n{suite}fedora=44\n"
                                          f"built={built}\n")

    def install(self) -> None:
        r = self.run("--install-driver", uid=0)
        assert r.returncode == 0, r.stdout + r.stderr

    def pass_test(self) -> None:
        r = self.run("--test")
        assert r.returncode == 0, r.stdout + r.stderr


def _stub(folder: Path, name: str, body: str) -> None:
    path = folder / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)


@pytest.fixture
def board(tmp_path) -> Board:
    """A BC-250 with the system Mesa 26.2.4 and nothing of this app installed yet."""
    root, home, stubs = tmp_path / "root", tmp_path / "home", tmp_path / "bin"
    for d in (root / "sys/bus/pci/devices/0000:01:00.0", root / "usr/share/vulkan/icd.d", root / "usr/share/drirc.d",
              root / "usr/local/bin", home, stubs):
        d.mkdir(parents=True, exist_ok=True)
    (root / "sys/bus/pci/devices/0000:01:00.0/vendor").write_text("0x1002\n")
    (root / "sys/bus/pci/devices/0000:01:00.0/device").write_text("0x13fe\n")
    (root / "usr/share/vulkan/icd.d/radeon_icd.i686.json").write_text("{}\n")
    klog = tmp_path / "klog"
    klog.write_text("amdgpu: initialised\n")
    _stub(stubs, "id", '[ "$1" = -u ] && { echo "$FAKE_UID"; exit 0; }; exec /usr/bin/id "$@"')
    _stub(stubs, "uname", '[ "$1" = -r ] && { echo "$FAKE_KERNEL"; exit 0; }; exec /usr/bin/uname "$@"')
    _stub(stubs, "rpm", 'echo "$FAKE_MESA"')
    _stub(stubs, "journalctl", 'cat "$FAKE_KLOG_FILE"')
    _stub(stubs, "ldd", 'printf "%s\\n" "$FAKE_LDD"')
    _stub(stubs, "podman", 'echo "$*" >> "$HOME/podman.log"; [ "${FAKE_PODMAN_RC:-0}" = 0 ] || exit "$FAKE_PODMAN_RC"\n'
          'case "$1" in run) mkdir -p "$HOME/.cache/bc250-mesh-shaders/work/stage/built" ;; esac')
    _stub(stubs, "curl", 'while [ $# -gt 1 ]; do [ "$1" = -o ] && out=$2; shift; done; echo "$1" > "$out"')
    env = {k: v for k, v in os.environ.items()
           if k not in ("PKEXEC_UID", "SUDO_UID", "SUDO_USER") and not k.startswith(("RADV_", "VK_"))}
    env.update({"PATH": f"{stubs}{os.pathsep}{env['PATH']}", "BC250_MESH_ROOT": str(root), "HOME": str(home),
                "FAKE_KERNEL": KERNEL, "FAKE_MESA": "26.2.4", "FAKE_LDD": "libdrm.so.2 => /usr/lib64/libdrm.so.2",
                "FAKE_KLOG_FILE": str(klog)})
    return Board(root, home, env)
