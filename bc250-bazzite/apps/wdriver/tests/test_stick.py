# SPDX-License-Identifier: GPL-3.0-or-later
"""The stick in its three modes, the interface, the loaded modules, the chip's answer in the kernel log, and the
kernel's build tree and tools."""

from __future__ import annotations

from pathlib import Path

from conftest import KERNEL, LOG_FAILED, LOG_WEDGED, LOG_WORKED, set_stick, usb_device, write

from usb_wifidriver import stick


def test_stick_in_wifi_mode(sys_root):
    (found,) = stick.find_sticks(sys_root)
    assert found.path == "2-5" and found.usb_id == "a69c:8d81" and found.name == "AIC 8800D80"
    assert found.mode == "wifi" and found.mode_text == "Wi-Fi mode"
    assert found.drivers == ("btusb", "btusb", "aic8800_fdrv")


def test_stick_in_storage_and_loader_mode(sys_root):
    set_stick(sys_root, "storage")
    (found,) = stick.find_sticks(sys_root)
    assert found.usb_id == "a69c:5723" and found.mode == "storage" and found.drivers == ("usb-storage",)
    set_stick(sys_root, "loader")
    (found,) = stick.find_sticks(sys_root)
    assert found.usb_id == "a69c:8d80" and found.mode == "loader" and found.mode_text == "waiting for its firmware"
    set_stick(sys_root, None)
    assert stick.find_sticks(sys_root) == ()


def test_other_vendors_are_left_out(sys_root):
    usb_device(sys_root, "1-2", "046d", "c52b", "USB Receiver", {"1.0": "usbhid"})
    usb_device(sys_root, "2-6", "368b", "8d81", "AIC 8800D80", {"1.0": "aic8800_fdrv"})
    found = stick.find_sticks(sys_root)
    assert [s.usb_id for s in found] == ["a69c:8d81", "368b:8d81"]
    assert stick.find_sticks(Path("/nowhere")) == ()


def test_wifi_interface_and_modules(sys_root, proc_root):
    (wlan,) = stick.wifi_interfaces(sys_root)
    assert wlan.name == "wlan0" and wlan.operstate == "up" and wlan.carrier
    assert stick.loaded_modules(proc_root) == ("aic_load_fw", "aic8800_fdrv")
    write(proc_root / "modules", "cfg80211 1691648 0 - Live 0x0000000000000000")
    assert stick.loaded_modules(proc_root) == ()
    set_stick(sys_root, "loader")
    assert stick.wifi_interfaces(sys_root) == ()


def test_chip_from_the_log():
    chip = stick.chip_from_log(LOG_WORKED)
    assert chip == stick.Chip(7, 1, False)
    assert chip.revision == "U03" and chip.branch == "legacy-mcu1" and chip.text == "revision U03, MCU 1"
    failed = stick.chip_from_log(LOG_FAILED)
    assert failed.upload_failed and failed.branch == "legacy-mcu1"
    # The last answer counts: after the failed attempt the legacy branch worked.
    assert stick.chip_from_log(LOG_FAILED + LOG_WORKED) == stick.Chip(7, 1, False)
    assert stick.chip_from_log(LOG_WORKED + "chip_id=3, chip_mcu_id = 0\n") == stick.Chip(3, 0, False)
    assert stick.chip_from_log("chip_id=3, chip_mcu_id = 0\n").branch == "main"
    assert stick.chip_from_log("chip_id=1f, chip_mcu_id = 0\n").revision == "U05"
    assert stick.chip_from_log("chip_id=5, chip_mcu_id = 0\n").revision == "0x5"


def test_a_wedged_stick_is_no_answer():
    assert stick.chip_from_log(LOG_WEDGED) is None
    assert stick.chip_from_log(LOG_WORKED + LOG_WEDGED) == stick.Chip(7, 1, False)
    assert stick.chip_from_log("") is None


def test_kernel_log_is_read_from_the_journal():
    calls = []
    stick.read_kernel_log(lambda argv: calls.append(argv) or "chip_id=7, chip_mcu_id = 1")
    assert calls == [["journalctl", "-k", "-o", "cat", "--no-pager"]]
    assert stick.run_text(["/nonexistent/journalctl"]) == ""


def test_build_tree_and_tools(usr_root):
    assert stick.build_tree(KERNEL, usr_root) == usr_root / "lib/modules" / KERNEL / "build"
    assert stick.build_tree("7.3.0-ogc1.fc44.x86_64", usr_root) is None
    assert stick.missing_tools(lambda tool: "/usr/bin/" + tool) == ()
    assert stick.missing_tools(lambda tool: None if tool == "git" else "/usr/bin/" + tool) == ("git",)
