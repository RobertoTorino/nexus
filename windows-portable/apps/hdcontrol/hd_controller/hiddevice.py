# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller's HID device through hidapi (the hidapi package, module hid): feature reports (get and send), input
reports read without blocking, and output reports written. On Windows a HID device needs no rule and no driver: Windows'
own HID class driver gives every user the controller, opened shared, beside Steam and the games (the BC250 app's
hidraw.py, with hidapi in place of Linux's hidraw ioctls). hid is imported where a device is opened, so the rest of the
app (and its tests) runs without it."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

LARGEST = 64                    # the DualSense's longest feature report, with its ID byte


def feature_sizes(descriptor: bytes) -> dict[int, int]:
    """Report ID -> length of each feature report, with its ID byte. Walks the descriptor's short items and adds up
    report size times count for every Feature item; the global items carry over as HID defines it."""
    sizes: dict[int, int] = {}
    report_id = size = count = 0
    i = 0
    while i < len(descriptor):
        prefix = descriptor[i]
        if prefix == 0xFE:                          # a long item: its data length is the next byte
            i += 3 + (descriptor[i + 1] if i + 1 < len(descriptor) else 0)
            continue
        length = (0, 1, 2, 4)[prefix & 3]
        value = int.from_bytes(descriptor[i + 1:i + 1 + length], "little")
        i += 1 + length
        tag = prefix & 0xFC
        if tag == 0x84:
            report_id = value
        elif tag == 0x74:
            size = value
        elif tag == 0x94:
            count = value
        elif tag == 0xB0:
            sizes[report_id] = sizes.get(report_id, 1 if report_id else 0) + size * count // 8
    return sizes


def _hid() -> Any:
    import hid                                      # hidapi: only where a device is opened
    return hid


def _failed(device: Any, what: str, exc: Exception | None = None) -> OSError:
    """An OSError with what hidapi says went wrong (never the device's path: over Bluetooth it holds the
    controller's address)."""
    try:
        said = device.error() or ""
    except Exception:  # noqa: BLE001  (an error while reading the error: the step's name is enough)
        said = ""
    return OSError(f"{what}: {said or exc or 'the controller did not answer'}".rstrip(": "))


class Device:
    """The controller's HID device, opened by its path from hid.enumerate(). Every feature report is padded to the size
    the descriptor declares: Windows sends no other length, so neither does the app. A feature report is read into a
    buffer of the longest one, as Windows' HID class driver wants it, and cut to its own size."""

    def __init__(self, path: bytes, sizes: dict[int, int] | None = None, hid_module: Callable[[], Any] = _hid,
                 blocking: bool = True):
        self.device = hid_module().device()
        try:
            self.device.open_path(path)
        except (OSError, ValueError) as exc:
            raise OSError("it could not be opened: another program may have it to itself (DS4Windows' exclusive "
                          "mode, or HidHide)") from exc
        if not blocking:
            self.device.set_nonblocking(1)
        self.sizes = sizes if sizes is not None else self.read_sizes()
        self.open = True

    def read_sizes(self) -> dict[int, int]:
        """The feature reports' sizes from the descriptor Windows keeps for the device; {} when it gives none (every
        report is then 64 bytes, the DualSense's longest)."""
        try:
            return feature_sizes(bytes(self.device.get_report_descriptor()))
        except (OSError, ValueError, AttributeError):
            return {}

    def size(self, report_id: int) -> int:
        return self.sizes.get(report_id, LARGEST)

    def get_feature(self, report_id: int) -> bytes:
        size = self.size(report_id)
        try:
            data = bytes(self.device.get_feature_report(report_id, max(size, LARGEST, *self.sizes.values())))
        except (OSError, ValueError) as exc:
            raise _failed(self.device, f"report 0x{report_id:02x} could not be read", exc) from exc
        if not data:
            raise _failed(self.device, f"report 0x{report_id:02x} could not be read")
        return data[:size]

    def set_feature(self, data: bytes) -> None:
        buffer = bytearray(self.size(data[0]))
        if len(data) > len(buffer):
            raise ValueError(f"report 0x{data[0]:02x} is {len(buffer)} bytes; {len(data)} were given")
        buffer[:len(data)] = data
        try:
            sent = self.device.send_feature_report(bytes(buffer))
        except (OSError, ValueError) as exc:
            raise _failed(self.device, f"report 0x{data[0]:02x} could not be sent", exc) from exc
        if sent is not None and sent < 0:
            raise _failed(self.device, f"report 0x{data[0]:02x} could not be sent")

    def write(self, data: bytes) -> None:
        """An output report (the light bar, the motors); hidapi pads it to the device's output length."""
        try:
            sent = self.device.write(bytes(data))
        except (OSError, ValueError) as exc:
            raise _failed(self.device, "the output report could not be sent", exc) from exc
        if sent is not None and sent < 0:
            raise _failed(self.device, "the output report could not be sent")

    def read(self, size: int = 128) -> bytes:
        """The next input report, or b"" when none waits (opened with blocking=False)."""
        try:
            return bytes(self.device.read(size))
        except (OSError, ValueError) as exc:
            raise _failed(self.device, "the controller could not be read", exc) from exc

    def close(self) -> None:
        if self.open:
            self.open = False
            self.device.close()

    def __enter__(self) -> Device:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
