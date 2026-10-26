# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading the BIOS flash chip with flashrom: finding a flashrom that can reach the board's own chip, the command
that reads it twice through polkit (pkexec), and checking that both reads are the same.

flashrom only ever runs with -r (read). The app never passes -w, -E or -v."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

CHIP = "W25Q128.V"                      # the BC-250's BIOS chip (Winbond, 16 MiB)
CHIP_SIZE = 16 * 1024 * 1024

# Reads the chip twice and hands both files to the user. $1 flashrom, $2/$3 the two files, $4 uid:gid, $5 chip.
READ_SCRIPT = ('set -e; "$1" -p internal -c "$5" -r "$2"; "$1" -p internal -c "$5" -r "$3"; '
               'chown "$4" "$2" "$3"')


@dataclass
class Flashrom:
    binary: Path
    libdir: Path | None                 # LD_LIBRARY_PATH for a flashrom unpacked from Fedora's RPM


def candidates(home: Path) -> list[Flashrom]:
    """Where flashrom may be: unpacked in ~/flashrom (as the manual describes), then on PATH, then /usr/sbin."""
    out = []
    unpacked = home / "flashrom" / "usr" / "bin" / "flashrom"
    if unpacked.is_file():
        out.append(Flashrom(unpacked, home / "flashrom" / "usr" / "lib64"))
    for found in (shutil.which("flashrom"), "/usr/sbin/flashrom", "/usr/bin/flashrom"):
        if found and Path(found).is_file() and all(c.binary != Path(found) for c in out):
            out.append(Flashrom(Path(found), None))
    return out


def has_internal(fr: Flashrom, timeout: float = 10) -> bool:
    """True when this flashrom was built with the internal programmer (Homebrew's is not)."""
    env = dict(os.environ)
    if fr.libdir is not None:
        env["LD_LIBRARY_PATH"] = str(fr.libdir)
    try:
        out = subprocess.run([str(fr.binary), "--help"], capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.SubprocessError):
        return False
    return "internal" in out.stdout + out.stderr


def find_flashrom(home: Path = Path.home()) -> Flashrom | None:
    return next((c for c in candidates(home) if has_internal(c)), None)


def dump_paths(folder: Path, now: float | None = None) -> tuple[Path, Path]:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    return folder / f"bios-{stamp}.bin", folder / f"bios-{stamp}.check.bin"


def read_command(fr: Flashrom, first: Path, second: Path, owner: str) -> list[str]:
    """pkexec command that reads the chip into *first* and *second* and gives both to *owner* (uid:gid)."""
    env = ["env", f"LD_LIBRARY_PATH={fr.libdir}"] if fr.libdir is not None else ["env"]
    return ["pkexec", *env, "sh", "-c", READ_SCRIPT, "sh", str(fr.binary), str(first), str(second), owner, CHIP]


def check_reads(first: Path, second: Path) -> str:
    """"" when the two reads are complete and identical (the second is then removed), otherwise what is wrong."""
    try:
        a, b = first.read_bytes(), second.read_bytes()
    except OSError as exc:
        return f"A read is missing: {exc.strerror or exc}."
    if len(a) != CHIP_SIZE or len(b) != CHIP_SIZE:
        return f"A read has {min(len(a), len(b))} bytes instead of {CHIP_SIZE}."
    if hashlib.sha256(a).digest() != hashlib.sha256(b).digest():
        return "The two reads differ, so the read is not reliable. Try again."
    second.unlink(missing_ok=True)
    return ""
