# SPDX-License-Identifier: GPL-3.0-or-later
"""Finding the camera (camera.py) among fake Windows devices: the boot loader with and without WinUSB, the ready
camera with Windows' webcam driver, a PS4 Camera behind Sony's adapter, and the IDs and speeds of devices.py."""

from __future__ import annotations

from usb_hd_cam import camera
from usb_hd_cam.devices import Device, Speed

HUB = "USB\\VID_0BDA&PID_0411\\6&1&0&2"
ADAPTER_HUB = "USB\\VID_054C&PID_0D0B\\5&1&0&1"
BOOT = "USB\\VID_05A9&PID_0580\\7&1&0&1"
READY = "USB\\VID_05A9&PID_058C\\7&1&0&1"
VIDEO = "USB\\VID_05A9&PID_058C&MI_00\\8&1&0&0000"
FAST = Speed(super_speed=True, capable=True)
SLOW = Speed(super_speed=False, capable=True)


def device(instance: str, service: str = "", parent: str = HUB, port: int = 1, name: str = "") -> Device:
    return Device(instance=instance, service=service, problem=0 if service else 28, parent=parent, port=port,
                  name=name)


def finder(devices: list[Device], kids: dict[str, list[Device]] | None = None, speed: Speed | None = FAST,
           extra: list[Device] = ()):
    known = {d.instance: d for d in (*devices, *extra)}
    return dict(present=lambda: [d.instance for d in devices], info=known.get, speed=lambda d: speed,
                children=lambda instance: (kids or {}).get(instance, []))


def test_ids_are_read_from_the_instance():
    assert device(BOOT).ids == ("05a9", "0580")
    assert device("ROOT\\SOMETHING\\0").ids == ("", "")


def test_speed_text():
    assert FAST.text == "USB 3, 5 Gbit/s"
    assert SLOW.text == "USB 2 or slower"
    assert Speed(True, True, True).text == "USB 3, 10 Gbit/s"


def test_a_boot_loader_without_a_driver():
    found = camera.find(**finder([device(BOOT)]))
    assert [c.state for c in found] == [camera.NO_DRIVER]
    assert found[0].name == "PS5 HD Camera" and found[0].instance == BOOT


def test_a_boot_loader_with_winusb():
    found = camera.find(**finder([device(BOOT, "WinUSB")]))
    assert found[0].state == camera.BOOT_LOADER and not found[0].slow


def test_the_ready_camera_with_its_webcam_name():
    kids = {READY: [device(VIDEO, "usbvideo", parent=READY, name="USB Camera-OV580")]}
    found = camera.find(**finder([device(READY, "usbccgp"), device(VIDEO, "usbvideo", parent=READY)], kids))
    assert len(found) == 1                  # the interface is not a second camera
    assert found[0].state == camera.READY_STATE and found[0].webcam == "USB Camera-OV580"
    assert found[0].video == VIDEO          # the webcam's own device, whose driver picture.py keeps


def test_a_ready_camera_comes_first():
    found = camera.find(**finder([device(BOOT.replace("&0&1", "&0&2"), port=2), device(READY, "usbccgp")]))
    assert [c.state for c in found] == [camera.READY_STATE, camera.NO_DRIVER]


def test_a_ps4_camera_behind_sonys_adapter():
    adapter = device(ADAPTER_HUB, "USBHUB3")
    found = camera.find(**finder([device(BOOT, "WinUSB", parent=ADAPTER_HUB)], extra=[adapter]))
    assert found[0].state == camera.PS4 and found[0].name == "PS4 Camera"


def test_a_slow_port():
    found = camera.find(**finder([device(BOOT)], speed=SLOW))
    assert found[0].slow
    assert not camera.find(**finder([device(BOOT)], speed=None))[0].slow     # not known is not slow


def test_other_devices_are_left_out():
    assert camera.find(**finder([device("USB\\VID_05A9&PID_1234\\1"), device("USB\\VID_0BDA&PID_8153\\X")])) == []
