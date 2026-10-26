# SPDX-License-Identifier: GPL-3.0-or-later
# The layout, the writing and the curve tables follow dualsense-edge-profile-web-application (src/helper/,
# src/enum/ and src/components/), MIT, Copyright (c) 2023 steffalon; the MIT notice is in the README's License
# section.
"""The DualSense Edge's four profiles, read from the controller: feature reports 0x70 to 0x7B, three per profile,
in the order Fn + Triangle (the default profile), Square, Cross, Circle. The app reads them, keeps a backup, and
writes and clears Fn + Square, Cross and Circle; it never changes the default profile (owner, 23-10-2026).

A report's byte 1 is its part (0, 1, 2), or 0x10 for an empty slot. The name is UTF-16LE in part 0 from byte 6 and
part 1 from byte 2 to 27. Part 2 holds the triggers' ranges (bytes 4 to 7), the button map (bytes 10 to 25, one per
input: what it sends), the sticks' curves (bytes 30 and 32) and a CRC-32 of the three parts (bytes 56 to 59: parts
0 and 1 from byte 2 to 59, part 2 from 2 to 55). Measured on the owner's Edge (23-10-2026): the default profile
"Default Profile", full trigger ranges, every button its own, both sticks Default, CRC correct; the other slots
empty.

A profile is written as three reports with the slot's own ID (0x60 Square, 0x61 Cross, 0x62 Circle; 0x63 is the
default's), byte 1 the part and bytes 60 to 63 a CRC-32 of 0xA3 and the report's 64 bytes (the tail still zero), as
the web application sends them; report 0x68 clears a slot, byte 1 its place in read order (Square 2). Both work on
the owner's Edge (23-10-2026: written, read back byte for byte, cleared, the default profile unchanged). The stick
curves' points (part 1 bytes 44 to 59, part 2 bytes 2 and 3) follow the web application's tables. On Linux the
controller applies the button map and the curves itself (owner's Edge, 23-10-2026: Cross set to Circle sent Circle,
the left stick on Digital jumped to the edge), not the trigger ranges (R2 set to 0 to 50 % reported its whole
travel)."""

from __future__ import annotations

import json
import os
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

from .hidraw import Device

FIRST_REPORT = 0x70
SLOTS = ("Triangle", "Square", "Cross", "Circle")      # Fn + this button selects the profile
EMPTY = 0x10
CURVES = {0: "Default", 1: "Quick", 2: "Precise", 3: "Steady", 4: "Digital", 5: "Dynamic"}
INPUTS = ("Up", "Left", "Down", "Right", "Circle", "Cross", "Square", "Triangle", "R1", "R2", "R3", "L1", "L2", "L3",
          "Left back button", "Right back button")
OUTPUTS = {**dict(enumerate(INPUTS)), 0x10: "Options", 0x11: "Touchpad"}
WRITE_REPORTS = {"Square": 0x60, "Cross": 0x61, "Circle": 0x62}    # Fn + Triangle, the default, is never written
CLEAR = 0x68
NAME_BYTES = 78                     # 39 UTF-16 code units: the name's 80 bytes always end in a zero
SENSITIVITY_LEVELS = 11             # 0 to 10, as on a PS5
DEFAULT_LEVEL = 5


class ProfileError(Exception):
    pass


# Each curve's six points by sensitivity level (0 to 10) and its modifier byte, from the web application's tables
# (src/helper/bytesToProfile.ts): a point is its start value plus its steps, a step per level (a pair of steps
# alternates).
_CURVE_POINTS: dict[int, tuple[tuple[tuple[int, tuple[int, ...]], ...], int]] = {
    0: (((128, ()), (128, ()), (196, ()), (196, ()), (225, ()), (225, ())), 0x03),
    1: (((38, ()), (38, ()), (122, (-3,)), (139, (6, 5)), (255, ()), (255, ())), 0x03),
    2: (((70, (3,)), (57, (-3, -4)), (134, (3,)), (115, (-6, -7)), (196, (2,)), (177, (-7, -8))), 0x04),
    3: (((62, (-1,)), (62, (-1,)), (120, (-4,)), (129, (0, -1)), (197, (3, 2)), (179, (-5, -6))), 0x04),
    4: (((38, ()), (38, ()), (38, ()), (75, (18,)), (255, ()), (255, ())), 0x03),
    5: (((69, (3, 2)), (57, (-3, -4)), (183, (-4, -5)), (198, (3,)), (255, ()), (255, ())), 0x03),
}


def curve_points(curve: int, level: int) -> bytes:
    points, _modifier = _CURVE_POINTS[curve]
    return bytes(start + sum(steps[i % len(steps)] for i in range(level)) if steps else start
                 for start, steps in points)


def curve_level(curve: int, points: bytes) -> int | None:
    """The sensitivity level whose points these are, or None (a profile made elsewhere, or the default's zeros)."""
    if curve not in _CURVE_POINTS:
        return None
    return next((level for level in range(SENSITIVITY_LEVELS) if curve_points(curve, level) == points), None)


@dataclass(frozen=True)
class Profile:
    slot: str                       # SLOTS
    reports: tuple[bytes, bytes, bytes]
    empty: bool
    name: str = ""
    left_curve: str = ""
    right_curve: str = ""
    triggers: tuple[int, int, int, int] = (0, 255, 0, 255)  # L2 start, end, R2 start, end (0 to 255)
    remapped: tuple[tuple[str, str], ...] = ()               # (input, what it sends), only those not its own
    crc_ok: bool = True

    @property
    def label(self) -> str:
        return f"Fn + {self.slot}"


def checksum(reports: tuple[bytes, bytes, bytes]) -> int:
    return zlib.crc32(reports[0][2:60] + reports[1][2:60] + reports[2][2:56])


def _name(reports: tuple[bytes, bytes, bytes]) -> str:
    raw = reports[0][6:60] + reports[1][2:28]
    text = raw.decode("utf-16-le", "replace")
    return "".join(text.split("\0")).strip()


def parse(slot: str, reports: tuple[bytes, bytes, bytes]) -> Profile:
    if any(len(report) < 64 for report in reports):
        raise ValueError(f"the reports of profile Fn + {slot} are too short")
    if reports[0][1] == EMPTY:
        return Profile(slot, reports, True)
    third = reports[2]
    remapped = tuple((INPUTS[i], OUTPUTS.get(value, f"0x{value:02x}")) for i, value in enumerate(third[10:26])
                     if value != i)
    curve = lambda value: CURVES.get(value, f"0x{value:02x}")  # noqa: E731
    return Profile(slot, reports, False, _name(reports), curve(third[30]), curve(third[32]),
                   (third[4], third[5], third[6], third[7]), remapped,
                   checksum(reports) == int.from_bytes(third[56:60], "little"))


def read(device: Device) -> list[Profile]:
    profiles = []
    for index, slot in enumerate(SLOTS):
        first = FIRST_REPORT + 3 * index
        reports = tuple(device.get_feature(first + part)[:64].ljust(64, b"\0") for part in range(3))
        profiles.append(parse(slot, reports))
    return profiles


def _left_points(reports: tuple[bytes, bytes, bytes]) -> bytes:
    return reports[1][47:53]


def _right_points(reports: tuple[bytes, bytes, bytes]) -> bytes:
    return reports[1][56:60] + reports[2][2:4]


@dataclass(frozen=True)
class Settings:
    """What the editor changes. A level of None keeps the curve's points as they are."""
    name: str
    left_curve: int
    left_level: int | None
    right_curve: int
    right_level: int | None
    triggers: tuple[int, int, int, int]
    buttons: tuple[int, ...]        # 16, in INPUTS' order: what each input sends


def settings_of(profile: Profile) -> Settings:
    third = profile.reports[2]
    return Settings(profile.name, third[30], curve_level(third[30], _left_points(profile.reports)),
                    third[32], curve_level(third[32], _right_points(profile.reports)), profile.triggers,
                    tuple(third[10:26]))


def name_fits(name: str) -> bool:
    return len(name.encode("utf-16-le")) <= NAME_BYTES


def build(settings: Settings, base: tuple[bytes, bytes, bytes], new_id: bytes | None = None) -> tuple[bytes, ...]:
    """The three parts of a profile: *base*'s bytes (a new profile starts from the default's) with the settings put
    in, and its CRC; the bytes the app does not know stay as the controller made them. *new_id* is the 16-byte ID a
    new profile gets."""
    if not settings.name.strip() or not name_fits(settings.name):
        raise ProfileError("the name must have 1 to 39 characters")
    start_l2, end_l2, start_r2, end_r2 = settings.triggers
    if not (0 <= start_l2 < end_l2 <= 255 and 0 <= start_r2 < end_r2 <= 255):
        raise ProfileError("a trigger's range must start before it ends")
    if len(settings.buttons) != len(INPUTS) or any(value not in OUTPUTS for value in settings.buttons):
        raise ProfileError("the button map is not complete")
    parts = [bytearray(report[:64].ljust(64, b"\0")) for report in base]
    for index, part in enumerate(parts):
        part[1] = index
        part[60:64] = bytes(4)
    area = settings.name.encode("utf-16-le").ljust(54 + 26, b"\0")
    parts[0][6:60], parts[1][2:28] = area[:54], area[54:]
    if new_id is not None:
        parts[1][28:44] = new_id
    third = parts[2]
    third[30], third[32] = settings.left_curve, settings.right_curve
    if settings.left_level is not None:
        parts[1][44] = _CURVE_POINTS[settings.left_curve][1]
        parts[1][47:53] = curve_points(settings.left_curve, settings.left_level)
    if settings.right_level is not None:
        parts[1][53] = _CURVE_POINTS[settings.right_curve][1]
        points = curve_points(settings.right_curve, settings.right_level)
        parts[1][56:60], third[2:4] = points[:4], points[4:]
    third[4:8] = bytes(settings.triggers)
    third[10:26] = bytes(settings.buttons)
    third[56:60] = checksum(tuple(bytes(part) for part in parts)).to_bytes(4, "little")
    return tuple(bytes(part) for part in parts)


def new_id() -> bytes:
    return os.urandom(16)


def framed(slot: str, parts: tuple[bytes, ...]) -> list[bytes]:
    """The reports that write *parts* to *slot*: its report ID and each report's own CRC."""
    out = []
    for part in parts:
        report = bytearray(part)
        report[0] = WRITE_REPORTS[slot]
        report[60:64] = zlib.crc32(b"\xa3" + bytes(report[:60]) + bytes(4)).to_bytes(4, "little")
        out.append(bytes(report))
    return out


def _slot(slot: str) -> int:
    if slot not in WRITE_REPORTS:
        raise ProfileError(f"Fn + {slot} is the default profile; the app does not change it")
    return SLOTS.index(slot)


def write(device: Device, slot: str, parts: tuple[bytes, ...], wait: float = 0.3) -> Profile:
    """Writes *parts* to *slot* and reads it back: the profile as the controller now holds it."""
    index = _slot(slot)
    for report in framed(slot, parts):
        device.set_feature(report)
    time.sleep(wait)
    written = read(device)[index]
    if written.empty or [report[1:60] for report in written.reports] != [part[1:60] for part in parts]:
        raise ProfileError(f"the controller did not keep the profile in Fn + {slot}")
    return written


def clear(device: Device, slot: str, wait: float = 0.3) -> None:
    index = _slot(slot)
    device.set_feature(bytes([CLEAR, index + 1]) + bytes(62))
    time.sleep(wait)
    if not read(device)[index].empty:
        raise ProfileError(f"the controller still holds a profile in Fn + {slot}")


# The drawing's part (drawing.PARTS) for each input of the button map.
INPUT_PARTS = {"Up": "dpad", "Left": "dpad", "Down": "dpad", "Right": "dpad", "Circle": "face", "Cross": "face",
               "Square": "face", "Triangle": "face", "R1": "bumpers", "L1": "bumpers", "R2": "triggers",
               "L2": "triggers", "R3": "sticks", "L3": "sticks", "Left back button": "back",
               "Right back button": "back"}
FULL_RANGE = (0, 255, 0, 255)


def changed_parts(profile: Profile) -> set[str]:
    """The parts of the controller a profile sets apart from their defaults, for the drawing to light: the sticks
    for another curve, the triggers for a shorter range, and each remapped input."""
    if profile.empty:
        return set()
    parts = {INPUT_PARTS[source] for source, _target in profile.remapped}
    if (profile.left_curve, profile.right_curve) != ("Default", "Default"):
        parts.add("sticks")
    if profile.triggers != FULL_RANGE:
        parts.add("triggers")
    return parts


def trigger_text(start: int, end: int) -> str:
    return f"{round(start * 100 / 255)} to {round(end * 100 / 255)} %"


def folder(home: Path | None = None) -> Path:
    from .firmware import folder as firmware_folder
    return firmware_folder(home).parent / "profiles"


def backup(profiles: list[Profile], target: Path, model: str, firmware: str) -> Path:
    """The profiles' reports as they came from the controller, in JSON: enough to compare, or to write them back."""
    data = {"app": "bc250-usb-hdcontrol", "controller": model, "firmware": firmware,
            "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
            "profiles": [{"slot": p.label, "name": p.name, "empty": p.empty,
                          "reports": {f"0x{p.reports[i][0]:02x}": p.reports[i].hex() for i in range(3)}}
                         for p in profiles]}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n")
    return target


def backup_path(home: Path | None = None, now: float | None = None) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    return folder(home) / f"profiles-{stamp}.json"
