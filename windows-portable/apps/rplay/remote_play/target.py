# SPDX-License-Identifier: AGPL-3.0-only
"""Which console and which Remote Play version a request is for. The numbers are the reference's: they decide the
request paths, the RP-Version header and the key tables."""

from __future__ import annotations

from enum import IntEnum


class Target(IntEnum):
    PS4_UNKNOWN = 0
    PS4_8 = 800
    PS4_9 = 900
    PS4_10 = 1000
    PS5_UNKNOWN = 1000000
    PS5_1 = 1000100

    @property
    def ps5(self) -> bool:
        return self >= Target.PS5_UNKNOWN

    @property
    def unknown(self) -> bool:
        return self in (Target.PS4_UNKNOWN, Target.PS5_UNKNOWN)

    @property
    def pre10(self) -> bool:
        """PS4 system software before 7.0: older paths and the older registration crypto."""
        return self < Target.PS4_10

    @property
    def console(self) -> str:
        return "PS5" if self.ps5 else "PS4"


RP_VERSIONS = {Target.PS4_8: "8.0", Target.PS4_9: "9.0", Target.PS4_10: "10.0", Target.PS5_1: "1.0"}

# RP-Application-Reason values the console sends with a refusal.
REASONS = {
    0x80108b09: "Registration failed, probably a wrong PIN",
    0x80108b02: "Invalid PSN account",
    0x80108b10: "Remote Play is already in use",
    0x80108b15: "Remote Play on the console crashed",
    0x80108b11: "Remote Play version mismatch",
}
REASON_RP_VERSION = 0x80108b11
REASON_UNKNOWN = 0x80108bff


def rp_version(target: Target) -> str | None:
    return RP_VERSIONS.get(target)


def parse_rp_version(text: str, ps5: bool) -> Target:
    if ps5:
        return Target.PS5_1 if text == "1.0" else Target.PS5_UNKNOWN
    return {"8.0": Target.PS4_8, "9.0": Target.PS4_9, "10.0": Target.PS4_10}.get(text, Target.PS4_UNKNOWN)


def software_version(system_version: str, ps5: bool) -> str:
    """A PS4's system software version from the system-version it reports in discovery: "14008001" is 14.00 (the
    owner's PS4 Pro on 14.00, 13-10-2026: major, minor, then 8001). A PS5 reports a Remote Play generation there
    ("08050001"), not its software version: "" for it, and for anything else that is not 8 digits."""
    if ps5 or len(system_version) != 8 or not system_version.isdigit():
        return ""
    return f"{int(system_version[:2])}.{system_version[2:4]}"


def from_system_version(system_version: str, ps5: bool) -> Target:
    """The target that goes with the system-version a console reports in discovery ("08050001": PS5 1.0)."""
    try:
        version = int(system_version)
    except ValueError:
        version = 0
    if ps5 and version >= 8050001:
        return Target.PS5_1
    if ps5 and version >= 8050000:
        return Target.PS5_UNKNOWN
    if version >= 8000000:
        return Target.PS4_10
    if version >= 7000000:
        return Target.PS4_9
    if version > 0:
        return Target.PS4_8
    return Target.PS4_UNKNOWN


def reason_text(code: int) -> str:
    return REASONS.get(code, "unknown reason")
