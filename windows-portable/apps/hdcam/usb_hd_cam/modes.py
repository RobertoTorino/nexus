# SPDX-License-Identifier: GPL-3.0-or-later
"""The camera's video modes, as the Picture card offers them. It has two image sensors and reports two kinds of mode:
one sensor's picture (1920 x 1080, 1280 x 800, ...) and both side by side in one frame (3840 x 1080, 2560 x 800,
...), for depth; 5148 x 1088 is both and smaller copies of them. A mode that gives no picture is left out: every
1080-line mode at 15 fps (the camera sends nothing, as on the BC-250), and with reduced bandwidth the three largest
side-by-side modes (measured on the owner's ROG Xbox Ally X, 31-10-2026). Each size is offered once, at its fastest
rate that gives a picture: LB and RB go through a dozen modes, not two dozen, and Qt's camera backend ran
1920 x 1080 at 8 fps at 30 anyway (01-11-2026)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

STEREO_RATIO = 2.5                          # one sensor is 16:9 or 16:10; two side by side are 3.2:1 or wider
SILENT = {(1920, 1080, 15), (3840, 1080, 15), (5148, 1088, 15)}
TOO_MUCH_FOR_REDUCED = {(2560, 800, 60), (3840, 1080, 30), (5148, 1088, 30)}


@dataclass(frozen=True)
class Mode:
    width: int
    height: int
    fps: int

    @property
    def key(self) -> str:
        return f"{self.width}x{self.height}@{self.fps}"

    @property
    def stereo(self) -> bool:
        return self.height > 0 and self.width / self.height > STEREO_RATIO

    @property
    def kind(self) -> str:
        if self.width == 5148:
            return "both cameras and smaller copies"
        return "both cameras" if self.stereo else "one camera"

    @property
    def label(self) -> str:
        return f"{self.width} × {self.height}, {self.fps} fps ({self.kind})"


def offered(found: Iterable[Mode], bandwidth: str) -> list[Mode]:
    """The modes that give a picture at *bandwidth* ("full" or "reduced"), each size at its fastest such rate: one
    camera first, then both; each by size, the largest first."""
    fastest: dict[tuple[int, int], Mode] = {}
    for mode in found:
        if (mode.width, mode.height, mode.fps) in SILENT or (
                bandwidth == "reduced" and (mode.width, mode.height, mode.fps) in TOO_MUCH_FOR_REDUCED):
            continue
        size = (mode.width, mode.height)
        if size not in fastest or mode.fps > fastest[size].fps:
            fastest[size] = mode
    return sorted(fastest.values(), key=lambda m: (m.stereo, -m.width * m.height))


def chosen(listed: list[Mode], key: str) -> Mode | None:
    """The mode with *key*, else the first: the largest one-camera picture at its fastest rate, a webcam's."""
    return next((mode for mode in listed if mode.key == key), listed[0] if listed else None)
