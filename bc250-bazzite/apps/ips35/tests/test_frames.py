# SPDX-License-Identifier: GPL-3.0-or-later
"""The rectangles that cover what changed between two frames."""

from __future__ import annotations

from usb_ips35 import frames

W, H = 10, 40


def frame(*pixels: tuple[int, int]) -> bytes:
    """A black frame with white pixels at (x, y)."""
    data = bytearray(W * H * 2)
    for x, y in pixels:
        data[(y * W + x) * 2:(y * W + x) * 2 + 2] = b"\xff\xff"
    return bytes(data)


def test_everything_without_a_previous_frame():
    assert frames.changed(None, frame(), W, H) == [(0, 0, W, H)]
    assert frames.changed(b"short", frame(), W, H) == [(0, 0, W, H)]


def test_nothing_when_equal():
    assert frames.changed(frame((3, 3)), frame((3, 3)), W, H) == []


def test_one_pixel():
    assert frames.changed(frame(), frame((3, 5)), W, H) == [(3, 5, 1, 1)]
    assert frames.changed(frame((9, 39)), frame(), W, H) == [(9, 39, 1, 1)]


def test_near_rows_share_a_rectangle():
    assert frames.changed(frame(), frame((2, 5), (7, 5 + frames.ROW_GAP)), W, H) == [(2, 5, 6, frames.ROW_GAP + 1)]


def test_far_rows_get_their_own():
    far = 5 + frames.ROW_GAP + 1
    assert frames.changed(frame(), frame((2, 5), (7, far)), W, H) == [(2, 5, 1, 1), (7, far, 1, 1)]


def test_the_rectangles_cover_every_change():
    old, new = frame((0, 0), (4, 12), (9, 30)), frame((1, 0), (4, 13), (8, 39))
    covered = set()
    for x, y, w, h in frames.changed(old, new, W, H):
        covered |= {(cx, cy) for cx in range(x, x + w) for cy in range(y, y + h)}
    line = W * 2
    diff = {(x, y) for y in range(H) for x in range(W)
            if old[y * line + x * 2:y * line + x * 2 + 2] != new[y * line + x * 2:y * line + x * 2 + 2]}
    assert diff <= covered
