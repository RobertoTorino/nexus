# SPDX-License-Identifier: GPL-3.0-or-later
"""The HID device through hidapi, against a fake hid module: the reports' sizes from the descriptor Windows keeps,
every feature report padded to its size and read into a buffer of the longest, and hidapi's errors as OSError,
without the device's path."""

from __future__ import annotations

import pytest

from conftest import BT_PATH, DESCRIPTOR, USB_PATH
from hd_controller import hiddevice


class FakeHid:
    """hidapi's device, as the hid module gives it: it records each call; *fail* names the calls that fail."""

    def __init__(self, fail: tuple[str, ...] = (), answers: dict[int, bytes] | None = None):
        self.fail, self.answers = fail, answers or {}
        self.calls: list[tuple] = []
        self.inputs: list[bytes] = []

    def device(self):
        return self

    def _call(self, name: str, *args):
        self.calls.append((name, *args))
        if name in self.fail:
            raise OSError("read error")

    def open_path(self, path):
        self._call("open_path", path)

    def set_nonblocking(self, on):
        self._call("set_nonblocking", on)

    def get_report_descriptor(self):
        self._call("get_report_descriptor")
        return list(DESCRIPTOR)

    def get_feature_report(self, report_id, length):
        self._call("get_feature_report", report_id, length)
        return list(self.answers.get(report_id, bytes([report_id]) + bytes(length - 1)))

    def send_feature_report(self, data):
        self._call("send_feature_report", bytes(data))
        return -1 if "send_short" in self.fail else len(data)

    def write(self, data):
        self._call("write", bytes(data))
        return len(data)

    def read(self, size):
        self._call("read", size)
        return list(self.inputs.pop(0)) if self.inputs else []

    def error(self):
        return "The device is not connected."

    def close(self):
        self._call("close")


def test_the_feature_sizes_of_the_owners_edge():
    sizes = hiddevice.feature_sizes(DESCRIPTOR)
    assert sizes[0x20] == 64 and sizes[0xF4] == 64 and sizes[0xF5] == 4 and sizes[0x09] == 20
    assert sizes[0x70] == 64 and sizes[0x60] == 64 and sizes[0x68] == 64


def test_opened_with_the_sizes_windows_keeps():
    fake = FakeHid()
    device = hiddevice.Device(USB_PATH, hid_module=lambda: fake)
    assert fake.calls[:2] == [("open_path", USB_PATH), ("get_report_descriptor",)]
    assert device.size(0xF5) == 4 and device.size(0x55) == hiddevice.LARGEST
    device.close()
    device.close()
    assert fake.calls[-1] == ("close",) and fake.calls.count(("close",)) == 1


def test_a_feature_report_is_read_into_the_longest_buffer_and_cut_to_its_size():
    fake = FakeHid(answers={0xF5: bytes([0xF5, 0x01, 0x03]) + bytes(61)})
    with hiddevice.Device(USB_PATH, {0xF5: 4, 0x20: 64}, hid_module=lambda: fake) as device:
        assert device.get_feature(0xF5) == bytes([0xF5, 0x01, 0x03, 0x00])
    assert ("get_feature_report", 0xF5, 64) in fake.calls


def test_a_feature_report_is_padded_to_its_size():
    fake = FakeHid()
    device = hiddevice.Device(USB_PATH, {0xF4: 64}, hid_module=lambda: fake)
    device.set_feature(bytes([0xF4, 0x00, 0x02, 0xAA, 0xBB]))
    sent = fake.calls[-1][1]
    assert len(sent) == 64 and sent[:5] == bytes([0xF4, 0x00, 0x02, 0xAA, 0xBB]) and sent[5:] == bytes(59)
    with pytest.raises(ValueError, match="64 bytes; 65 were given"):
        device.set_feature(bytes([0xF4]) + bytes(64))


def test_hidapis_errors_are_oserrors_without_the_path():
    fake = FakeHid(fail=("get_feature_report", "send_short"))
    device = hiddevice.Device(BT_PATH, {}, hid_module=lambda: fake)
    with pytest.raises(OSError, match="report 0x20 could not be read: The device is not connected.") as error:
        device.get_feature(0x20)
    with pytest.raises(OSError, match="report 0xf4 could not be sent"):
        device.set_feature(bytes([0xF4, 0x00]))
    assert BT_PATH.decode() not in str(error.value)


def test_a_device_that_cannot_be_opened_says_why():
    with pytest.raises(OSError, match="another program may have it to itself"):
        hiddevice.Device(USB_PATH, {}, hid_module=lambda: FakeHid(fail=("open_path",)))


def test_input_reports_without_blocking_and_output_reports():
    fake = FakeHid()
    device = hiddevice.Device(USB_PATH, {}, hid_module=lambda: fake, blocking=False)
    assert ("set_nonblocking", 1) in fake.calls
    fake.inputs.append(b"\x01\x80")
    assert device.read() == b"\x01\x80" and device.read() == b""
    device.write(b"\x02\x00\x04")
    assert fake.calls[-1] == ("write", b"\x02\x00\x04")


def test_without_hidapi_nothing_is_found(monkeypatch):
    """The window looks every second: without the hid module it finds no controller, and says nothing worse."""
    from hd_controller import controller

    def missing():
        raise ImportError("No module named 'hid'")
    assert controller.find(missing) == []
