# SPDX-License-Identifier: GPL-3.0-or-later
"""HID feature reports through a hidraw node (HIDIOCGFEATURE and HIDIOCSFEATURE), and the size of each feature
report as the device's report descriptor declares it."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path


def _ioc(number: int, size: int) -> int:
    """_IOC(_IOC_READ | _IOC_WRITE, 'H', number, size), as linux/hidraw.h builds the feature ioctls."""
    return (3 << 30) | (size << 16) | (ord("H") << 8) | number


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


class Device:
    """An open hidraw node. Every report is padded to the size the descriptor declares: Windows sends no other
    length, so neither does the app."""

    def __init__(self, path: Path | str, sizes: dict[int, int]):
        self.path = str(path)
        self.sizes = sizes
        self.fd = os.open(self.path, os.O_RDWR | os.O_CLOEXEC)

    def size(self, report_id: int) -> int:
        return self.sizes.get(report_id, 64)

    def get_feature(self, report_id: int) -> bytes:
        buffer = bytearray(self.size(report_id))
        buffer[0] = report_id
        count = fcntl.ioctl(self.fd, _ioc(0x07, len(buffer)), buffer)
        return bytes(buffer[:count]) if 0 < count <= len(buffer) else bytes(buffer)

    def set_feature(self, data: bytes) -> None:
        buffer = bytearray(self.size(data[0]))
        if len(data) > len(buffer):
            raise ValueError(f"report 0x{data[0]:02x} is {len(buffer)} bytes; {len(data)} were given")
        buffer[:len(data)] = data
        fcntl.ioctl(self.fd, _ioc(0x06, len(buffer)), buffer)

    def close(self) -> None:
        if self.fd >= 0:
            fd, self.fd = self.fd, -1
            os.close(fd)

    def __enter__(self) -> Device:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
