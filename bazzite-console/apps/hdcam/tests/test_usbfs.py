# SPDX-License-Identifier: GPL-3.0-or-later
"""The usbfs ioctls: their numbers as linux/usbdevice_fs.h gives them on x86-64, and what a control transfer hands
the kernel, through a fake ioctl."""

from __future__ import annotations

import ctypes
import errno

import pytest

from usb_hdcam import usbfs


def test_ioctl_numbers():
    assert ctypes.sizeof(usbfs.CtrlTransfer) == 24
    assert usbfs.CONTROL == 0xC0185500
    assert usbfs.SETCONFIGURATION == 0x80045505
    assert usbfs.CLAIMINTERFACE == 0x8004550F
    assert usbfs.RELEASEINTERFACE == 0x80045510
    assert usbfs.RESET == 0x5514


class FakeKernel:
    def __init__(self, fail: int = 0):
        self.calls = []
        self.fail = fail

    def __call__(self, fd, request, address):
        if request == usbfs.CONTROL:
            transfer = usbfs.CtrlTransfer.from_address(address)
            data = ctypes.string_at(transfer.data, transfer.wLength)
            self.calls.append(("control", transfer.bRequestType, transfer.bRequest, transfer.wValue,
                               transfer.wIndex, transfer.timeout, data))
            result = transfer.wLength
        elif address is None:
            self.calls.append((request, None))
            result = 0
        else:
            self.calls.append((request, ctypes.c_uint.from_address(address).value))
            result = 0
        if self.fail:
            ctypes.set_errno(self.fail)
            return -1
        return result


def test_calls(tmp_path):
    node = tmp_path / "003"
    node.touch()
    kernel = FakeKernel()
    device = usbfs.Device(node, ioctl=kernel)
    device.reset()
    device.set_configuration(1)
    device.claim_interface(0)
    assert device.control_out(0x40, 0, 0x2200, 0x8018, b"\x5b") == 1
    device.close()
    device.close()                                  # twice is fine
    assert kernel.calls == [(usbfs.RESET, None), (usbfs.SETCONFIGURATION, 1), (usbfs.CLAIMINTERFACE, 0),
                            ("control", 0x40, 0, 0x2200, 0x8018, 1000, b"\x5b")]


def test_errors_carry_the_kernels_errno(tmp_path):
    node = tmp_path / "003"
    node.touch()
    device = usbfs.Device(node, ioctl=FakeKernel(fail=errno.ENODEV))
    with pytest.raises(OSError) as raised:
        device.control_out(0x40, 0, 0, 0x14, b"x" * 512)
    assert raised.value.errno == errno.ENODEV


def test_a_missing_node(tmp_path):
    with pytest.raises(FileNotFoundError):
        usbfs.Device(tmp_path / "gone", ioctl=FakeKernel())
