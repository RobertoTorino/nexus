# SPDX-License-Identifier: GPL-3.0-or-later
"""Video capture through V4L2 on the camera's /dev/video<n>, with the standard library only: every mode the camera
reports, each frame size at each of its rates, and frames streamed into memory-mapped buffers.

Qt Multimedia, the app's first preview, lists one entry per frame size with a range of rates and always streams at
the fastest; with Reduced bandwidth the fastest side-by-side rates do not fit, so the rates that do (2560x800 at 30,
3840x1080 at 8) could not be chosen. And the kernel hands on frames it could not complete (uvcvideo's nodrop): Qt
showed them, half garbage, as if all were well (owner's board, 23-10-2026). Here a damaged frame is marked as such.
Errors come as OSError with the kernel's errno."""

from __future__ import annotations

import ctypes
import fcntl
import mmap
import os
import select
from dataclasses import dataclass

from .modes import Mode

BUF_TYPE_VIDEO_CAPTURE = 1
MEMORY_MMAP = 1
FIELD_NONE = 1
FRMSIZE_TYPE_DISCRETE = 1
FRMIVAL_TYPE_DISCRETE = 1
BUF_FLAG_ERROR = 0x40
BUFFERS = 4


def fourcc(code: str) -> int:
    return int.from_bytes(code.encode(), "little")


def name(code: int) -> str:
    return code.to_bytes(4, "little").decode(errors="replace").strip("\0 ")


YUYV = fourcc("YUYV")


class Fract(ctypes.Structure):
    _fields_ = [("numerator", ctypes.c_uint32), ("denominator", ctypes.c_uint32)]


class FmtDesc(ctypes.Structure):
    """struct v4l2_fmtdesc."""
    _fields_ = [("index", ctypes.c_uint32), ("type", ctypes.c_uint32), ("flags", ctypes.c_uint32),
                ("description", ctypes.c_char * 32), ("pixelformat", ctypes.c_uint32),
                ("mbus_code", ctypes.c_uint32), ("reserved", ctypes.c_uint32 * 3)]


class FrmSizeDiscrete(ctypes.Structure):
    _fields_ = [("width", ctypes.c_uint32), ("height", ctypes.c_uint32)]


class FrmSizeUnion(ctypes.Union):
    _fields_ = [("discrete", FrmSizeDiscrete), ("stepwise", ctypes.c_uint32 * 6)]


class FrmSizeEnum(ctypes.Structure):
    """struct v4l2_frmsizeenum."""
    _fields_ = [("index", ctypes.c_uint32), ("pixel_format", ctypes.c_uint32), ("type", ctypes.c_uint32),
                ("size", FrmSizeUnion), ("reserved", ctypes.c_uint32 * 2)]


class FrmIvalUnion(ctypes.Union):
    _fields_ = [("discrete", Fract), ("stepwise", Fract * 3)]


class FrmIvalEnum(ctypes.Structure):
    """struct v4l2_frmivalenum."""
    _fields_ = [("index", ctypes.c_uint32), ("pixel_format", ctypes.c_uint32), ("width", ctypes.c_uint32),
                ("height", ctypes.c_uint32), ("type", ctypes.c_uint32), ("interval", FrmIvalUnion),
                ("reserved", ctypes.c_uint32 * 2)]


class PixFormat(ctypes.Structure):
    """struct v4l2_pix_format."""
    _fields_ = [("width", ctypes.c_uint32), ("height", ctypes.c_uint32), ("pixelformat", ctypes.c_uint32),
                ("field", ctypes.c_uint32), ("bytesperline", ctypes.c_uint32), ("sizeimage", ctypes.c_uint32),
                ("colorspace", ctypes.c_uint32), ("priv", ctypes.c_uint32), ("flags", ctypes.c_uint32),
                ("ycbcr_enc", ctypes.c_uint32), ("quantization", ctypes.c_uint32), ("xfer_func", ctypes.c_uint32)]


class FormatUnion(ctypes.Union):
    # 200 bytes, aligned as the kernel's (struct v4l2_window in it holds pointers)
    _fields_ = [("pix", PixFormat), ("raw_data", ctypes.c_uint8 * 200), ("align", ctypes.c_void_p)]


class Format(ctypes.Structure):
    """struct v4l2_format."""
    _fields_ = [("type", ctypes.c_uint32), ("fmt", FormatUnion)]


class CaptureParm(ctypes.Structure):
    """struct v4l2_captureparm."""
    _fields_ = [("capability", ctypes.c_uint32), ("capturemode", ctypes.c_uint32), ("timeperframe", Fract),
                ("extendedmode", ctypes.c_uint32), ("readbuffers", ctypes.c_uint32),
                ("reserved", ctypes.c_uint32 * 4)]


class ParmUnion(ctypes.Union):
    _fields_ = [("capture", CaptureParm), ("raw_data", ctypes.c_uint8 * 200)]


class StreamParm(ctypes.Structure):
    """struct v4l2_streamparm."""
    _fields_ = [("type", ctypes.c_uint32), ("parm", ParmUnion)]


class RequestBuffers(ctypes.Structure):
    """struct v4l2_requestbuffers."""
    _fields_ = [("count", ctypes.c_uint32), ("type", ctypes.c_uint32), ("memory", ctypes.c_uint32),
                ("capabilities", ctypes.c_uint32), ("flags", ctypes.c_uint8), ("reserved", ctypes.c_uint8 * 3)]


class TimeVal(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class TimeCode(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("flags", ctypes.c_uint32), ("frames", ctypes.c_uint8),
                ("seconds", ctypes.c_uint8), ("minutes", ctypes.c_uint8), ("hours", ctypes.c_uint8),
                ("userbits", ctypes.c_uint8 * 4)]


class BufferM(ctypes.Union):
    _fields_ = [("offset", ctypes.c_uint32), ("userptr", ctypes.c_ulong), ("planes", ctypes.c_void_p),
                ("fd", ctypes.c_int32)]


class Buffer(ctypes.Structure):
    """struct v4l2_buffer."""
    _fields_ = [("index", ctypes.c_uint32), ("type", ctypes.c_uint32), ("bytesused", ctypes.c_uint32),
                ("flags", ctypes.c_uint32), ("field", ctypes.c_uint32), ("timestamp", TimeVal),
                ("timecode", TimeCode), ("sequence", ctypes.c_uint32), ("memory", ctypes.c_uint32),
                ("m", BufferM), ("length", ctypes.c_uint32), ("reserved2", ctypes.c_uint32),
                ("request_fd", ctypes.c_int32)]


def _iowr(number: int, size: int) -> int:
    return (3 << 30) | (size << 16) | (ord("V") << 8) | number


def _iow(number: int, size: int) -> int:
    return (1 << 30) | (size << 16) | (ord("V") << 8) | number


ENUM_FMT = _iowr(2, ctypes.sizeof(FmtDesc))
S_FMT = _iowr(5, ctypes.sizeof(Format))
REQBUFS = _iowr(8, ctypes.sizeof(RequestBuffers))
QUERYBUF = _iowr(9, ctypes.sizeof(Buffer))
QBUF = _iowr(15, ctypes.sizeof(Buffer))
DQBUF = _iowr(17, ctypes.sizeof(Buffer))
STREAMON = _iow(18, ctypes.sizeof(ctypes.c_int))
STREAMOFF = _iow(19, ctypes.sizeof(ctypes.c_int))
S_PARM = _iowr(22, ctypes.sizeof(StreamParm))
ENUM_FRAMESIZES = _iowr(74, ctypes.sizeof(FrmSizeEnum))
ENUM_FRAMEINTERVALS = _iowr(75, ctypes.sizeof(FrmIvalEnum))


def _ioctl(fd: int, request: int, argument) -> None:
    fcntl.ioctl(fd, request, argument)


@dataclass(frozen=True)
class Frame:
    data: bytes
    damaged: bool                           # the driver could not complete it (V4L2_BUF_FLAG_ERROR)


def _rate(interval: Fract) -> int:
    return round(interval.denominator / interval.numerator) if interval.numerator else 0


class Camera:
    """An open video node. *ioctl* is (fd, request, ctypes structure) -> None, raising OSError; *open_node*, *map*
    and *wait* stand in for os.open, mmap.mmap and select.select in the tests."""

    def __init__(self, node: str | os.PathLike, ioctl=_ioctl, open_node=None, map=None, wait=None):
        self.fd = (open_node or (lambda path: os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)))(node)
        self._ioctl = ioctl
        self._map = map or (lambda fd, length, offset: mmap.mmap(fd, length, mmap.MAP_SHARED,
                                                                 mmap.PROT_READ | mmap.PROT_WRITE, offset=offset))
        self._wait = wait or (lambda fd, timeout: bool(select.select([fd], [], [], timeout)[0]))
        self.buffers: list = []
        self.mode: Mode | None = None
        self.size = 0
        self.streaming = False

    def _each(self, structure, request: int, **fields):
        """Every answer of an enumerating ioctl, by index, until the driver says there are no more (EINVAL)."""
        index = 0
        while True:
            item = structure(index=index, **fields)
            try:
                self._ioctl(self.fd, request, item)
            except OSError as exc:
                if exc.errno == 22:
                    return
                raise
            yield item
            index += 1

    def modes(self) -> list[Mode]:
        """Every frame size of every pixel format, at each of its discrete rates."""
        found = []
        for desc in list(self._each(FmtDesc, ENUM_FMT, type=BUF_TYPE_VIDEO_CAPTURE)):
            for size in list(self._each(FrmSizeEnum, ENUM_FRAMESIZES, pixel_format=desc.pixelformat)):
                if size.type != FRMSIZE_TYPE_DISCRETE:
                    continue
                width, height = size.size.discrete.width, size.size.discrete.height
                for interval in self._each(FrmIvalEnum, ENUM_FRAMEINTERVALS, pixel_format=desc.pixelformat,
                                           width=width, height=height):
                    if interval.type == FRMIVAL_TYPE_DISCRETE:
                        found.append(Mode(width, height, _rate(interval.interval.discrete), name(desc.pixelformat)))
        return found

    def _interval(self, mode: Mode) -> Fract:
        for interval in self._each(FrmIvalEnum, ENUM_FRAMEINTERVALS, pixel_format=fourcc(mode.pixel_format),
                                   width=mode.width, height=mode.height):
            if interval.type == FRMIVAL_TYPE_DISCRETE and _rate(interval.interval.discrete) == mode.fps:
                return Fract(interval.interval.discrete.numerator, interval.interval.discrete.denominator)
        return Fract(1, mode.fps)

    def start(self, mode: Mode) -> None:
        """Sets *mode* (its size, pixel format and exact rate) and starts streaming into memory-mapped buffers."""
        form = Format(type=BUF_TYPE_VIDEO_CAPTURE)
        form.fmt.pix.width, form.fmt.pix.height = mode.width, mode.height
        form.fmt.pix.pixelformat, form.fmt.pix.field = fourcc(mode.pixel_format), FIELD_NONE
        self._ioctl(self.fd, S_FMT, form)
        parm = StreamParm(type=BUF_TYPE_VIDEO_CAPTURE)
        parm.parm.capture.timeperframe = self._interval(mode)
        self._ioctl(self.fd, S_PARM, parm)
        self.mode = Mode(form.fmt.pix.width, form.fmt.pix.height, mode.fps, name(form.fmt.pix.pixelformat))
        self.size = form.fmt.pix.sizeimage or mode.width * mode.height * 2
        request = RequestBuffers(count=BUFFERS, type=BUF_TYPE_VIDEO_CAPTURE, memory=MEMORY_MMAP)
        self._ioctl(self.fd, REQBUFS, request)
        for index in range(request.count):
            buffer = Buffer(index=index, type=BUF_TYPE_VIDEO_CAPTURE, memory=MEMORY_MMAP)
            self._ioctl(self.fd, QUERYBUF, buffer)
            self.buffers.append(self._map(self.fd, buffer.length, buffer.m.offset))
            self._ioctl(self.fd, QBUF, buffer)
        self._ioctl(self.fd, STREAMON, ctypes.c_int(BUF_TYPE_VIDEO_CAPTURE))
        self.streaming = True

    def read(self, timeout: float) -> Frame | None:
        """The next frame, or None when none came within *timeout* seconds."""
        if not self._wait(self.fd, timeout):
            return None
        buffer = Buffer(type=BUF_TYPE_VIDEO_CAPTURE, memory=MEMORY_MMAP)
        try:
            self._ioctl(self.fd, DQBUF, buffer)
        except BlockingIOError:
            return None
        # Read before the buffer goes back: queueing it again rewrites its flags and size.
        damaged = bool(buffer.flags & BUF_FLAG_ERROR) or buffer.bytesused < self.size
        data = bytes(self.buffers[buffer.index][:buffer.bytesused])
        self._ioctl(self.fd, QBUF, buffer)
        return Frame(data, damaged)

    def close(self) -> None:
        if self.streaming:
            try:
                self._ioctl(self.fd, STREAMOFF, ctypes.c_int(BUF_TYPE_VIDEO_CAPTURE))
            except OSError:
                pass
            self.streaming = False
        for buffer in self.buffers:
            try:
                buffer.close()
            except (BufferError, ValueError):
                pass
        self.buffers = []
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
