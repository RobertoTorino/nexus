# SPDX-License-Identifier: GPL-3.0-or-later
"""The PS2 games: disc images in the chosen folders. An ISO (plain ISO 9660, as a PS2 DVD is laid out) is read for
its serial and version: SYSTEM.CNF in the disc's root says which program the console boots
(BOOT2 = cdrom0:\\SLUS_123.45;1), and that name is the game's serial. A PS2 disc carries no title or pictures the
way a PSP or PS3 disc does: the title comes from PCSX2's own catalog by the serial (catalogue.py), else from the
file's name without a serial in it ("SLUS_215.53.Lumines Plus" is "Lumines Plus"). The boot program is read too,
for its CRC as PCSX2 computes it (every 32-bit word of the file XORed): with the serial it names the game's own
settings and patches in PCSX2. A CHD, CSO, ZSO or GZ holds the same disc compressed; the app does not look into
those formats and lists the file under its own name, without a serial or CRC. PCSX2 plays them all the same.

ISO 9660 is read directly: the volume descriptor in sector 16 names the root directory, whose records (length,
sector, size, flags, name, each little-endian where both byte orders are stored) lead to SYSTEM.CNF."""

from __future__ import annotations

import os
import re
import struct
from dataclasses import dataclass
from pathlib import Path

MAX_DEPTH = 5
DISC_SUFFIXES = (".iso", ".chd", ".cso", ".zso", ".gz")
READ_SUFFIXES = (".iso",)
SECTOR = 2048
# "BOOT2 = cdrom0:\SLUS_123.45;1" (a CD boots with BOOT instead); the serial is the file's name.
_BOOT = re.compile(r"BOOT2?\s*=\s*cdrom0:\\?([^\s;]+)", re.IGNORECASE)
_VER = re.compile(r"VER\s*=\s*(\S+)", re.IGNORECASE)
# A serial in a file's name, as dumps are often named: in front ("SLUS_215.53.Title", "SLUS-21553 Title") or in
# brackets ("Title [SLUS-21553]", "Title (SLUS-21553)").
_SERIAL = r"[A-Z]{4}[-_ ]?\d{3}\.?\d{2}"
_SERIAL_IN_NAME = re.compile(rf"^{_SERIAL}[\s._-]*|\s*[\[(]{_SERIAL}[\])]", re.IGNORECASE)
_crcs: dict[tuple[str, int, float], int] = {}


@dataclass(frozen=True)
class Game:
    file: Path                          # the disc image
    title: str                          # PCSX2's name for it, else the file's name without a serial
    serial: str = ""                    # SLUS-12345, as PCSX2 shows it
    version: str = ""
    kind: str = "iso"                   # iso, chd, cso, zso or gz
    crc: int = 0                        # the boot program's CRC as PCSX2 computes it; 0 when not read

    @property
    def folder(self) -> Path:
        return self.file.parent


class _Iso:
    def __init__(self, file):
        self.file = file

    def read_at(self, offset: int, size: int) -> bytes:
        self.file.seek(offset)
        return self.file.read(size)


def _records(image, sector: int, size: int):
    """The records of one ISO 9660 directory: (name, sector, size, is a directory)."""
    data = image.read_at(sector * SECTOR, size)
    at = 0
    while at + 33 <= len(data):
        length = data[at]
        if length == 0:                                 # the rest of this sector is empty: the next one
            at = (at // SECTOR + 1) * SECTOR
            continue
        extent = struct.unpack_from("<I", data, at + 2)[0]
        file_size = struct.unpack_from("<I", data, at + 10)[0]
        flags, name_len = data[at + 25], data[at + 32]
        name = data[at + 33:at + 33 + name_len].decode("ascii", "replace").partition(";")[0]
        if name not in ("\0", "\x01"):                  # . and ..
            yield name.upper(), extent, file_size, bool(flags & 2)
        at += length


def _find(image, parts: tuple[str, ...]) -> bytes | None:
    """The file at /parts[0]/parts[1]/... in the image; None when the path is not there or it is no ISO 9660."""
    pvd = image.read_at(16 * SECTOR, SECTOR)
    if len(pvd) < 190 or pvd[0] != 1 or pvd[1:6] != b"CD001":
        return None
    sector, size = struct.unpack_from("<I", pvd, 158)[0], struct.unpack_from("<I", pvd, 166)[0]
    for depth, wanted in enumerate(parts):
        found = next((r for r in _records(image, sector, size) if r[0] == wanted.upper()), None)
        if found is None or found[3] != (depth < len(parts) - 1):
            return None
        _name, sector, size, _directory = found
    return image.read_at(sector * SECTOR, size)


def iso_file(path: Path, parts: tuple[str, ...]) -> bytes | None:
    """One file out of an ISO; None when it is not there. OSError is the caller's."""
    with path.open("rb") as file:
        try:
            return _find(_Iso(file), parts)
        except (ValueError, struct.error, EOFError):
            return None


def serial_of(boot: str) -> str:
    """The boot file's name as PCSX2 shows a serial: SLUS_123.45 (after any folders) becomes SLUS-12345."""
    name = boot.replace("\\", "/").rsplit("/", 1)[-1]
    return name.replace("_", "-").replace(".", "")


def boot_file(data: bytes) -> str:
    """The boot program a SYSTEM.CNF names (SLUS_123.45, or DATA\\SLES_500.03); "" when it names none."""
    boot = _BOOT.search(data.decode("ascii", "replace"))
    return boot.group(1) if boot else ""


def read_system_cnf(data: bytes) -> tuple[str, str]:
    """(serial, version) from a SYSTEM.CNF; ("", "") when it names no boot file."""
    boot = boot_file(data)
    if not boot:
        return "", ""
    version = _VER.search(data.decode("ascii", "replace"))
    return serial_of(boot), version.group(1) if version else ""


def elf_crc(data: bytes) -> int:
    """The CRC PCSX2 gives a game: every 32-bit little-endian word of its boot program XORed."""
    crc = 0
    for (word,) in struct.iter_unpack("<I", data[:len(data) // 4 * 4]):
        crc ^= word
    return crc


def _boot_crc(path: Path, boot: str) -> int:
    """The boot program's CRC, read once per file (by its path, size and time); 0 when it cannot be read."""
    try:
        stat = path.stat()
    except OSError:
        return 0
    key = (str(path), stat.st_size, stat.st_mtime)
    if key not in _crcs:
        parts = tuple(p for p in boot.replace("\\", "/").split("/") if p)
        try:
            data = iso_file(path, parts)
        except OSError:
            data = None
        _crcs[key] = elf_crc(data) if data else 0
    return _crcs[key]


def file_title(stem: str) -> str:
    """A title from a file's name: without a serial in it; the name as it is when nothing else is left."""
    return _SERIAL_IN_NAME.sub("", stem).strip(" ._-") or stem


def is_file(path: Path) -> bool:
    """path.is_file(), False when it cannot be asked: a failing or half-mounted SD card answers with an error (EIO)
    instead of no, which ended the scan (the Windows suite's empty card slot, 29-10-2026)."""
    try:
        return path.is_file()
    except OSError:
        return False


def read_disc(path: Path, titles: dict[str, str] | None = None) -> Game | None:
    """The game of a disc image: an ISO read for its SYSTEM.CNF and boot program, the compressed formats under their
    own name; None when the file is not there. An ISO without a SYSTEM.CNF (not a PS2 disc) is no game. *titles*:
    PCSX2's titles by serial."""
    kind = path.suffix.lower().lstrip(".")
    if not is_file(path):
        return None
    if kind != "iso":
        return Game(path, file_title(path.stem), kind=kind)
    try:
        data = iso_file(path, ("SYSTEM.CNF",))
    except OSError:
        return None
    if data is None:
        return None
    serial, version = read_system_cnf(data)
    if not serial:
        return None
    title = (titles or {}).get(serial) or file_title(path.stem)
    return Game(path, title, serial, version, "iso", _boot_crc(path, boot_file(data)))


def _found(root: Path, depth: int = MAX_DEPTH):
    """The disc images below *root*."""
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)
    except OSError:
        return
    for entry in entries:
        try:
            plain = entry.is_file()
            folder = not plain and depth > 0 and entry.is_dir(follow_symlinks=False)
        except OSError:                                 # a failing card: skipped, the scan goes on
            continue
        if plain:
            if entry.name.lower().endswith(DISC_SUFFIXES):
                yield Path(entry.path)
        elif folder and not entry.name.startswith("."):
            yield from _found(Path(entry.path), depth - 1)


def scan(folders: list[Path], titles: dict[str, str] | None = None) -> list[Game]:
    """Every game below the chosen folders (a game found twice counted once), sorted by title. *titles*: PCSX2's
    titles by serial."""
    seen: set[Path] = set()
    games = []
    for folder in folders:
        for path in _found(folder):
            key = path.resolve()
            if key in seen:
                continue
            seen.add(key)
            game = read_disc(path, titles)
            if game is not None:
                games.append(game)
    return sorted(games, key=lambda g: (g.title.casefold(), g.serial, str(g.file)))
