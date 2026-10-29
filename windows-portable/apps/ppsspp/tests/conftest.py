# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication with bc250_core from the checkout, and the settings and the suite's folders
in a temp folder (never Windows' registry); and, as the BC250 suite's PPSSPP Manager's tests make them, PSP games made
here: a PARAM.SFO written in the PSP's layout, disc images (a small ISO 9660 with /PSP_GAME, and the same ISO as a
CSO), EBOOT.PBPs and PPSSPP's memory stick."""

from __future__ import annotations

import os
import struct
import sys
import zlib
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as a release bundles it
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SECTOR = 2048


def make_sfo(fields: dict[str, str | int]) -> bytes:
    """A PARAM.SFO: header, one 16-byte index entry per field, the key table, then the data table."""
    keys = b"".join(name.encode() + b"\0" for name in fields)
    keys += b"\0" * (-len(keys) % 4)
    index, data, key_at = b"", b"", 0
    for name, value in fields.items():
        if isinstance(value, int):
            raw, kind, room = struct.pack("<I", value), 0x0404, 4
        else:
            raw = value.encode() + b"\0"
            kind, room = 0x0204, len(raw) + (-len(raw) % 4)
        index += struct.pack("<HHIII", key_at, kind, len(raw), room, len(data))
        data += raw + b"\0" * (room - len(raw))
        key_at += len(name) + 1
    key_start = 20 + len(index)
    return b"\0PSF" + struct.pack("<4I", 0x101, key_start, key_start + len(keys), len(fields)) + index + keys + data


def game_sfo(title: str = "Game", disc_id: str = "ULUS10001", version: str = "1.00",
             category: str = "UG") -> bytes:
    return make_sfo({"BOOTABLE": 1, "CATEGORY": category, "DISC_ID": disc_id, "DISC_VERSION": version,
                     "TITLE": title})


def _png(size: tuple[int, int], color: str) -> bytes:
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
    from PyQt6.QtGui import QColor, QImage
    image = QImage(*size, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def game_pictures() -> dict[str, bytes]:
    """The game's own pictures at the PSP's sizes: ICON0.PNG red, PIC1.PNG green."""
    return {"ICON0.PNG": _png((144, 80), "#ff0000"), "PIC1.PNG": _png((480, 272), "#00ff00")}


def _record(name: bytes, sector: int, size: int, directory: bool) -> bytes:
    """One ISO 9660 directory record, both byte orders in place."""
    length = 33 + len(name)
    length += length % 2
    record = bytearray(length)
    record[0] = length
    struct.pack_into("<I", record, 2, sector)
    struct.pack_into(">I", record, 6, sector)
    struct.pack_into("<I", record, 10, size)
    struct.pack_into(">I", record, 14, size)
    record[25] = 2 if directory else 0
    record[32] = len(name)
    record[33:33 + len(name)] = name
    return bytes(record)


def iso_bytes(files: dict[str, bytes], root_name: bytes = b"PSP_GAME") -> bytes:
    """A small ISO 9660: the volume descriptor, a root directory with one folder (*root_name*), and *files* in it
    (PARAM.SFO, pictures). UMD video would have UMD_VIDEO as the folder."""
    sectors: dict[int, bytes] = {}
    root_dir, game_dir = 18, 19
    at = 20
    records = [_record(b"\0", game_dir, SECTOR, True), _record(b"\x01", root_dir, SECTOR, True)]
    for name, data in files.items():
        records.append(_record(name.encode() + b";1", at, len(data), False))
        for n in range(0, max(len(data), 1), SECTOR):
            sectors[at] = data[n:n + SECTOR]
            at += 1
    sectors[game_dir] = b"".join(records)
    sectors[root_dir] = b"".join([_record(b"\0", root_dir, SECTOR, True), _record(b"\x01", root_dir, SECTOR, True),
                                  _record(root_name, game_dir, SECTOR, True)])
    pvd = bytearray(SECTOR)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[156:156 + 34] = _record(b"\0", root_dir, SECTOR, True)
    sectors[16] = bytes(pvd)
    sectors[17] = b"\xff" + b"CD001"                    # the terminator
    image = bytearray((max(sectors) + 1) * SECTOR)
    for n, data in sectors.items():
        image[n * SECTOR:n * SECTOR + len(data)] = data
    return bytes(image)


def cso_bytes(iso: bytes, align: int = 0) -> bytes:
    """The ISO as a CSO v1: each 2048-byte block deflated, or stored as it is (the top bit) when deflate does not
    make it smaller."""
    blocks = [iso[n:n + SECTOR] for n in range(0, len(iso), SECTOR)]
    index: list[int] = []
    body = b""
    start = 24 + 4 * (len(blocks) + 1)
    start += -start % (1 << align)
    for block in blocks:
        packed = zlib.compress(block, 9)[2:-4]          # raw deflate: no zlib header or checksum
        plain = len(packed) >= len(block)
        at = start + len(body)
        index.append((at >> align) | (0x80000000 if plain else 0))
        data = block if plain else packed
        body += data + b"\0" * (-len(data) % (1 << align))
    index.append((start + len(body)) >> align)
    header = struct.pack("<4sIQIBBH", b"CISO", 24, len(iso), SECTOR, 1, align, 0)
    return header + struct.pack(f"<{len(index)}I", *index) + b"\0" * (start - 24 - 4 * len(index)) + body


def pbp_bytes(sfo: bytes, icon0: bytes = b"", pic1: bytes = b"") -> bytes:
    """An EBOOT.PBP: the magic, a version, eight offsets and the parts (the program a stub)."""
    parts = [sfo, icon0, b"", b"", pic1, b"", b"DATA.PSP", b"DATA.PSAR"]
    offsets, at = [], 40
    for part in parts:
        offsets.append(at)
        at += len(part)
    return b"\0PBP" + struct.pack("<I", 0x10000) + struct.pack("<8I", *offsets) + b"".join(parts)


def make_disc(path: Path, title: str = "Game", disc_id: str = "ULUS10001", version: str = "1.00",
              pictures: bool = False, cso: bool = False) -> Path:
    """A disc image on disk: an ISO with /PSP_GAME/PARAM.SFO (and the pictures), or the same as a CSO."""
    files = {"PARAM.SFO": game_sfo(title, disc_id, version)}
    if pictures:
        files.update(game_pictures())
    iso = iso_bytes(files)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(cso_bytes(iso) if cso else iso)
    return path


def make_pbp(folder: Path, title: str = "Homebrew", disc_id: str = "", version: str = "1.00",
             category: str = "MG", pictures: bool = False) -> Path:
    """A memory stick game: its folder with an EBOOT.PBP. Returns the EBOOT.PBP."""
    folder.mkdir(parents=True, exist_ok=True)
    art = game_pictures() if pictures else {}
    pbp = folder / "EBOOT.PBP"
    pbp.write_bytes(pbp_bytes(make_sfo({"BOOTABLE": 1, "CATEGORY": category, "DISC_ID": disc_id,
                                        "DISC_VERSION": version, "TITLE": title}),
                              art.get("ICON0.PNG", b""), art.get("PIC1.PNG", b"")))
    return pbp


def make_memstick(stick: Path) -> Path:
    """PPSSPP's memory stick as it leaves it: the PSP's layout."""
    for name in ("PSP/GAME", "PSP/SAVEDATA", "PSP/SYSTEM"):
        (stick / name).mkdir(parents=True, exist_ok=True)
    return stick


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from bc250_core import portable
    portable.pin_scale((1280, 720))     # the Ally's screen, not the offscreen one (800 x 800): the windows fit-tested
    yield app
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)


@pytest.fixture(autouse=True)
def settings_in_tmp(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
