# SPDX-License-Identifier: GPL-3.0-or-later
"""V4L2 capture against a fake kernel: the structures' sizes and ioctl numbers (linux/videodev2.h on x86-64), every
mode at each of its rates, the exact rate set, and frames read with the driver's damage mark, as on the owner's
board (23-10-2026: 2560x800 at 60 fps with Reduced bandwidth gave partial frames flagged 0x40)."""

from __future__ import annotations

import ctypes
import errno

import pytest

from usb_hdcam import v4l2
from usb_hdcam.modes import Mode

# Frame sizes and their intervals (numerator, denominator: 100 ns units) as the PS5 HD Camera reports a few.
SIZES = {(1920, 1080): [(333333, 10000000), (666666, 10000000), (1250000, 10000000)],
         (2560, 800): [(166666, 10000000), (333333, 10000000)],
         (320, 184): [(41666, 10000000)]}


def test_structure_sizes_and_ioctl_numbers():
    sizes = {v4l2.FmtDesc: 64, v4l2.FrmSizeEnum: 44, v4l2.FrmIvalEnum: 52, v4l2.Format: 208, v4l2.StreamParm: 204,
             v4l2.RequestBuffers: 20, v4l2.Buffer: 88}
    assert {s: ctypes.sizeof(s) for s in sizes} == sizes
    assert (v4l2.ENUM_FMT, v4l2.S_FMT, v4l2.REQBUFS, v4l2.QUERYBUF, v4l2.QBUF, v4l2.DQBUF) == \
        (0xc0405602, 0xc0d05605, 0xc0145608, 0xc0585609, 0xc058560f, 0xc0585611)
    assert (v4l2.STREAMON, v4l2.STREAMOFF, v4l2.S_PARM, v4l2.ENUM_FRAMESIZES, v4l2.ENUM_FRAMEINTERVALS) == \
        (0x40045612, 0x40045613, 0xc0cc5616, 0xc02c564a, 0xc034564b)
    assert v4l2.Buffer.flags.offset == 12 and v4l2.Buffer.m.offset == 64 and v4l2.Buffer.length.offset == 72
    assert v4l2.fourcc("YUYV") == 0x56595559 and v4l2.name(0x56595559) == "YUYV"


class FakeKernel:
    """A UVC camera with one pixel format, YUYV, and the sizes above. *frames*: (bytesused, flags) per dequeue."""

    def __init__(self, frames=(), busy=False):
        self.frames = list(frames)
        self.busy = busy
        self.calls = []
        self.queued = []
        self.format = None
        self.interval = None

    def __call__(self, fd, request, argument):
        self.calls.append(request)
        if request == v4l2.ENUM_FMT:
            if argument.index > 0:
                raise OSError(errno.EINVAL, "no more")
            argument.pixelformat = v4l2.YUYV
        elif request == v4l2.ENUM_FRAMESIZES:
            sizes = list(SIZES)
            if argument.index >= len(sizes):
                raise OSError(errno.EINVAL, "no more")
            argument.type = v4l2.FRMSIZE_TYPE_DISCRETE
            argument.size.discrete.width, argument.size.discrete.height = sizes[argument.index]
        elif request == v4l2.ENUM_FRAMEINTERVALS:
            rates = SIZES[(argument.width, argument.height)]
            if argument.index >= len(rates):
                raise OSError(errno.EINVAL, "no more")
            argument.type = v4l2.FRMIVAL_TYPE_DISCRETE
            argument.interval.discrete.numerator, argument.interval.discrete.denominator = rates[argument.index]
        elif request == v4l2.S_FMT:
            if self.busy:
                raise OSError(errno.EBUSY, "Device or resource busy")
            self.format = (argument.fmt.pix.width, argument.fmt.pix.height, argument.fmt.pix.pixelformat)
            argument.fmt.pix.sizeimage = argument.fmt.pix.width * argument.fmt.pix.height * 2
        elif request == v4l2.S_PARM:
            fraction = argument.parm.capture.timeperframe
            self.interval = (fraction.numerator, fraction.denominator)
        elif request == v4l2.REQBUFS:
            argument.count = 2
        elif request == v4l2.QUERYBUF:
            argument.length, argument.m.offset = 64, argument.index * 4096
        elif request == v4l2.QBUF:
            self.queued.append(argument.index)
            argument.flags, argument.bytesused = 0x2, 0           # the kernel rewrites them on queueing
        elif request == v4l2.DQBUF:
            if not self.frames:
                raise BlockingIOError(errno.EAGAIN, "again")
            argument.index = self.queued.pop(0)
            argument.bytesused, argument.flags = self.frames.pop(0)


class FakeMap(bytearray):
    def close(self):
        self.closed = True


def camera(kernel, ready=True):
    maps = []

    def make(fd, length, offset):
        maps.append(FakeMap(bytes([offset // 4096 + 1]) * length))
        return maps[-1]
    found = v4l2.Camera("/dev/video1", ioctl=kernel, open_node=lambda path: -1, map=make,
                        wait=lambda fd, timeout: ready)
    found.maps = maps
    return found


def test_every_size_at_each_rate():
    modes = camera(FakeKernel()).modes()
    assert [m.key for m in modes] == ["1920x1080@30", "1920x1080@15", "1920x1080@8", "2560x800@60", "2560x800@30",
                                      "320x184@240"]
    assert {m.pixel_format for m in modes} == {"YUYV"}


def test_start_sets_the_size_and_the_exact_rate():
    kernel = FakeKernel()
    found = camera(kernel)
    found.start(Mode(2560, 800, 30, "YUYV"))
    assert kernel.format == (2560, 800, v4l2.YUYV) and kernel.interval == (333333, 10000000)
    assert found.streaming and len(found.buffers) == 2 and kernel.queued == [0, 1]
    assert found.mode == Mode(2560, 800, 30, "YUYV") and found.size == 2560 * 800 * 2


def test_frames_complete_and_damaged():
    size = 2560 * 800 * 2
    kernel = FakeKernel(frames=[(size, 0x12001), (72664, 0x12041), (size, 0x12041)])
    found = camera(kernel)
    found.start(Mode(2560, 800, 30, "YUYV"))
    first, second, third = found.read(0.5), found.read(0.5), found.read(0.5)
    assert not first.damaged and first.data[:1] == b"\x01"
    assert second.damaged and third.damaged                         # short, and flagged even when full
    assert found.read(0.5) is None                                  # nothing more yet (EAGAIN)
    assert sorted(kernel.queued) == [0, 1]                          # each buffer back in the queue
    found.close()
    assert v4l2.STREAMOFF in kernel.calls and found.buffers == [] and not found.streaming
    found.close()                                                   # twice is fine


def test_no_frame_within_the_timeout():
    found = camera(FakeKernel(), ready=False)
    found.start(Mode(1920, 1080, 30, "YUYV"))
    assert found.read(0.1) is None


def test_a_busy_camera():
    found = camera(FakeKernel(busy=True))
    with pytest.raises(OSError) as raised:
        found.start(Mode(1920, 1080, 30, "YUYV"))
    assert raised.value.errno == errno.EBUSY
