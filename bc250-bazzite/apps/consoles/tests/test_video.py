# SPDX-License-Identifier: AGPL-3.0-or-later
"""video.py: the planes of a picture, its color matrix and the slot between the stream and the view."""

from __future__ import annotations

import pytest

from consoles_link.video import (BT709, BT2020_NCL, SMPTE170M, UNSPECIFIED, Picture, PictureSlot, color_matrix,
                                      to_rgb)


def test_planes_of_both_formats():
    yuv = Picture("yuv420p", 4, 2, bytes(range(8)) + b"\x80\x81" + b"\x90\x91")
    assert [(p.width, p.height, p.channels, p.data) for p in yuv.planes()] == [
        (4, 2, 1, bytes(range(8))), (2, 1, 1, b"\x80\x81"), (2, 1, 1, b"\x90\x91")]
    nv12 = Picture("nv12", 4, 2, bytes(8) + b"\x80\x90\x81\x91")
    assert [(p.width, p.height, p.channels) for p in nv12.planes()] == [(4, 2, 1), (2, 1, 2)]
    odd = Picture("yuv420p", 3, 3, bytes(9 + 4 + 4))           # chroma rounds up: 2 × 2
    assert [(p.width, p.height) for p in odd.planes()] == [(3, 3), (2, 2), (2, 2)]


def test_wrong_sizes_and_formats_are_refused():
    with pytest.raises(ValueError, match="has 5 bytes"):
        Picture("yuv420p", 4, 2, bytes(5)).planes()
    ten_bit = Picture("yuv420p10le", 4, 2, bytes(24))
    assert not ten_bit.shown
    with pytest.raises(ValueError, match="not shown"):
        ten_bit.planes()


def test_matrix_follows_the_stream_or_the_size():
    assert Picture("nv12", 640, 480, b"", BT709).matrix_name == "bt709"
    assert Picture("nv12", 1920, 1080, b"", SMPTE170M).matrix_name == "bt601"
    assert Picture("nv12", 1920, 1080, b"", BT2020_NCL).matrix_name == "bt2020"
    assert Picture("nv12", 1280, 720, b"", UNSPECIFIED).matrix_name == "bt709"
    assert Picture("nv12", 720, 480, b"", UNSPECIFIED).matrix_name == "bt601"


@pytest.mark.parametrize("name", ["bt709", "bt601", "bt2020"])
def test_limited_range_black_white_and_grey(name):
    assert to_rgb(16, 128, 128, name) == (0, 0, 0)
    assert to_rgb(235, 128, 128, name) == (255, 255, 255)
    assert to_rgb(126, 128, 128, name) == (128, 128, 128)
    assert to_rgb(0, 128, 128, name, full_range=True) == (0, 0, 0)
    assert to_rgb(255, 128, 128, name, full_range=True) == (255, 255, 255)


def test_primaries_of_bt709():
    # The BT.709 limited-range codes of pure red, green and blue, rounded to 8 bits: within one step.
    for codes, rgb in (((63, 102, 240), (255, 0, 0)), ((173, 42, 26), (0, 255, 0)), ((32, 240, 118), (0, 0, 255))):
        assert all(abs(a - b) <= 1 for a, b in zip(to_rgb(*codes), rgb)), codes
    matrix, _offset = color_matrix("bt709", True)
    assert matrix[2] == pytest.approx(1.5748) and matrix[7] == pytest.approx(1.8556)


def test_slot_keeps_only_the_newest():
    slot = PictureSlot()
    first, second = Picture("nv12", 2, 2, bytes(6)), Picture("nv12", 2, 2, bytes(6))
    assert slot.wanted() and slot.put(first)
    assert not slot.wanted() and not slot.put(second)            # replaces: the view is told once
    assert slot.take() is second and slot.take() is None and slot.wanted()
    assert (slot.put_count, slot.replaced) == (2, 1)
