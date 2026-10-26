# SPDX-License-Identifier: GPL-3.0-or-later
"""The camera's video modes. It has two image sensors and reports two kinds of mode: one sensor's picture (1920×1080,
1280×800, …) and both side by side in one frame (3840×1080, 2560×800, …), for depth. Every mode it reports is
offered; a side-by-side frame can be shown whole or as either half."""

from __future__ import annotations

from dataclasses import dataclass

STEREO_RATIO = 2.5                          # one sensor is 16:9 or 16:10; two side by side are 3.2:1 or wider


@dataclass(frozen=True)
class Mode:
    width: int
    height: int
    fps: int
    pixel_format: str = ""

    @property
    def key(self) -> str:
        return f"{self.width}x{self.height}@{self.fps}"

    @property
    def stereo(self) -> bool:
        return self.height > 0 and self.width / self.height > STEREO_RATIO

    @property
    def label(self) -> str:
        kind = "both cameras" if self.stereo else "one camera"
        return f"{self.width} × {self.height}, {self.fps} fps ({kind})"


def ordered(modes: list[Mode]) -> list[Mode]:
    """One camera first, then both; each by size, the largest and fastest first; no duplicates."""
    unique = {mode.key: mode for mode in modes}
    return sorted(unique.values(), key=lambda m: (m.stereo, -m.width * m.height, -m.fps))


def default(modes: list[Mode]) -> Mode | None:
    """The largest one-camera picture at its fastest rate: a webcam's picture."""
    listed = ordered(modes)
    return listed[0] if listed else None


def chosen(modes: list[Mode], key: str) -> Mode | None:
    for mode in modes:
        if mode.key == key:
            return mode
    return default(modes)


def crop(width: int, height: int, view: str) -> tuple[int, int, int, int]:
    """(x, y, width, height) of what *view* shows of a frame: "both" the whole frame, "left" or "right" a half."""
    if view == "left":
        return 0, 0, width // 2, height
    if view == "right":
        return width // 2, 0, width - width // 2, height
    return 0, 0, width, height
