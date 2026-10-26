# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings and XDG folders in a temp folder, and PS3 games made here:
a PARAM.SFO written in the PS3's layout, disc games (PS3_DISC.SFB and PS3_GAME) and installed games, and RPCS3's
own folder as 0.0.43 leaves it."""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it


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


def _content(content: Path, title: str, title_id: str, version: str, category: str, pictures: bool,
             eboot: bool = True) -> Path:
    (content / "USRDIR").mkdir(parents=True)
    if eboot:
        (content / "USRDIR" / "EBOOT.BIN").write_bytes(b"SCE\0")
    (content / "PARAM.SFO").write_bytes(make_sfo(
        {"APP_VER": version, "ATTRIBUTE": 0, "CATEGORY": category, "TITLE": title, "TITLE_ID": title_id,
         "VERSION": "01.00"}))
    if pictures:
        from PyQt6.QtGui import QColor, QImage
        for name, size, colour in (("ICON0.PNG", (320, 176), "#ff0000"), ("PIC1.PNG", (1920, 1080), "#00ff00")):
            image = QImage(*size, QImage.Format.Format_ARGB32)
            image.fill(QColor(colour))
            image.save(str(content / name), "PNG")
    return content / "USRDIR" / "EBOOT.BIN"


def make_disc_game(folder: Path, title: str = "Game", title_id: str = "BLUS30001", version: str = "01.00",
                   sfb: bytes | None = b".SFB\0\0\0\x01", pictures: bool = False) -> Path:
    """A disc game copied from its disc: PS3_DISC.SFB (None: without it) and PS3_GAME. Returns EBOOT.BIN."""
    eboot = _content(folder / "PS3_GAME", title, title_id, version, "DG", pictures)
    if sfb is not None:
        (folder / "PS3_DISC.SFB").write_bytes(sfb + b"\0" * 32)
    return eboot


def make_hdd_game(folder: Path, title: str = "Game", title_id: str = "NPUB30001", version: str = "01.00",
                  category: str = "HG", pictures: bool = False, eboot: bool = True) -> Path:
    """A game installed from a package (or, with category "GD", an update). Returns EBOOT.BIN."""
    return _content(folder, title, title_id, version, category, pictures, eboot)


def write_rpcs3_files(home: Path, firmware: str | None = "release:04.9200:\nbuild:...\n",
                      games: dict[str, str] | None = None, vfs: str | None = None) -> Path:
    """RPCS3's folder as 0.0.43 leaves it: vfs.yml as it writes it, games.yml with the disc games it knows, and
    the firmware's version.txt (None: no firmware installed)."""
    home.mkdir(parents=True, exist_ok=True)
    (home / "vfs.yml").write_text(vfs if vfs is not None else (
        '$(EmulatorDir): ""\n/dev_hdd0/: $(EmulatorDir)dev_hdd0/\n/dev_hdd1/: $(EmulatorDir)dev_hdd1/\n'
        "/dev_flash/: $(EmulatorDir)dev_flash/\n/dev_flash2/: $(EmulatorDir)dev_flash2/\n"
        "/dev_flash3/: $(EmulatorDir)dev_flash3/\n/dev_bdvd/: $(EmulatorDir)dev_bdvd/\n"
        '/games/: $(EmulatorDir)games/\n/app_home/: ""\n/dev_usb***/:\n  /dev_usb000:\n'
        "    Path: $(EmulatorDir)dev_usb000/\n"))
    (home / "games.yml").write_text("".join(f"{key}: {value}\n" for key, value in (games or {}).items()))
    if firmware is not None:
        version = home / "dev_flash" / "vsh" / "etc" / "version.txt"
        version.parent.mkdir(parents=True)
        version.write_text(firmware)
    (home / "dev_hdd0" / "game").mkdir(parents=True)
    return home


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
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))      # RPCS3's log
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))      # WirePlumber's stream volumes
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    return tmp_path / "settings"


@pytest.fixture
def rpcs3_files(tmp_path):
    return write_rpcs3_files(tmp_path / "rpcs3")
