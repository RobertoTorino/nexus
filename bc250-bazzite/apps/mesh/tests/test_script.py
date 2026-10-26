# SPDX-License-Identifier: GPL-3.0-or-later
"""bc250-mesh-shaders.sh against a fake board: status, build, install, the test and its gate, remove, and the
per-game wrapper."""

from __future__ import annotations

import subprocess

from conftest import APP, BUILT, KERNEL, PREFIX, SUITE_PATCH, needs_bash

pytestmark = needs_bash

ICD = f"/{PREFIX}/share/vulkan/icd.d/radeon_icd.x86_64.json"
PATCH_SHA256 = "6669d4644d9a00ad8da022dd2716c59e4d235a2c6f0eb4f272c9c8d9fbcc9b77"


def test_status_of_a_fresh_board(board):
    assert board.status() == {
        "Board": "BC-250 (1002:13fe)",
        "Kernel": KERNEL,
        "System Mesa": "26.2.4",
        "DirectMesh": f"v1.3.1, Mesa 26.2.1, suite patch {SUITE_PATCH}",
        "Build": "none",
        "Driver": "not installed",
        "Test": "none",
        "Launch options": "/usr/local/bin/bc250-mesh-shaders-run %command%",
    }


def test_status_knows_both_board_ids(board):
    device = board.root / "sys/bus/pci/devices/0000:01:00.0/device"
    device.write_text("0x143f\n")
    assert board.status()["Board"] == "BC-250 (1002:143f)"
    device.write_text("0x73bf\n")
    assert board.status()["Board"] == "no BC-250 found (1002:13fe or 1002:143f)"


def test_build_downloads_the_pinned_mesa_and_runs_the_container(board):
    r = board.run("--build")
    assert r.returncode == 0, r.stdout + r.stderr
    src = board.home / ".cache/bc250-mesh-shaders/src"
    assert (src / "mesa-26.2.1.tar.xz").read_text().strip() == "https://archive.mesa3d.org/mesa-26.2.1.tar.xz"
    assert (src / "mesa-26.2.1.tar.xz.sig").is_file()
    podman = (board.home / "podman.log").read_text()
    assert "MESA_VER=26.2.1" in podman and f"PREFIX=/{PREFIX}" in podman
    assert "DIRECTMESH=v1.3.1" in podman and f"PATCH_SHA256={PATCH_SHA256}" in podman
    assert f"{APP}:/app:ro" in podman and "bash /app/mesa/build-in-container.sh" in podman
    assert (board.home / ".cache/bc250-mesh-shaders/stage/built").is_dir()     # the work stage moved into place


def test_build_drops_older_sources(board):
    src = board.home / ".cache/bc250-mesh-shaders/src"
    src.mkdir(parents=True)
    (src / "mesa-26.1.4.tar.xz").write_text("old")
    assert board.run("--build").returncode == 0
    assert sorted(p.name for p in src.iterdir()) == ["mesa-26.2.1.tar.xz", "mesa-26.2.1.tar.xz.sig"]


def test_build_failure_keeps_the_previous_build(board):
    board.make_build()
    board.env["FAKE_PODMAN_RC"] = "1"
    r = board.run("--build")
    assert r.returncode == 1 and "The build failed" in r.stderr
    assert (board.stage / "BUILD-INFO").is_file()


def test_build_refuses_root(board):
    assert "your own user" in board.run("--build", uid=0).stderr


def test_install_copies_the_build_and_links_drirc(board):
    board.make_build()
    board.install()
    assert (board.driver / "lib64/libvulkan_radeon.so").read_bytes() == b"radv"
    assert (board.driver / "libexec/bc250-mesh-test").is_file()
    assert (board.driver / "share/drirc.d").readlink().as_posix() == "/usr/share/drirc.d"
    assert (board.driver / "etc/drirc").readlink().as_posix() == "/etc/drirc"
    assert (board.root / "usr/local/bin/bc250-mesh-shaders-run").read_text() == \
        (APP / "bc250-mesh-shaders-run").read_text()
    s = board.status()
    assert s["Build"] == BUILT
    assert s["Driver"] == f"installed, {BUILT}"
    assert s["Test"] == "not run with this driver"


def test_install_needs_root_a_build_and_its_libraries(board):
    assert "Run as root" in board.run("--install-driver").stderr
    assert "build it first" in board.run("--install-driver", uid=0).stderr
    board.make_build()
    board.env["FAKE_LDD"] = "libdisplay-info.so.2 => not found"
    r = board.run("--install-driver", uid=0)
    assert r.returncode == 1 and "libdisplay-info.so.2" in r.stderr
    assert not board.driver.exists()


def test_install_refuses_an_incomplete_build_or_one_for_another_folder(board):
    board.make_build()
    (board.stage / "libexec/bc250-mesh-test").unlink()
    assert "bc250-mesh-test is missing" in board.run("--install-driver", uid=0).stderr
    board.make_build()
    (board.stage / "share/vulkan/icd.d/radeon_icd.x86_64.json").write_text('{"library_path": "/opt/x.so"}')
    assert "another folder" in board.run("--install-driver", uid=0).stderr


def test_passed_test_runs_on_the_driver_alone(board):
    board.make_build()
    board.install()
    board.pass_test()
    assert (board.home / "test-env").read_text().strip() == ICD              # only the DirectMesh driver
    assert "Device: fake --rounds 10" in (board.state / "test.log").read_text()
    assert board.status()["Test"].startswith("passed on this kernel (")
    board.env["FAKE_KERNEL"] = "7.2.9-ogc1.1.fc44.x86_64"
    assert board.status()["Test"] == f"passed on kernel {KERNEL}; test again on this one"


def test_rounds_go_to_the_test(board):
    board.make_build()
    board.install()
    assert board.run("--test", "--rounds", "3").returncode == 0
    assert "Device: fake --rounds 3" in (board.state / "test.log").read_text()


def test_failed_test_and_kernel_log_faults(board):
    board.make_build()
    board.install()
    board.env["FAKE_TEST_RC"] = "1"
    r = board.run("--test")
    assert r.returncode == 1 and "The test failed (exit code 1)" in r.stderr
    assert "FAIL: wrong pixels or data" in (board.state / "test.log").read_text()
    assert board.status()["Test"].startswith("failed (")
    board.env["FAKE_TEST_RC"] = "0"
    board.env["FAKE_TEST_FAULT"] = "1"                                      # passes, but the GPU reset meanwhile
    r = board.run("--test")
    assert r.returncode == 1 and "ring timeout or reset" in r.stdout
    assert not (board.state / "tested").exists()


def test_the_test_log_starts_afresh(board):
    board.make_build()
    board.install()
    board.pass_test()
    board.pass_test()
    assert (board.state / "test.log").read_text().count("Device: fake") == 1


def test_new_driver_needs_a_new_test(board):
    board.make_build()
    board.install()
    board.pass_test()
    board.make_build(built="2026-10-14 08:00 UTC", library=b"radv 2")
    board.install()
    assert board.status()["Test"] == "not run with this driver"


def test_remove_reverses_everything(board):
    board.make_build()
    board.install()
    board.pass_test()
    r = board.run("--remove-driver", uid=0)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not board.driver.exists()
    assert not (board.root / "usr/local/bin/bc250-mesh-shaders-run").exists()
    assert "launch options" in r.stdout
    assert board.status()["Driver"] == "not installed"
    assert "Run as root" in board.run("--remove-driver").stderr


def run_game(board, tmp_path, **switches: str) -> tuple[str, str]:
    """Runs the wrapper as Steam would; returns the VK_DRIVER_FILES the game got and the log line."""
    wrapper = tmp_path / "run"
    # The wrapper reads the real /usr/local; point it at the fake one.
    wrapper.write_text((APP / "bc250-mesh-shaders-run").read_text().replace(
        "PREFIX=/usr/local", f"PREFIX={board.root}/usr/local").replace(
        "/usr/share/vulkan", f"{board.root}/usr/share/vulkan"))
    game = subprocess.run(["bash", str(wrapper), "sh", "-c", 'echo "$VK_DRIVER_FILES"', "AppId=2215430"],
                          env={**board.env, **switches}, capture_output=True, text=True)
    log = (board.state / "run.log").read_text().splitlines()[-1]
    return game.stdout.strip(), log


def test_wrapper_uses_the_driver_only_after_a_passed_test(board, tmp_path):
    got, log = run_game(board, tmp_path)
    assert got == "" and log.endswith("AppId=2215430: system Mesa (the DirectMesh driver is not installed)")
    board.make_build()
    board.install()
    got, log = run_game(board, tmp_path)
    assert got == "" and log.endswith("AppId=2215430: system Mesa (the test has not passed on kernel "
                                      f"{KERNEL} with this driver)")
    board.pass_test()
    got, log = run_game(board, tmp_path)
    assert got == f"{board.root}/{PREFIX}/share/vulkan/icd.d/radeon_icd.x86_64.json:" \
                  f"{board.root}/usr/share/vulkan/icd.d/radeon_icd.i686.json"   # no lavapipe on this fake board
    assert log.endswith("AppId=2215430: DirectMesh RADV")
    board.env["FAKE_KERNEL"] = "7.2.9-ogc1.1.fc44.x86_64"
    got, _ = run_game(board, tmp_path)
    assert got == ""


def test_wrapper_logs_the_switches(board, tmp_path):
    board.make_build()
    board.install()
    board.pass_test()
    _, log = run_game(board, tmp_path, RADV_BC250_MESH_IDXPASS="0", RADV_DEBUG="nomeshshader")
    assert log.endswith("AppId=2215430: DirectMesh RADV, RADV_DEBUG=nomeshshader RADV_BC250_MESH_IDXPASS=0")


def test_launch_options_and_usage(board):
    assert board.run("--launch-options").stdout == "/usr/local/bin/bc250-mesh-shaders-run %command%\n"
    version = (APP / "VERSION").read_text().strip()
    assert board.run("--version").stdout.strip() == f"bc250-mesh-shaders {version} (DirectMesh v1.3.1, Mesa 26.2.1)"
    r = board.run("--rounds", "many")
    assert r.returncode == 1 and "takes a number" in r.stderr
    assert "Usage:" in board.run("--help").stdout
    assert board.run().returncode == 2
