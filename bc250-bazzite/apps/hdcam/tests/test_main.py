# SPDX-License-Identifier: GPL-3.0-or-later
"""python -m usb_hdcam --load [--auto]: what the load service does, without a window."""

from __future__ import annotations

import sys

import pytest
from conftest import FIRMWARE, plug

from usb_hdcam import INFO, __main__ as entry, camera, firmware, loader
from usb_hdcam.settings import CameraSettings
from test_controls import FakeKernel, open_fake


def run(tmp_path, auto=False, outcome=loader.Outcome(True, "The PS5 HD Camera is ready: /dev/video2."),
        kernel=None):
    loads = []
    code = entry.load_all(auto, find=lambda: camera.find(tmp_path),
                          load=lambda boot, data: loads.append((boot.port, data)) or outcome,
                          open_controls=lambda node: open_fake(kernel or FakeKernel()))
    return code, loads


def test_nothing_to_do(tmp_path, capsys):
    assert run(tmp_path) == (0, [])
    assert capsys.readouterr().out.strip() == f"No camera found. {camera.NOT_FOUND}"   # in the service's journal
    plug(tmp_path, product="058c", address=4, videos=(2,))
    assert run(tmp_path) == (0, [])
    assert capsys.readouterr().out.strip() == "No camera waits for its firmware."


def test_loads_a_waiting_camera(tmp_path, capsys):
    plug(tmp_path)
    plug(tmp_path, port="7-2", product="058c", address=5, videos=(0,))         # ready already: left alone
    firmware.store("cfi-zey1", FIRMWARE)
    assert run(tmp_path) == (0, [("7-1", FIRMWARE)])
    assert "PS5 HD Camera on port 7-1: The PS5 HD Camera is ready" in capsys.readouterr().out


def test_without_firmware(tmp_path, capsys):
    plug(tmp_path)
    assert run(tmp_path) == (1, [])
    assert "no firmware for it yet" in capsys.readouterr().out


def test_a_failed_load(tmp_path):
    plug(tmp_path)
    firmware.store("cfi-zey1", FIRMWARE)
    assert run(tmp_path, outcome=loader.Outcome(False, "No."))[0] == 1


def test_auto_follows_the_setting(tmp_path, qapp):
    plug(tmp_path)
    firmware.store("cfi-zey1", FIRMWARE)
    assert run(tmp_path, auto=True)[1] == [("7-1", FIRMWARE)]
    CameraSettings(INFO).set("autoload", False)
    assert run(tmp_path, auto=True) == (0, [])
    assert run(tmp_path)[1] == [("7-1", FIRMWARE)]                  # by hand it loads all the same


def test_the_firmware_goes_with_the_chosen_bandwidth(tmp_path, monkeypatch, qapp):
    plug(tmp_path)
    firmware.store("cfi-zey1", FIRMWARE)
    sent = []
    monkeypatch.setattr(loader, "with_bandwidth", lambda data, bursts: sent.append(bursts) or data)
    run(tmp_path)
    CameraSettings(INFO).set("bandwidth", "full")
    run(tmp_path)
    assert sent == [2, 3]


def test_auto_needs_load(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["usb_hdcam", "--auto"])
    with pytest.raises(SystemExit):
        entry.main()


def test_the_chosen_picture_settings_are_set_after_the_load(tmp_path, qapp, capsys):
    plug(tmp_path)
    firmware.store("cfi-zey1", FIRMWARE)
    CameraSettings(INFO).set_controls({"brightness": 7})
    ready = camera.Camera("cfi-zey1", True, tmp_path / "7-1", 7, 4, 5000, ("/dev/video2",))
    kernel = FakeKernel()
    assert run(tmp_path, outcome=loader.Outcome(True, "ready", ready), kernel=kernel)[0] == 0
    assert kernel.values[0x980900] == 7 and kernel.values[0x9a0901] == 0
    assert run(tmp_path, outcome=loader.Outcome(True, "ready", ready), kernel=FakeKernel(refuse={0x980900}))[0] == 0
    assert "refused Brightness" in capsys.readouterr().out


def test_settings_survive_a_bad_value(qapp):
    settings = CameraSettings(INFO)
    settings.set("controls", "not json")
    assert settings.controls() == {"auto_exposure": 0}
    settings.set("controls", '{"brightness": 5, "name": "x"}')
    assert settings.controls() == {"auto_exposure": 0, "brightness": 5}
    settings.set_controls({"auto_exposure": 2})
    assert settings.controls() == {"auto_exposure": 2}                  # the user's choice over the app's default
