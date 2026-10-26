# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings and XDG folders in a temp folder, and PS2 games made here:
a small ISO 9660 with SYSTEM.CNF in its root, as a PS2 disc names its boot file, and PCSX2's own folder with a
BIOS dump. For the memory cards: mymc++'s own test data (fixtures/mymcplusplus-data.tar.gz, its test/data.tar.gz
at the pinned commit) and its clock fixed as its tests fix it."""

from __future__ import annotations

import hashlib
import os
import shutil
import struct
import sys
import tarfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it

SECTOR = 2048
FIXTURES = Path(__file__).resolve().parent / "fixtures"


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


def iso_bytes(files: dict[str, bytes]) -> bytes:
    """A small ISO 9660 with *files* in its root directory, as a PS2 DVD holds SYSTEM.CNF."""
    sectors: dict[int, bytes] = {}
    root_dir = 18
    at = 19
    records = [_record(b"\0", root_dir, SECTOR, True), _record(b"\x01", root_dir, SECTOR, True)]
    for name, data in files.items():
        records.append(_record(name.encode() + b";1", at, len(data), False))
        for n in range(0, max(len(data), 1), SECTOR):
            sectors[at] = data[n:n + SECTOR]
            at += 1
    sectors[root_dir] = b"".join(records)
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


def system_cnf(boot: str = "cdrom0:\\SLUS_123.45;1", version: str = "1.00") -> bytes:
    return f"BOOT2 = {boot}\r\nVER = {version}\r\nVMODE = NTSC\r\n".encode()


def make_disc(path: Path, serial_file: str = "SLUS_123.45", version: str = "1.00", program: bytes = b"") -> Path:
    """A PS2 disc image on disk: an ISO whose SYSTEM.CNF boots *serial_file*, with *program* as that file when
    given (its CRC is the game's)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    files = {"SYSTEM.CNF": system_cnf(f"cdrom0:\\{serial_file};1", version)}
    if program:
        files[serial_file] = program
    path.write_bytes(iso_bytes(files))
    return path


def make_bios(folder: Path, name: str = "SCPH-70012.bin") -> Path:
    """A BIOS dump in PCSX2's bios folder, with the files a dump brings beside it."""
    folder.mkdir(parents=True, exist_ok=True)
    dump = folder / name
    dump.write_bytes(b"\0" * 64)
    (folder / f"{dump.stem}.nvm").write_bytes(b"\0" * 16)
    return dump


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    """The app keeps an .ini (AppInfo.settings_ini), so this also keeps the tests out of the Windows registry."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    return tmp_path / "settings"


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


@pytest.fixture(scope="session")
def mymc_data(tmp_path_factory) -> Path:
    """mymc++'s test data: two 8 MB cards (mc01.ps2 with Rez's save and the PS2's system configuration, mc02.ps2
    empty), Rez's save in each format the import reads, and a PS2 and a PS1 save as .psv."""
    folder = tmp_path_factory.mktemp("mymc")
    with tarfile.open(FIXTURES / "mymcplusplus-data.tar.gz") as tar:
        tar.extractall(folder, filter="data")
    return folder


@pytest.fixture
def cards(mymc_data, tmp_path) -> Path:
    """A memcards folder with copies of both cards."""
    folder = tmp_path / "memcards"
    folder.mkdir()
    for name in ("mc01.ps2", "mc02.ps2"):
        shutil.copy(mymc_data / name, folder / name)
    return folder


@pytest.fixture
def fixed_time(monkeypatch):
    """The cards' clock as mymc++'s tests fix it (20-04-2018 22:37:42 on the PS2's clock), in every module of the
    card code that reads it, so a changed card has the checksum mymc++'s tests expect."""
    from pcsx2_manager import mymc
    from pcsx2_manager.mymc import ps2mc, ps2mc_dir
    from pcsx2_manager.mymc.save import ps2save

    def tod_now():
        return 42, 37, 22, 20, 4, 2018
    for module in (ps2mc, ps2mc_dir, ps2save, mymc):
        if hasattr(module, "tod_now"):
            monkeypatch.setattr(module, "tod_now", tod_now)
