# SPDX-License-Identifier: GPL-3.0-or-later
"""Allow access (driver.py and __main__'s --bind): only the camera's boot loader is bound, the elevated copy's
command, and what each outcome tells the user. Nothing here installs a driver."""

from __future__ import annotations

import sys

import pytest

from usb_hd_cam import __main__ as entry
from usb_hd_cam import driver

BOOT = "USB\\VID_05A9&PID_0580\\7&1B484A56&0&1"


def test_only_the_boot_loader_is_bound():
    assert driver.BOOT_LOADER.fullmatch(BOOT)
    assert driver.BOOT_LOADER.fullmatch(BOOT.lower())
    for other in ("USB\\VID_05A9&PID_058C\\7&1&0&1", "USB\\VID_0BDA&PID_8153\\X", BOOT + "\\more", "PCI\\VEN_1022"):
        assert not driver.BOOT_LOADER.fullmatch(other)
    with pytest.raises(driver.DriverError, match="Not the camera's boot loader"):
        driver.bind("USB\\VID_0BDA&PID_8153\\X")


def test_the_elevated_copy_refuses_another_device():
    assert entry.bind("USB\\VID_0BDA&PID_8153\\X") == driver.NOT_A_BOOT_LOADER


def test_the_elevated_copy_reports_a_failure(monkeypatch):
    def fail(instance):
        raise driver.DriverError("Installing WinUSB: refused")
    monkeypatch.setattr(driver, "bind", fail)
    assert entry.bind(BOOT) == driver.FAILED
    monkeypatch.setattr(driver, "bind", lambda instance: None)
    assert entry.bind(BOOT) == driver.BOUND


def test_the_elevated_command_from_the_checkout():
    command = driver.elevated_command(BOOT)
    assert command[-2:] == ["--bind", BOOT] and command[1] == "-c"
    assert "usb_hd_cam.__main__" in command[2] and "sys.path" in command[2]


def test_the_elevated_command_of_the_installed_program(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "C:\\app\\USB-HD-Cam.exe")
    assert driver.elevated_command(BOOT) == ["C:\\app\\USB-HD-Cam.exe", "--bind", BOOT]


def test_what_each_outcome_says():
    assert driver.ask(BOOT, run=lambda command: driver.BOUND) == ""
    assert "declined" in driver.ask(BOOT, run=lambda command: driver.ERROR_CANCELLED)
    assert "not the camera's boot loader" in driver.ask(BOOT, run=lambda command: driver.NOT_A_BOOT_LOADER)
    assert "code 3" in driver.ask(BOOT, run=lambda command: driver.FAILED)

    def broken(command):
        raise OSError("no shell")
    assert "did not start" in driver.ask(BOOT, run=broken)
