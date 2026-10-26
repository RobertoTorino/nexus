# SPDX-License-Identifier: GPL-3.0-or-later
"""The root helper: install (the files, the unit, the rule, the service started), uninstall, the service's load
(building for a new kernel, insmod with the firmware path, the eject of a stick in storage mode, the state file),
unload, and the pkexec command line and answer. The commands are recorded, never run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import KERNEL, fake_build, fake_source, set_stick, write

from usb_wifidriver import driver


class Runner:
    """Records the commands; "make ... modules" leaves the modules behind as the kernel's build system would."""

    def __init__(self, fail: str = ""):
        self.calls: list[list[str]] = []
        self.fail = fail

    def __call__(self, argv: list[str], timeout: float = 30, cwd: Path | None = None) -> driver.Result:
        self.calls.append(argv)
        if self.fail and self.fail in " ".join(argv):
            return driver.Result(1, f"{argv[0]} failed on purpose")
        if argv[0] == "make" and argv[-1] == "modules":
            module_dir = Path(argv[3][2:])
            for module in driver.MODULES:
                target = module_dir / module / f"{module}.ko"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"\x7fELF " + module.encode())
            return driver.Result(0, "  CC [M]  aic_load_fw/aicwf_usb.o\n  LD [M]  aic_load_fw/aic_load_fw.ko\n")
        return driver.Result(0, "")

    def names(self) -> list[str]:
        return [" ".join(c[:2]) for c in self.calls]


@pytest.fixture
def user_build(tmp_path):
    """What the app built: the output for the running kernel and its checkout."""
    build = tmp_path / "home/build/legacy-mcu1" / KERNEL
    source = tmp_path / "home/src/legacy-mcu1"
    fake_build(build)
    fake_source(source)
    return build, source


def installed(paths, run, user_build, own: Path) -> None:
    build, source = user_build
    driver.install(paths, "legacy-mcu1", build, source, KERNEL, commit="1d1b8fff", app_version="0.1.0", run=run,
                   own=own)


def test_install_puts_everything_in_place(paths, user_build, tmp_path):
    own = tmp_path / "driver.py"
    own.write_text("# this version\n")
    run = Runner()
    installed(paths, run, user_build, own)
    assert paths.script.read_text() == "# this version\n"
    assert json.loads(paths.config.read_text()) == {"branch": "legacy-mcu1", "commit": "1d1b8fff",
                                                     "app_version": "0.1.0"}
    unit = paths.unit.read_text()
    assert "ExecStart=/usr/bin/python3 -I /etc/bc250-usb-wifi/driver.py load" in unit
    assert "ExecStop=/usr/bin/python3 -I /etc/bc250-usb-wifi/driver.py unload" in unit
    assert "Type=simple\nRemainAfterExit=yes" in unit and "WantedBy=multi-user.target" in unit
    rules = paths.rules.read_text()
    assert 'ATTRS{idProduct}=="5723", RUN+="/usr/bin/eject /dev/%k"' in rules and rules.count("\n") == 6
    # The sources for the next kernel, without the build products, and this kernel's modules with the firmware.
    src = paths.source("legacy-mcu1")
    assert (src / "drivers/aic8800/Makefile").is_file() and (src / "fw/aic8800D80/fmacfw_8800d80_u02.bin").is_file()
    assert not (src / "drivers/aic8800/aic_load_fw/aicwf_usb.o").exists()
    modules = paths.modules(KERNEL)
    assert driver.complete(modules) and (modules / "fw/aic8800D80/aic8800D80/fmacfw_8800d80_u02.bin").is_file()
    assert (modules / "build.log").read_text() == "built\n"
    assert driver.built_kernels(paths) == (KERNEL,)
    assert driver.installed(paths) == driver.Config("legacy-mcu1", "1d1b8fff", "0.1.0")
    assert not driver.outdated(paths, own)
    assert run.names()[-4:] == ["systemctl daemon-reload", "udevadm control", "systemctl enable", "systemctl restart"]
    assert run.calls[-2] == ["systemctl", "enable", "bc250-usb-wifi.service"]


def test_install_replaces_the_other_branch_and_old_kernels(paths, user_build, tmp_path):
    own = tmp_path / "driver.py"
    own.write_text("# v\n")
    run = Runner()
    fake_build(paths.modules("7.1.0-ogc1.fc44.x86_64"))
    fake_source(paths.source("main"))
    installed(paths, run, user_build, own)
    assert not paths.source("main").exists() and not paths.modules("7.1.0-ogc1.fc44.x86_64").exists()
    assert driver.built_kernels(paths) == (KERNEL,)


def test_install_refuses_an_incomplete_build_or_source(paths, user_build, tmp_path):
    build, source = user_build
    (build / "aic8800_fdrv.ko").unlink()
    with pytest.raises(ValueError, match="no complete build"):
        driver.install(paths, "legacy-mcu1", build, source, KERNEL, run=Runner(), own=tmp_path / "x")
    fake_build(build)
    with pytest.raises(ValueError, match="no driver sources"):
        driver.install(paths, "legacy-mcu1", build, tmp_path / "empty", KERNEL, run=Runner(), own=tmp_path / "x")
    with pytest.raises(ValueError, match="Unknown driver branch"):
        driver.install(paths, "develop", build, source, KERNEL, run=Runner(), own=tmp_path / "x")
    assert driver.installed(paths) is None


def test_install_reports_a_service_that_does_not_start(paths, user_build, tmp_path):
    own = tmp_path / "driver.py"
    own.write_text("# v\n")
    with pytest.raises(ValueError, match="did not start"):
        installed(paths, Runner(fail="systemctl restart"), user_build, own)


def test_uninstall_removes_everything(paths, user_build, tmp_path):
    own = tmp_path / "driver.py"
    own.write_text("# v\n")
    run = Runner()
    installed(paths, run, user_build, own)
    write(paths.etc / "udev/rules.d/70-other.rules", "# someone else's")
    run.calls.clear()
    driver.uninstall(paths, run)
    for path in (paths.script, paths.config, paths.unit, paths.rules, paths.folder, paths.data):
        assert not path.exists()
    assert (paths.etc / "udev/rules.d/70-other.rules").is_file()
    assert run.calls[0] == ["systemctl", "disable", "--now", "bc250-usb-wifi.service"]
    assert run.names()[1:] == ["systemctl daemon-reload", "udevadm control"]
    assert driver.installed(paths) is None


def test_outdated_and_broken_config(paths, user_build, tmp_path):
    own = tmp_path / "driver.py"
    own.write_text("# v\n")
    installed(paths, Runner(), user_build, own)
    own.write_text("# a newer version\n")
    assert driver.outdated(paths, own)
    write(paths.config, '{"branch": "develop"}')
    assert driver.installed(paths) is None
    write(paths.config, "not json")
    assert driver.read_config(paths) is None


def notifications(target: list) -> callable:
    return lambda _run, title, body: target.append((title, body))


def test_load_with_the_modules_built(paths, user_build, tmp_path):
    own = tmp_path / "driver.py"
    own.write_text("# v\n")
    installed(paths, Runner(), user_build, own)
    write(paths.proc / "modules", "cfg80211 1691648 0 - Live 0x0000000000000000")
    run, notes = Runner(), []
    assert driver.load(paths, KERNEL, run, now=lambda: 1000.0, notify=notifications(notes)) == 0
    modules = paths.modules(KERNEL)
    assert run.calls == [["modprobe", "cfg80211"],
                         ["insmod", str(modules / "aic_load_fw.ko"), f"aic_fw_path={modules / 'fw'}"],
                         ["insmod", str(modules / "aic8800_fdrv.ko")]]
    state = driver.read_state(paths)
    assert state == {"time": 1000.0, "kernel": KERNEL, "built": False, "loaded": ["aic_load_fw", "aic8800_fdrv"],
                     "ejected": [], "error": "", "branch": "legacy-mcu1"}
    assert notes == []


def test_load_skips_loaded_modules_and_ejects_a_stick_in_storage_mode(paths, user_build, tmp_path, sys_root):
    own = tmp_path / "driver.py"
    own.write_text("# v\n")
    installed(paths, Runner(), user_build, own)
    set_stick(sys_root, "storage")
    run = Runner()
    assert driver.load(paths, KERNEL, run, now=lambda: 1.0, notify=notifications([])) == 0
    assert run.calls == [["modprobe", "cfg80211"], ["eject", str(paths.dev / "sda")]]
    assert driver.read_state(paths)["ejected"] == ["sda"]


def test_load_builds_for_a_new_kernel_and_says_so(paths, user_build, tmp_path):
    own = tmp_path / "driver.py"
    own.write_text("# v\n")
    installed(paths, Runner(), user_build, own)
    new = "7.3.1-ogc1.fc44.x86_64"
    write(paths.build_tree(new) / ".config", "CONFIG_CFG80211=m")
    write(paths.proc / "modules", "")
    run, notes = Runner(), []
    assert driver.load(paths, new, run, now=lambda: 5.0, notify=notifications(notes)) == 0
    module_dir = paths.source("legacy-mcu1") / "drivers/aic8800"
    assert run.calls[0] == ["make", "-C", str(paths.build_tree(new)), f"M={module_dir}", "clean"]
    assert run.calls[1][:4] == ["make", "-C", str(paths.build_tree(new)), f"M={module_dir}"]
    assert run.calls[1][-1] == "modules"
    modules = paths.modules(new)
    assert driver.complete(modules) and "LD [M]" in (modules / "build.log").read_text()
    assert run.calls[2:] == [["modprobe", "cfg80211"],
                             ["insmod", str(modules / "aic_load_fw.ko"), f"aic_fw_path={modules / 'fw'}"],
                             ["insmod", str(modules / "aic8800_fdrv.ko")]]
    assert driver.built_kernels(paths) == (KERNEL, new)
    assert driver.read_state(paths)["built"] is True
    assert notes == [("BC-250 USB Wi-Fi: the Wi-Fi driver was rebuilt for kernel " + new,
                      "The stick works as before. Plug it in again if it does not show up.")]


def test_load_reports_a_failed_build(paths, user_build, tmp_path, monkeypatch):
    own = tmp_path / "driver.py"
    own.write_text("# v\n")
    installed(paths, Runner(), user_build, own)
    new = "7.3.1-ogc1.fc44.x86_64"
    write(paths.build_tree(new) / ".config", "CONFIG_CFG80211=m")
    notes = []
    assert driver.load(paths, new, Runner(fail="modules"), now=lambda: 5.0, notify=notifications(notes)) == 1
    state = driver.read_state(paths)
    assert "failed (exit 1)" in state["error"] and state["loaded"] == []
    assert notes[0][0].endswith(f"could not be built for kernel {new}") and "Open BC-250 USB Wi-Fi" in notes[0][1]
    assert (paths.modules(new) / "build.log").read_text() == "make failed on purpose"
    # Without the kernel's build tree there is nothing to build with.
    assert "kernel-devel is missing" in driver.build(paths, "legacy-mcu1", "7.4.0-none", Runner())


def test_load_without_a_configuration_or_with_a_failing_insmod(paths, user_build, tmp_path):
    assert driver.load(paths, KERNEL, Runner(), now=lambda: 0.0, notify=notifications([])) == 1
    assert "missing or broken" in driver.read_state(paths)["error"]
    own = tmp_path / "driver.py"
    own.write_text("# v\n")
    installed(paths, Runner(), user_build, own)
    write(paths.proc / "modules", "")
    assert driver.load(paths, KERNEL, Runner(fail="insmod"), now=lambda: 0.0, notify=notifications([])) == 1
    assert driver.read_state(paths)["error"].startswith("insmod aic_load_fw failed")


def test_unload_in_reverse_order(paths):
    write(paths.proc / "modules", "aic8800_fdrv 1 0 - Live 0\naic_load_fw 1 1 aic8800_fdrv, Live 0")
    run = Runner()
    assert driver.unload(paths, run) == 0
    assert run.calls == [["rmmod", "aic8800_fdrv"], ["rmmod", "aic_load_fw"]]
    write(paths.proc / "modules", "")
    run = Runner()
    driver.unload(paths, run)
    assert run.calls == []


def test_command_and_answer(tmp_path):
    cmd = driver.command(["install", "--branch", "main"], own=tmp_path / "driver.py")
    assert cmd[0] == "pkexec" and cmd[2:] == ["-I", str(tmp_path / "driver.py"), "install", "--branch", "main"]
    assert driver.answer(0, '{"ok": true}\n') == ""
    assert driver.answer(1, '{"ok": false, "error": "No build"}\n') == "No build"
    assert driver.answer(126, "") == "Not authorized: the password dialog was canceled or refused."
    assert "exit code 3" in driver.answer(3, "boom")


def test_main_install_and_uninstall(paths, user_build, tmp_path, monkeypatch, capsys):
    """main() hands the module's run on by name, so this Runner takes the place of every real command."""
    monkeypatch.setenv("BC250_SYSTEM_ROOT", str(tmp_path))
    runner = Runner()
    monkeypatch.setattr(driver, "run", runner)
    monkeypatch.setattr(driver, "paths_from_env", lambda: paths)
    build, source = user_build
    assert driver.main(["install", "--branch", "legacy-mcu1", "--build", str(build), "--source", str(source),
                        "--kernel", KERNEL, "--commit", "abc", "--app-version", "0.1.0"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == {"ok": True}
    assert driver.installed(paths).commit == "abc"
    assert ["systemctl", "restart", "bc250-usb-wifi.service"] in runner.calls
    assert driver.main(["install", "--branch", "legacy-mcu1", "--build", str(tmp_path / "none"),
                        "--source", str(source), "--kernel", KERNEL]) == 1
    assert json.loads(capsys.readouterr().out.strip())["ok"] is False
    assert driver.main(["uninstall"]) == 0
    assert driver.installed(paths) is None


def test_notify_desktop_reaches_each_session(tmp_path):
    (tmp_path / "run/user/1000").mkdir(parents=True)
    (tmp_path / "run/user/1000/bus").write_text("")
    (tmp_path / "run/user/0").mkdir(parents=True)
    (tmp_path / "run/user/0/bus").write_text("")
    run = Runner()
    import pwd
    import shutil
    me = pwd.getpwuid(1000).pw_name if any(p.pw_uid == 1000 for p in pwd.getpwall()) else None
    if me is None or shutil.which("notify-send") is None:
        pytest.skip("no uid 1000 or no notify-send here")
    driver.notify_desktop(run, "title", "body", run_root=tmp_path / "run")
    assert len(run.calls) == 1 and run.calls[0][:3] == ["runuser", "-u", me] and run.calls[0][-2:] == ["title", "body"]
