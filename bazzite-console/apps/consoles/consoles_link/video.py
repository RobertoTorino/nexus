# SPDX-License-Identifier: AGPL-3.0-or-later
"""The decoded pictures as the view shows them: their planes and the color matrix that turns Y'CbCr into RGB.
Without Qt, so the arithmetic is tested on its own; the view (stream_view.py) uploads the planes as textures and
applies the matrix in a shader.

A picture comes from the native decoder: yuv420p in software (three planes: Y at full size, Cb and Cr at half the
width and height), nv12 from VA-API (Y, then Cb and Cr interleaved at half size). Its color matrix is the one the
stream names (BT.709, BT.601 or BT.2020); a stream that names none gets BT.709 from 720 lines up and BT.601 below,
as FFmpeg's players assume. Limited range (16 to 235 for Y, 16 to 240 for Cb and Cr) unless it says full range."""

from __future__ import annotations

import threading
from time import perf_counter
from dataclasses import dataclass, field

# FFmpeg's AVColorSpace numbers.
BT709, UNSPECIFIED, BT470BG, SMPTE170M, BT2020_NCL, BT2020_CL = 1, 2, 5, 6, 9, 10
KR_KB = {"bt709": (0.2126, 0.0722), "bt601": (0.299, 0.114), "bt2020": (0.2627, 0.0593)}
FORMATS = ("yuv420p", "nv12")


@dataclass(frozen=True)
class Plane:
    width: int
    height: int
    channels: int                       # 1, or 2 for nv12's interleaved Cb and Cr
    data: bytes


@dataclass(frozen=True)
class Picture:
    format: str
    width: int
    height: int
    data: bytes
    colorspace: int = UNSPECIFIED
    full_range: bool = False
    made: float = field(default=0.0, compare=False)    # perf_counter() when it came out of the decoder

    @classmethod
    def from_image(cls, image: dict) -> Picture:
        """From the native decoder's image()."""
        return cls(image["format"], image["width"], image["height"], image["data"], image["colorspace"],
                   image["full_range"], perf_counter())

    @property
    def shown(self) -> bool:
        return self.format in FORMATS

    def planes(self) -> list[Plane]:
        """The planes in the order the shader takes them: Y, then Cb and Cr (yuv420p) or CbCr (nv12)."""
        if not self.shown:
            raise ValueError(f"pictures in {self.format} are not shown")
        w, h = self.width, self.height
        cw, ch = (w + 1) // 2, (h + 1) // 2
        y = w * h
        if self.format == "yuv420p":
            sizes = [(w, h, 1, y), (cw, ch, 1, cw * ch), (cw, ch, 1, cw * ch)]
        else:
            sizes = [(w, h, 1, y), (cw, ch, 2, cw * ch * 2)]
        if sum(size for *_, size in sizes) != len(self.data):
            raise ValueError(f"a {w}×{h} {self.format} picture has {len(self.data)} bytes")
        planes, at = [], 0
        for pw, ph, channels, size in sizes:
            planes.append(Plane(pw, ph, channels, self.data[at:at + size]))
            at += size
        return planes

    @property
    def matrix_name(self) -> str:
        if self.colorspace == BT709:
            return "bt709"
        if self.colorspace in (BT470BG, SMPTE170M):
            return "bt601"
        if self.colorspace in (BT2020_NCL, BT2020_CL):
            return "bt2020"
        return "bt709" if self.height >= 720 else "bt601"


def color_matrix(name: str, full_range: bool) -> tuple[list[float], list[float]]:
    """RGB = M × (Y', Cb, Cr) + offset, with Y', Cb and Cr as stored (0 to 1): M row by row (3 × 3) and the
    offset. The range scaling is folded in, so the shader does one multiply and one add."""
    kr, kb = KR_KB[name]
    kg = 1.0 - kr - kb
    rows = [(1.0, 0.0, 2.0 * (1.0 - kr)),
            (1.0, -2.0 * kb * (1.0 - kb) / kg, -2.0 * kr * (1.0 - kr) / kg),
            (1.0, 2.0 * (1.0 - kb), 0.0)]
    if full_range:
        y_scale, c_scale, y_zero = 1.0, 1.0, 0.0
    else:
        y_scale, c_scale, y_zero = 255.0 / 219.0, 255.0 / 224.0, 16.0 / 255.0
    c_zero = 128.0 / 255.0
    matrix, offset = [], []
    for ry, rcb, rcr in rows:
        my, mcb, mcr = ry * y_scale, rcb * c_scale, rcr * c_scale
        matrix += [my, mcb, mcr]
        offset.append(-(my * y_zero + mcb * c_zero + mcr * c_zero))
    return matrix, offset


def to_rgb(y: int, cb: int, cr: int, name: str = "bt709", full_range: bool = False) -> tuple[int, int, int]:
    """One pixel, as the shader computes it (8-bit values in and out, clamped): the tests' reference."""
    matrix, offset = color_matrix(name, full_range)
    yuv = (y / 255.0, cb / 255.0, cr / 255.0)
    rgb = []
    for row in range(3):
        value = sum(matrix[row * 3 + i] * yuv[i] for i in range(3)) + offset[row]
        rgb.append(round(min(max(value, 0.0), 1.0) * 255.0))
    return rgb[0], rgb[1], rgb[2]


class PictureSlot:
    """The newest picture, handed from the stream's thread to the view: put() replaces what the view has not taken
    yet (an older picture is never worth showing late), take() empties it. wanted() lets the stream skip copying a
    picture out of the decoder while the view has not taken the last one."""

    def __init__(self):
        self._lock = threading.Lock()
        self._picture: Picture | None = None
        self.put_count = 0
        self.replaced = 0

    def wanted(self) -> bool:
        with self._lock:
            return self._picture is None

    def put(self, picture: Picture) -> bool:
        """True when the slot was empty (the view should be told)."""
        with self._lock:
            empty = self._picture is None
            self.replaced += not empty
            self._picture = picture
            self.put_count += 1
            return empty

    def take(self) -> Picture | None:
        with self._lock:
            picture, self._picture = self._picture, None
            return picture
