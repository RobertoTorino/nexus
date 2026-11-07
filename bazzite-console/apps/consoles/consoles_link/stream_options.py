# SPDX-License-Identifier: AGPL-3.0-or-later
"""A console's stream settings (owner, 13-10-2026: per console, in a dialog): what the stream asks the console for
(resolution, frame rate, bitrate) and how the board plays it (audio delay, low latency, the picture's fit on the
screen). Kept with the console in consoles.json, so the Game Mode shortcut streams with them too.

Automatic is the reference's presets: 1080p at 15 Mbit/s from a PS5 or a PS4 Pro, 720p at 10 Mbit/s from a PS4.
A PS4 that is not a Pro streams at most 720p, whatever is chosen."""

from __future__ import annotations

from dataclasses import asdict, dataclass

AUTO = 0
RESOLUTIONS = (360, 540, 720, 1080)             # heights; the width is 16:9
FRAME_RATES = (30, 60)
BITRATES = {360: 2000, 540: 6000, 720: 10000, 1080: 15000}     # the reference's presets, kbit/s
BITRATE_RANGE = (1000, 50000)                   # kbit/s, by hand
AUDIO_DELAY_MAX = 500                           # ms
SCREENS = {"fit": "Fit: the whole picture, black bars where the shape differs",
           "stretch": "Stretch: the whole screen, the picture distorted to fill it",
           "fill": "Fill: the whole screen, the picture's edges cut off"}
PS4_MAX = 720                                   # a PS4 that is not a Pro


@dataclass(frozen=True)
class StreamOptions:
    resolution: int = AUTO                      # a height of RESOLUTIONS, or AUTO
    fps: int = 60
    bitrate: int = AUTO                         # kbit/s, or AUTO (the preset of the resolution)
    audio_delay: int = 0                        # ms the sound plays later than it comes, to meet a late picture
    low_latency: bool = False                   # a shorter sound buffer and the decoder's low-delay mode
    screen: str = "fit"

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: object) -> StreamOptions:
        """From consoles.json; what is missing or not valid stays at its default."""
        if not isinstance(data, dict):
            return cls()
        default = cls()

        def pick(name: str, valid) -> object:
            value = data.get(name, getattr(default, name))
            return value if valid(value) else getattr(default, name)
        return cls(
            resolution=pick("resolution", lambda v: v == AUTO or v in RESOLUTIONS),
            fps=pick("fps", lambda v: v in FRAME_RATES),
            bitrate=pick("bitrate", lambda v: v == AUTO or (isinstance(v, int) and
                                                           BITRATE_RANGE[0] <= v <= BITRATE_RANGE[1])),
            audio_delay=pick("audio_delay", lambda v: isinstance(v, int) and 0 <= v <= AUDIO_DELAY_MAX),
            low_latency=pick("low_latency", lambda v: isinstance(v, bool)),
            screen=pick("screen", lambda v: v in SCREENS),
        )

    def height(self, ps5: bool, server_type: str = "") -> int:
        """The resolution asked for: the chosen one, or the preset; at most 720p from a PS4 that is not a Pro."""
        strong = ps5 or server_type == "PS4 Pro"
        if self.resolution == AUTO:
            return 1080 if strong else 720
        return self.resolution if strong else min(self.resolution, PS4_MAX)

    def kbps(self, height: int) -> int:
        return self.bitrate if self.bitrate != AUTO else BITRATES[height]

    def describe(self, ps5: bool, server_type: str = "") -> str:
        """For the log and the statistics file: "1080p, 60 fps, 15 Mbit/s (automatic), fit"."""
        height = self.height(ps5, server_type)
        parts = [f"{height}p" + (" (automatic)" if self.resolution == AUTO else ""), f"{self.fps} fps",
                 f"{self.kbps(height) / 1000:g} Mbit/s" + (" (automatic)" if self.bitrate == AUTO else ""),
                 self.screen]
        if self.audio_delay:
            parts.append(f"sound {self.audio_delay} ms later")
        if self.low_latency:
            parts.append("low latency")
        return ", ".join(parts)


def width(height: int) -> int:
    """16:9, as the console streams: 360 -> 640, 540 -> 960, 720 -> 1280, 1080 -> 1920."""
    return height * 16 // 9
