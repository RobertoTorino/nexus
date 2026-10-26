# SPDX-License-Identifier: GPL-3.0-or-later
"""The picture after the TV was off: KDE's display settings for the CEC adapter's output, through kscreen-doctor.

Behind a DP-to-HDMI converter the board never learns that the TV went to standby: the converter keeps the
DisplayPort side up. Above 340 MHz on the HDMI side (for example 1080p120 at 10 or 12 bits per color) HDMI 2.0
needs scrambling, which the converter must set up with the TV again when it comes back. Some converters do not, and
the TV stays black although it is on (the owner's UGreen cable, 11-10-2026). Two ways around it:
 * 8 bits per color: 1080p120 then needs 297 MHz, below the limit, and the picture comes back by itself. Larger
   modes (1440p120, 4K60) stay above it even at 8 bits: there only the next one helps;
 * a different signal once the TV is on again (another refresh rate and back): the converter has to handshake anew.
Nothing here needs root; kscreen-doctor talks to the running KDE session (not to gamescope's Game Mode)."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from typing import Callable

from .runner import Result

KSCREEN = "kscreen-doctor"
AUTOMATIC = 0                           # kscreen's maxBpc for "automatic"
HANDSHAKE_MHZ = 340                     # above this HDMI 2.0 scrambles: the handshake a converter may forget
BLANKING = 1.19                         # CTA-861 timings: all pixels / visible ones (2200 x 1125 for 1920 x 1080)

Runner = Callable[[list[str]], Result]


@dataclass(frozen=True)
class Mode:
    id: str
    width: int
    height: int
    rate: float


@dataclass(frozen=True)
class Output:
    name: str                           # DP-1
    enabled: bool
    max_bpc: int                        # 0: automatic
    hdr: bool
    current: str                        # the current mode's id
    modes: tuple[Mode, ...]

    @property
    def mode(self) -> Mode | None:
        return next((m for m in self.modes if m.id == self.current), None)


def available() -> bool:
    return shutil.which(KSCREEN) is not None


def parse(text: str) -> dict[str, Output]:
    """kscreen-doctor -j: the outputs by name."""
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    outputs = {}
    for o in data.get("outputs", []) if isinstance(data, dict) else []:
        modes = tuple(Mode(str(m["id"]), int(m["size"]["width"]), int(m["size"]["height"]), float(m["refreshRate"]))
                      for m in o.get("modes", []))
        outputs[o["name"]] = Output(o["name"], bool(o.get("enabled")), int(o.get("maxBpc") or 0),
                                    bool(o.get("hdr")), str(o.get("currentModeId", "")), modes)
    return outputs


def read(run: Runner) -> dict[str, Output]:
    result = run([KSCREEN, "-j"])
    return parse(result.out) if result.ok else {}


def other_rate(output: Output) -> Mode | None:
    """The mode to switch to for a moment: the same size at another refresh rate, 60 Hz if possible (50 Hz when
    the current one is 60 Hz)."""
    now = output.mode
    if now is None:
        return None
    same = [m for m in output.modes if (m.width, m.height) == (now.width, now.height) and abs(m.rate - now.rate) > 1]
    if not same:
        return None
    target = 50.0 if abs(now.rate - 60) < 1 else 60.0
    return min(same, key=lambda m: (abs(m.rate - target), m.id))


def clock_mhz(mode: Mode, bits: int = 8) -> float:
    """An estimate of the HDMI signal's speed (TMDS character rate) for *mode* at *bits* per color: 1080p120 at 8
    bits is 297 MHz. kscreen-doctor does not report the real timings; CTA's are the widest common ones."""
    return mode.width * mode.height * mode.rate * BLANKING * bits / 8 / 1e6


def handshake(mode: Mode) -> str:
    """Whether *mode* needs the handshake: "never" (not even at 12 bits), "above 8 bits" or "always"."""
    if clock_mhz(mode, 12) <= HANDSHAKE_MHZ:
        return "never"
    return "above 8 bits" if clock_mhz(mode, 8) <= HANDSHAKE_MHZ else "always"


def describe(mode: Mode) -> str:
    """ "1920 × 1080 at 120 Hz" """
    return f"{mode.width} × {mode.height} at {mode.rate:g} Hz"


def set_max_bpc(output: str, bits: int) -> list[str]:
    return [KSCREEN, f"output.{output}.maxbpc.{bits if bits else 'automatic'}"]


def set_mode(output: str, mode_id: str) -> list[str]:
    return [KSCREEN, f"output.{output}.mode.{mode_id}"]
