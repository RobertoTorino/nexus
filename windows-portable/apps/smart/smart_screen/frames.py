# SPDX-License-Identifier: GPL-3.0-or-later
"""Which parts of the screen changed between two frames. At about 166 KB/s a whole 3.5" screen takes almost two
seconds, so the app sends only the rectangles that changed: once a second that is a few values, a few KB."""

from __future__ import annotations

ROW_GAP = 8                     # changed rows closer than this go in one rectangle: a command costs more than a row


def _row_span(old: bytes, new: bytes) -> tuple[int, int]:
    """The first and one past the last pixel that differ in two rows of RGB565 that are not equal."""
    first = 0
    while old[first:first + 2] == new[first:first + 2]:
        first += 2
    last = len(new)
    while old[last - 2:last] == new[last - 2:last]:
        last -= 2
    return first // 2, last // 2


def changed(old: bytes | None, new: bytes, width: int, height: int) -> list[tuple[int, int, int, int]]:
    """Rectangles (x, y, width, height) that cover every pixel that differs; the whole screen without *old*."""
    if old is None or len(old) != len(new):
        return [(0, 0, width, height)]
    line = width * 2
    rects: list[tuple[int, int, int, int]] = []
    top = bottom = left = right = None           # the rectangle being built: rows top..bottom, pixels left..right
    for y in range(height):
        start = y * line
        a, b = old[start:start + line], new[start:start + line]
        if a == b:
            continue
        x0, x1 = _row_span(a, b)
        if top is not None and y - bottom <= ROW_GAP:
            bottom, left, right = y, min(left, x0), max(right, x1)
            continue
        if top is not None:
            rects.append((left, top, right - left, bottom - top + 1))
        top = bottom = y
        left, right = x0, x1
    if top is not None:
        rects.append((left, top, right - left, bottom - top + 1))
    return rects

