# SPDX-License-Identifier: GPL-3.0-or-later
"""bc250-ace-queues.sh against a fake board: status, build, install, the test and its gate, all apps on and off with
the boot check, remove, and the per-game wrapper."""

from __future__ import annotations

import subprocess

from conftest import APP, KERNEL, PREFIX, needs_bash

pytestmark = needs_bash

ICD = f"/{PREFIX}/share/vulkan/icd.d/radeon_icd.x86_64.json"


def test_status_of_a_fresh_board(board):
    assert board.status() == {
        "Board": "BC-250 (1002:13fe)",
        "Kernel": KERNEL,
        "System Mesa": "26.2.4",
        "Build": "none",
        "Driver": "not installed",
        "Test": "none",
        "All apps": "off",
        "Launch options": "/usr/local/bin/bc250-ace-queues-run %command%",
    }


def test_status_without_a_bc250(board):
    (board.root / "sys/bus/pci/devices/0000:01:00.0/device").write_text("0x73bf\n")
    assert board.status()["Board"] == "no BC-250 found (1002:13fe)"


def test_build_downloads_the_system_mesa_and_runs_the_container(board):
    r = board.run("--build")
    assert r.returncode == 0, r.stdout + r.stderr
    src = board.home / ".cache/bc250-ace-queues/src"
    assert (src / "mesa-26.2.4.tar.xz").read_text().strip() == "https://archive.mesa3d.org/mesa-26.2.4.tar.xz"
    assert (src / "mesa-26.2.4.tar.xz.sig").is_file()
    podman = (board.home / "podman.log").read_text()
    assert "MESA_VER=26.2.4" in podman and f"PREFIX=/{PREFIX}" in podman
    assert f"{APP}:/app:ro" in podman and "bash /app/mesa/build-in-container.sh" in podman
    assert (board.home / ".cache/bc250-ace-queues/stage/built").is_dir()       # the work stage moved into place


def test_build_with_another_mesa_drops_older_sources(board):
    src = board.home / ".cache/bc250-ace-queues/src"
    src.mkdir(parents=True)
    (src / "mesa-26.2.3.tar.xz").write_text("old")
    assert board.run("--build", "--mesa", "26.2.5").returncode == 0
    assert sorted(p.name for p in src.iterdir()) == ["mesa-26.2.5.tar.xz", "mesa-26.2.5.tar.xz.sig"]


def test_build_failure_keeps_the_previous_build(board):
    board.make_build()
    board.env["FAKE_PODMAN_RC"] = "1"
    r = board.run("--build")
    assert r.returncode == 1 and "The build failed" in r.stderr
    assert (board.stage / "BUILD-INFO").is_file()


def test_build_refuses_root_and_an_unknown_mesa(board):
    assert "your own user" in board.run("--build", uid=0).stderr
    board.env["FAKE_MESA"] = ""
    r = board.run("--build")
    assert r.returncode == 1 and "--mesa X.Y.Z" in r.stderr


def test_install_copies_the_build_and_links_drirc(board):
    board.make_build()
    board.install()
    assert (board.driver / "lib64/libvulkan_radeon.so").read_bytes() == b"radv"
    assert (board.driver / "share/drirc.d").readlink().as_posix() == "/usr/share/drirc.d"
    assert (board.driver / "etc/drirc").readlink().as_posix() == "/etc/drirc"
    assert (board.root / "usr/local/bin/bc250-ace-queues-run").read_text() == (APP / "bc250-ace-queues-run").read_text()
    s = board.status()
    assert s["Build"] == "Mesa 26.2.4, 2026-10-10 16:00 UTC"
    assert s["Driver"] == "installed, Mesa 26.2.4"
    assert s["Test"] == "not run with this driver"


def test_install_needs_root_a_build_and_its_libraries(board):
    assert "Run as root" in board.run("--install-driver").stderr
    assert "build it first" in board.run("--install-driver", uid=0).stderr
    board.make_build()
    board.env["FAKE_LDD"] = "libdisplay-info.so.2 => not found"
    r = board.run("--install-driver", uid=0)
    assert r.returncode == 1 and "libdisplay-info.so.2" in r.stderr
    assert not board.driver.exists()


def test_install_refuses_a_build_for_another_folder(board):
    board.make_build()
    (board.stage / "share/vulkan/icd.d/radeon_icd.x86_64.json").write_text('{"library_path": "/opt/x.so"}')
    assert "another folder" in board.run("--install-driver", uid=0).stderr


def test_passed_test_is_recorded_for_this_kernel_and_driver(board):
    board.make_build()
    board.install()
    board.pass_test()
    assert (board.home / "test-env").read_text().strip() == ICD             # only the patched driver
    assert "PASS" in (board.state / "test.log").read_text()
    assert board.status()["Test"].startswith("passed on this kernel (")
    board.env["FAKE_KERNEL"] = "7.2.9-ogc1.1.fc44.x86_64"
    assert board.status()["Test"] == f"passed on kernel {KERNEL}; test again on this one"


def test_failed_test_and_kernel_log_faults(board):
    board.make_build()
    board.install()
    board.env["FAKE_TEST_RC"] = "1"
    r = board.run("--test")
    assert r.returncode == 1 and "The test failed (exit code 1)" in r.stderr
    assert board.status()["Test"].startswith("failed (")
    board.env["FAKE_TEST_RC"] = "0"
    board.env["FAKE_TEST_FAULT"] = "1"                                       # passes, but the GPU reset meanwhile
    r = board.run("--test")
    assert r.returncode == 1 and "ring timeout or reset" in r.stdout
    assert not (board.state / "tested").exists()


def test_new_driver_needs_a_new_test(board):
    board.make_build()
    board.install()
    board.pass_test()
    board.make_build(library=b"radv 2")
    board.install()
    assert board.status()["Test"] == "not run with this driver"


def test_all_apps_needs_a_passed_test(board):
    board.make_build()
    board.install()
    r = board.run("--all-apps", "on", uid=0)
    assert r.returncode == 1 and "has not passed" in r.stderr
    assert not board.env_conf.exists()


def test_all_apps_on_and_off(board):
    board.make_build()
    board.install()
    board.pass_test()
    r = board.run("--all-apps", "on", uid=0)
    assert r.returncode == 0, r.stdout + r.stderr
    files = f"{ICD}:/usr/share/vulkan/icd.d/radeon_icd.i686.json"            # no lavapipe on this fake board
    assert f"VK_DRIVER_FILES={files}" in board.env_conf.read_text().splitlines()
    profile = board.root / "etc/profile.d/90-bc250-ace-queues.sh"
    assert f"export VK_DRIVER_FILES={files}" in profile.read_text().splitlines()
    assert f"ExecStart=/usr/bin/bash /{PREFIX}/boot-check" in board.unit.read_text()
    assert board.status()["All apps"] == "on"

    r = board.run("--all-apps", "off", uid=0)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not board.env_conf.exists() and not profile.exists() and not board.unit.exists()
    assert not (board.driver / "boot-check").exists()
    assert board.status()["All apps"] == "off"


def boot(board) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(board.driver / "boot-check")], env=board.env, capture_output=True, text=True)


def test_boot_check_keeps_all_apps_on_the_tested_kernel(board):
    board.make_build()
    board.install()
    board.pass_test()
    assert board.run("--all-apps", "on", uid=0).returncode == 0
    assert boot(board).returncode == 0
    assert board.env_conf.exists()


def test_boot_check_switches_all_apps_off_on_a_new_kernel(board):
    board.make_build()
    board.install()
    board.pass_test()
    assert board.run("--all-apps", "on", uid=0).returncode == 0
    board.env["FAKE_KERNEL"] = "7.2.9-ogc1.1.fc44.x86_64"
    r = boot(board)
    assert "all apps switched off: kernel 7.2.9-ogc1.1.fc44.x86_64, tested on" in r.stdout
    assert not board.env_conf.exists()
    assert board.status()["All apps"].startswith("off (switched off at boot: ")


def test_installing_a_new_driver_switches_all_apps_off(board):
    board.make_build()
    board.install()
    board.pass_test()
    assert board.run("--all-apps", "on", uid=0).returncode == 0
    board.make_build(library=b"radv 2")
    r = board.run("--install-driver", uid=0)
    assert r.returncode == 0 and "not been tested yet" in r.stdout
    assert not board.env_conf.exists()


def test_remove_reverses_everything(board):
    board.make_build()
    board.install()
    board.pass_test()
    assert board.run("--all-apps", "on", uid=0).returncode == 0
    r = board.run("--remove-driver", uid=0)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not board.driver.exists() and not board.env_conf.exists() and not board.unit.exists()
    assert not (board.root / "usr/local/bin/bc250-ace-queues-run").exists()
    assert "launch options" in r.stdout
    assert board.status()["Driver"] == "not installed"


def run_game(board, tmp_path) -> tuple[str, str]:
    """Runs the wrapper as Steam would; returns the VK_DRIVER_FILES the game got and the log line."""
    wrapper = tmp_path / "run"
    # The wrapper reads the real /usr/local; point it at the fake one.
    wrapper.write_text((APP / "bc250-ace-queues-run").read_text().replace(
        "PREFIX=/usr/local", f"PREFIX={board.root}/usr/local").replace(
        "/usr/share/vulkan", f"{board.root}/usr/share/vulkan"))
    game = subprocess.run(["bash", str(wrapper), "sh", "-c", 'echo "$VK_DRIVER_FILES"', "AppId=1091500"],
                          env=board.env, capture_output=True, text=True)
    log = (board.state / "run.log").read_text().splitlines()[-1]
    return game.stdout.strip(), log


def test_wrapper_uses_the_driver_only_after_a_passed_test(board, tmp_path):
    board.make_build()
    board.install()
    got, log = run_game(board, tmp_path)
    assert got == "" and log.endswith("AppId=1091500: system Mesa (the ACE queue test has not passed on kernel "
                                      f"{KERNEL} with this driver)")
    board.pass_test()
    got, log = run_game(board, tmp_path)
    assert got.startswith(f"{board.root}/{PREFIX}/share/vulkan/icd.d/radeon_icd.x86_64.json:")
    assert log.endswith("AppId=1091500: patched RADV")
    board.env["FAKE_KERNEL"] = "7.2.9-ogc1.1.fc44.x86_64"
    got, _ = run_game(board, tmp_path)
    assert got == ""


def test_launch_options_and_usage(board):
    assert board.run("--launch-options").stdout == "/usr/local/bin/bc250-ace-queues-run %command%\n"
    assert board.run("--version").stdout.strip() == f"bc250-ace-queues {(APP / 'VERSION').read_text().strip()}"
    r = board.run("--all-apps", "maybe")
    assert r.returncode == 1 and "on or off" in r.stderr
    assert board.run().returncode == 2
