# SPDX-License-Identifier: GPL-3.0-or-later
"""The window: the stick in its modes, the chip's answer and the branch it chooses, the notes, the buttons, the
build steps handed to the runner, and the helper calls behind Install, Update and Remove."""

from __future__ import annotations

import pytest
from conftest import KERNEL, LOG_FAILED, LOG_WORKED, fake_build, fake_source, set_stick, usb_device, write  # noqa: F401
from PyQt6.QtWidgets import QMessageBox

from usb_wifidriver import __version__, builder, driver
from usb_wifidriver.main_window import MainWindow, StepRunner


class Helper:
    """Stands in for pkexec driver.py: installs into the test's paths."""

    def __init__(self, paths, error: str = ""):
        self.paths, self.error, self.calls = paths, error, []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        if self.error:
            return self.error
        if args[0] == "install":
            values = dict(zip(args[1::2], args[2::2]))
            driver.install(self.paths, values["--branch"], driver.Path(values["--build"]),
                           driver.Path(values["--source"]), values["--kernel"], values["--commit"],
                           values["--app-version"], run=lambda *_a, **_k: driver.Result(0, ""),
                           own=driver.Path(driver.__file__))
            driver.write_state(self.paths, {"time": 1000.0, "kernel": values["--kernel"], "built": False,
                                            "loaded": ["aic_load_fw", "aic8800_fdrv"], "ejected": ["sda"],
                                            "error": "", "branch": values["--branch"]})
        else:
            driver.uninstall(self.paths, lambda *_a, **_k: driver.Result(0, ""))
        return ""


@pytest.fixture
def yes(monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text: warnings.append(text))
    return warnings


IW_LINK = "Connected to 00:00:00:00:00:00 (on wlan0)\n\tfreq: 5180\n\tsignal: -44 dBm\n\ttx bitrate: 540.4 MBit/s\n"


def window(qapp, sys_root, proc_root, usr_root, paths, tmp_path, helper=None, log=LOG_WORKED,
           kernel=KERNEL, which=None, boot_log="") -> MainWindow:
    return MainWindow(sys_root=sys_root, proc_root=proc_root, usr_root=usr_root, paths=paths,
                      data_dir=tmp_path / "home/data", runner=helper or Helper(paths), log_reader=lambda: log,
                      kernel=kernel, which=which or (lambda tool: "/usr/bin/" + tool), clock=lambda: 1000.0,
                      lib_root=tmp_path / "lib/modules", boot_log_reader=lambda: boot_log,
                      link_runner=lambda _argv: IW_LINK)


def test_shows_the_owners_stick_without_the_driver_installed(qapp, sys_root, proc_root, usr_root, paths, tmp_path):
    w = window(qapp, sys_root, proc_root, usr_root, paths, tmp_path)
    assert w.stick_box.value.text() == "Wi-Fi mode" and "AIC 8800D80 (a69c:8d81)" in w.stick_box.toolTip()
    assert w.chip_box.value.text() == "MCU 1" and "revision U03" in w.chip_box.toolTip()
    assert w.driver_box.value.text() == "Not installed" and w.wifi_box.value.text() == "wlan0"
    assert w.branch == "legacy-mcu1"
    assert w.badge.text() == "Connected"
    assert w.build_button.isEnabled() and w.build_button.text() == "Build"
    assert not w.install_button.isEnabled() and w.install_button.text() == "Install…"
    assert not w.remove_button.isEnabled()
    assert "not installed" in w.events_label.text()


def test_stick_modes_and_no_stick(qapp, sys_root, proc_root, usr_root, paths, tmp_path):
    w = window(qapp, sys_root, proc_root, usr_root, paths, tmp_path, log="")
    set_stick(sys_root, "storage")
    write(proc_root / "modules", "")
    w.refresh()
    assert w.stick_box.value.text() == "storage mode" and w.wifi_box.value.text() == "—"
    assert "sits in storage mode" in w.driver_note.text() and "sudo eject /dev/sdX" in w.driver_note.text()
    assert w.chip_box.value.text() == "Unknown" and w.branch == "main"
    assert "has not answered yet" in w.driver_note.text()
    set_stick(sys_root, "loader")
    w.refresh()
    assert w.stick_box.value.text() == "waiting for its firmware"
    set_stick(sys_root, None)
    w.refresh()
    assert w.stick_box.value.text() == "None" and w.badge.text() == "Not installed"


def test_the_wifi_adapters(qapp, sys_root, proc_root, usr_root, paths, tmp_path):
    w = window(qapp, sys_root, proc_root, usr_root, paths, tmp_path)
    (adapter,) = w.adapters
    assert adapter.verdict == "connected"
    assert "AIC 8800D80 (a69c:8d81, USB 2-5)" in w.adapters_label.text()
    assert "5 GHz (5180 MHz), signal -44 dBm, 540.4 Mbit/s" in w.adapters_label.text()
    set_stick(sys_root, "storage")
    w.refresh(read_log=True)
    assert "build and install the driver here" in w.adapters_label.text()
    # A stick of another chip, which the running kernel has a driver for, not loaded.
    write(tmp_path / "lib/modules" / KERNEL / "modules.dep", "kernel/drivers/net/wireless/mediatek/mt76/mt7921u.ko:")
    write(tmp_path / "lib/modules" / KERNEL / "modules.alias", "alias usb:v0E8Dp7961d*dc*dsc*dp*ic*isc*ip*in* mt7921u")
    set_stick(sys_root, None)
    usb_device(sys_root, "1-3", "0e8d", "7961", "Wireless_Device", {"3.0": None})
    write(sys_root / "bus/usb/devices/1-3:3.0/modalias", "usb:v0E8Dp7961d0100dc00dsc00dp00icFFiscFFipFFin00")
    w = window(qapp, sys_root, proc_root, usr_root, paths, tmp_path)
    assert "has a driver for it (mt7921u), but it is not loaded" in w.adapters_label.text()
    set_stick(sys_root, None)
    import shutil
    shutil.rmtree(sys_root / "bus/usb/devices/1-3")
    w.refresh()                                 # the adapters are read with the kernel log, not at every refresh
    assert "mt7921u" in w.adapters_label.text()
    w.refresh(read_log=True)
    assert "No Wi-Fi adapter" in w.adapters_label.text() and "from this app." in w.adapters_label.text()


def test_a_failed_upload_points_at_the_legacy_branch(qapp, sys_root, proc_root, usr_root, paths, tmp_path):
    w = window(qapp, sys_root, proc_root, usr_root, paths, tmp_path, log=LOG_FAILED)
    assert w.branch == "legacy-mcu1" and "broke off at 0x170400" in w.driver_note.text()
    assert "needs the legacy-mcu1 branch" in w.driver_note.text()


def test_missing_build_tree_or_tools(qapp, sys_root, proc_root, usr_root, paths, tmp_path):
    w = window(qapp, sys_root, proc_root, usr_root, paths, tmp_path, kernel="7.3.0-none")
    assert "No kernel build tree for 7.3.0-none" in w.driver_note.text() and not w.build_button.isEnabled()
    w = window(qapp, sys_root, proc_root, usr_root, paths, tmp_path,
               which=lambda tool: None if tool == "gcc" else "/usr/bin/" + tool)
    assert "Not installed: gcc" in w.driver_note.text() and not w.build_button.isEnabled()


def test_build_runs_the_steps_and_collects(qapp, sys_root, proc_root, usr_root, paths, tmp_path, monkeypatch):
    w = window(qapp, sys_root, proc_root, usr_root, paths, tmp_path)
    started = []

    def fake_start(steps):
        started.extend(steps)
        # The fetch and the make "happened": leave what they leave.
        fake_source(w.building.source)
        for module in builder.built_modules(w.building):
            write(module, "ELF")
        w.steps.on_done(True)

    monkeypatch.setattr(w.steps, "start", fake_start)
    w.build()
    layout = w.layout_for("legacy-mcu1")
    assert started[0].argv[:2] == ["git", "init"] and started[-1].argv[0] == "make"
    assert started[-1].argv[-1] == "modules" and f"M={layout.module_dir}" in started[-1].argv
    assert builder.complete(layout.output) and (layout.output / "build.log").read_text().startswith("Building legacy")
    assert builder.output_commit(layout.output) == builder.PINS["legacy-mcu1"].commit
    assert "Built:" in w.terminal.toPlainText()
    assert not w.busy and w.install_button.isEnabled() and w.build_button.text() == "Build again"
    assert w.driver_box.value.text() == "Built"


def test_newest_sources_build_and_install(qapp, sys_root, proc_root, usr_root, paths, tmp_path, monkeypatch, yes):
    helper = Helper(paths)
    w = window(qapp, sys_root, proc_root, usr_root, paths, tmp_path, helper=helper)
    w.newest_check.setChecked(True)
    assert "Newest sources" in w.driver_note.text() and "nobody has tested" in w.driver_note.text()
    started = []

    def fake_start(steps):
        started.extend(steps)
        fake_source(w.building.source)
        write(w.building.source / ".git/HEAD", "b" * 40)             # what git checked out
        for module in builder.built_modules(w.building):
            write(module, "ELF")
        w.steps.on_done(True)

    monkeypatch.setattr(w.steps, "start", fake_start)
    w.build()
    layout = w.layout_for("legacy-mcu1")
    assert layout.newest and layout.output.parent.name == "legacy-mcu1-newest"
    fetch = [s for s in started if "fetch" in s.argv][0]
    assert fetch.argv[-2:] == ["mirror", "legacy-mcu1"] and fetch.fallback[-2:] == ["upstream", "legacy-mcu1"]
    assert "untested" in w.terminal.toPlainText() and builder.output_commit(layout.output) == "b" * 40
    w.install()
    assert helper.calls[-1][helper.calls[-1].index("--commit") + 1] == "b" * 40
    assert w.driver_box.value.text() == "legacy-mcu1 (newest)" and "not the tested pin" in w.driver_box.toolTip()
    w.newest_check.setChecked(False)
    w.refresh()
    assert w.driver_box.value.text() == "legacy-mcu1 (newest)" and not w.install_button.isEnabled()


def test_a_failed_build_leaves_install_off(qapp, sys_root, proc_root, usr_root, paths, tmp_path, monkeypatch):
    w = window(qapp, sys_root, proc_root, usr_root, paths, tmp_path)
    monkeypatch.setattr(w.steps, "start", lambda steps: w.steps.on_done(False))
    w.build()
    assert not w.install_button.isEnabled() and not w.busy


def test_install_update_and_remove(qapp, sys_root, proc_root, usr_root, paths, tmp_path, yes):
    helper = Helper(paths)
    w = window(qapp, sys_root, proc_root, usr_root, paths, tmp_path, helper=helper)
    layout = w.layout_for("legacy-mcu1")
    fake_build(layout.output)
    fake_source(layout.source)
    w.refresh()
    assert w.install_button.isEnabled()
    w.install()
    assert helper.calls == [["install", "--branch", "legacy-mcu1", "--build", str(layout.output), "--source",
                             str(layout.source), "--commit", builder.PINS["legacy-mcu1"].commit, "--app-version",
                             __version__, "--kernel", KERNEL]]
    assert driver.installed(paths).branch == "legacy-mcu1"
    assert w.driver_box.value.text() == "legacy-mcu1" and w.badge.text() == "Connected"
    assert w.install_button.text() == "Update…" and w.remove_button.isEnabled()
    assert "Loaded aic_load_fw, aic8800_fdrv" in w.events_label.text()
    assert "Ejected the virtual disk of sda" in w.events_label.text()
    assert not yes
    w.remove()
    assert helper.calls[-1] == ["uninstall"]
    assert driver.installed(paths) is None and w.install_button.text() == "Install…"


def test_a_helper_error_is_shown(qapp, sys_root, proc_root, usr_root, paths, tmp_path, yes):
    w = window(qapp, sys_root, proc_root, usr_root, paths, tmp_path, helper=Helper(paths, "Not authorized"))
    layout = w.layout_for("legacy-mcu1")
    fake_build(layout.output)
    fake_source(layout.source)
    w.refresh()
    w.install()
    assert yes == ["Not authorized"] and driver.installed(paths) is None


def test_installed_states(qapp, sys_root, proc_root, usr_root, paths, tmp_path, yes):
    helper = Helper(paths)
    w = window(qapp, sys_root, proc_root, usr_root, paths, tmp_path, helper=helper)
    layout = w.layout_for("legacy-mcu1")
    fake_build(layout.output)
    fake_source(layout.source)
    w.refresh()
    w.install()
    # The modules not loaded: the service failed.
    write(proc_root / "modules", "")
    set_stick(sys_root, "loader")
    w.refresh()
    assert w.badge.text() == "Driver not loaded"
    # A new kernel without a build: the service builds at the next boot.
    w.kernel = "7.3.1-ogc1.fc44.x86_64"
    w.refresh()
    assert w.badge.text() == "No driver for this kernel"
    # The service's error shows.
    driver.write_state(paths, {"time": 1000.0, "kernel": w.kernel, "built": False, "loaded": [], "ejected": [],
                               "error": "The build for kernel x failed (exit 2)", "branch": "legacy-mcu1"})
    w.refresh()
    assert "failed (exit 2)" in w.events_label.text()
    # Installed by another version of the app.
    paths.script.write_text("# older\n")
    w.refresh()
    assert "another version of the app" in w.driver_note.text()


def test_choosing_another_branch_is_remembered(qapp, sys_root, proc_root, usr_root, paths, tmp_path):
    w = window(qapp, sys_root, proc_root, usr_root, paths, tmp_path)
    assert w.branch == "legacy-mcu1"
    w.branch_combo.setCurrentIndex(w.branch_combo.findData("main"))
    assert w.branch == "main" and w.settings.get("branch") == "main"
    w.refresh(read_log=True)
    assert w.branch == "main"
    w.branch_combo.setCurrentIndex(w.branch_combo.findData("legacy-mcu1"))
    assert w.settings.get("branch") == ""           # back to following the chip


def run_steps(qapp, steps) -> tuple[str, list]:
    output, done = [], []
    runner = StepRunner(output.append, done.append)
    runner.start(steps)
    from PyQt6.QtCore import QCoreApplication, QDeadlineTimer
    deadline = QDeadlineTimer(10000)
    while not done and not deadline.hasExpired():
        QCoreApplication.processEvents()
        qapp.processEvents()
    return "".join(output), done


def test_step_runner_runs_commands_in_turn(qapp):
    text, done = run_steps(qapp, [builder.Step(["true"]), builder.Step(["sh", "-c", "echo hello"]),
                                  builder.Step(["false"]), builder.Step(["true"])])
    assert done == [False]
    assert "$ true" in text and "hello" in text and "Stopped: exit code 1." in text and text.count("$ true") == 1


def test_step_runner_takes_the_fallback(qapp):
    text, done = run_steps(qapp, [builder.Step(["false"], fallback=["sh", "-c", "echo from upstream"],
                                               note="The mirror did not answer."),
                                  builder.Step(["true"])])
    assert done == [True]
    assert "The mirror did not answer." in text and "from upstream" in text and text.count("$ true") == 1
    text, done = run_steps(qapp, [builder.Step(["false"], fallback=["false"], note="again")])
    assert done == [False] and "again" in text and "Stopped: exit code 1." in text
