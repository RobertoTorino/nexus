# SPDX-License-Identifier: GPL-3.0-or-later
"""The device's BIOS (device.py and __main__'s --read-variables): its identity, the variables never read (personal
data), the elevated copy's request and result, its command, and what each outcome tells the user. Nothing here asks
Windows for an administrator or reads a firmware variable."""

from __future__ import annotations

import base64
import json
import sys

import pytest

from bios_reader import __main__ as entry
from bios_reader import device

AMD = ("3A997502-647A-4C82-998E-52EF9486A247", "AmdSetup")
SETUP = ("EC87D643-EBA4-4BB5-A1E5-3F3E36B20DA9", "Setup")
WIFI = ("EC87D643-EBA4-4BB5-A1E5-3F3E36B20DA9", "WifiSetupManageNetwork")


def test_identity():
    values = {"BIOSVendor": "AMI", "BIOSVersion": "RC73XA.319", "BIOSReleaseDate": "09/23/2026",
              "SystemProductName": "ROG Xbox Ally X RC73XA_RC73XA"}
    found, model = device.identity(lambda name: values.get(name, ""))
    assert (found.vendor, found.version, found.date, model) == ("AMI", "RC73XA.319", "09/23/2026", values[
        "SystemProductName"])
    assert device.identity(lambda name: {"BaseBoardProduct": "RC73XA"}.get(name, ""))[1] == "RC73XA"


@pytest.mark.parametrize("name", ["WifiSetup", "AsusWifiBt", "NetworkStackVar", "VlanNvData", "RtkNvData",
                                  "TLS_AUTH_CONFIG_IFR_NVDATA", "HTTP_BOOT_CONFIG_IFR_NVDATA", "BootOrder",
                                  "AddBootOption", "SystemAccess", "VendorKeys", "PK", "KEK", "db", "dbx",
                                  "DriverOrder", "LegacyDev", "UsbMassDevValid", "AsusCoreInfo"])
def test_personal_data_is_never_read(name):
    assert device.private(("X", name))


@pytest.mark.parametrize("name", ["Setup", "AmdSetup", "AMD_PBS_SETUP", "PlatformLang", "PlatformLangCodes",
                                  "AodSetupStx", "AsusCbsConfig", "PmfSetupVar", "AMITSESetup", "Timeout"])
def test_the_settings_are_read(name):
    assert not device.private(("X", name))


def test_what_the_elevated_copy_reads():
    found = {AMD: b"\x01\x02"}
    result = device.read_all([AMD, SETUP, WIFI], read=lambda name, guid: found.get((guid, name)))
    assert result == {"read": {f"{AMD[0]}|AmdSetup": base64.b64encode(b"\x01\x02").decode()},
                      "missing": [f"{SETUP[0]}|Setup"]}


def test_the_elevated_copy_refuses_another_request(tmp_path):
    request, result = tmp_path / device.REQUEST, tmp_path / device.RESULT
    assert device.run_request(tmp_path / "other.json", result) == device.BAD_REQUEST
    assert device.run_request(request, tmp_path / "other.json") == device.BAD_REQUEST
    request.write_text("not json", encoding="utf-8")
    assert device.run_request(request, result) == device.BAD_REQUEST
    assert not result.exists()


def test_the_elevated_copy_without_the_right(tmp_path):
    request, result = tmp_path / device.REQUEST, tmp_path / device.RESULT
    request.write_text(json.dumps({"variables": [list(AMD)]}), encoding="utf-8")

    def refused():
        raise device.DeviceError("no right")
    assert device.run_request(request, result, enable=refused) == device.NO_PRIVILEGE
    assert device.run_request(request, result, enable=lambda: None,
                              read=lambda name, guid: b"\x05") == device.READ
    assert json.loads(result.read_text(encoding="utf-8"))["read"] == {f"{AMD[0]}|AmdSetup": "BQ=="}


def test_reading_the_settings(tmp_path):
    """The window's side: the request written, the elevated copy run (here in this process), the result read and
    both files removed; a private variable is never asked for."""
    asked = []

    def run(command):
        request, result = command[-2], command[-1]
        asked.extend(json.loads(open(request, encoding="utf-8").read())["variables"])
        return device.run_request(device.Path(request), device.Path(result), enable=lambda: None,
                                  read=lambda name, guid: b"\x07" if name == "AmdSetup" else None)
    read, missing = device.read_settings([AMD, SETUP, WIFI], tmp_path, run=run)
    assert read == {AMD: b"\x07"} and missing == [SETUP]
    assert [tuple(key) for key in asked] == [AMD, SETUP]
    assert list(tmp_path.iterdir()) == []


def test_what_each_outcome_says(tmp_path):
    with pytest.raises(device.DeviceError, match="declined"):
        device.read_settings([AMD], tmp_path, run=lambda command: device.ERROR_CANCELLED)
    with pytest.raises(device.DeviceError, match="administrator's rights"):
        device.read_settings([AMD], tmp_path, run=lambda command: device.NO_PRIVILEGE)
    with pytest.raises(device.DeviceError, match="code 3"):
        device.read_settings([AMD], tmp_path, run=lambda command: device.FAILED)
    with pytest.raises(device.DeviceError, match="result could not be read"):
        device.read_settings([AMD], tmp_path, run=lambda command: device.READ)
    with pytest.raises(device.DeviceError, match="no variable"):
        device.read_settings([WIFI], tmp_path, run=lambda command: device.READ)

    def broken(command):
        raise OSError("no shell")
    with pytest.raises(device.DeviceError, match="did not start"):
        device.read_settings([AMD], tmp_path, run=broken)
    assert list(tmp_path.iterdir()) == []


def test_the_elevated_command_from_the_checkout(tmp_path):
    command = device.elevated_command(tmp_path / device.REQUEST, tmp_path / device.RESULT)
    assert command[1] == "-c" and "bios_reader.__main__" in command[2] and "sys.path" in command[2]
    assert command[-3:] == ["--read-variables", str(tmp_path / device.REQUEST), str(tmp_path / device.RESULT)]


def test_the_elevated_command_of_the_installed_program(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "C:\\app\\BIOS-Reader.exe")
    assert device.elevated_command(tmp_path / "a.json", tmp_path / "b.json") == [
        "C:\\app\\BIOS-Reader.exe", "--read-variables", str(tmp_path / "a.json"), str(tmp_path / "b.json")]


def test_the_entry_point_runs_the_elevated_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(device, "run_request", lambda request, result: device.NO_PRIVILEGE)
    monkeypatch.setattr(sys, "argv", ["bios_reader", "--read-variables", str(tmp_path / device.REQUEST),
                                      str(tmp_path / device.RESULT)])
    assert entry.main() == device.NO_PRIVILEGE
