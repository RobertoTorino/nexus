# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication with bc250_core from the checkout, and the settings and the suite's folders
in a temp folder (never Windows' registry); and, as the BC250 suite's Xenia Manager's tests make them, Xbox 360 games
made here: a disc image with its game partition's magic (sparse, at the partition's place), an XEX with its execution
info, and an STFS package with its content type, name and title ID."""

from __future__ import annotations

import json
import os
import struct
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as a release bundles it
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def make_iso(path: Path, partition: int = 0) -> Path:
    """An Xbox 360 disc image: "MICROSOFT*XBOX*MEDIA" in sector 32 of a game partition at *partition* (a sparse
    file where the file system makes one)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as file:
        file.seek(partition + 32 * 2048)
        file.write(b"MICROSOFT*XBOX*MEDIA" + b"\0" * 2028)
    return path


def xex_bytes(title_id: int = 0x4D5307E6) -> bytes:
    """An XEX's start: the XEX2 header with two optional headers, the second the execution info."""
    data = bytearray(0x100)
    data[0:4] = b"XEX2"
    struct.pack_into(">I", data, 0x14, 2)
    struct.pack_into(">II", data, 0x18, 0x00010001, 0)
    struct.pack_into(">II", data, 0x20, 0x00040006, 0x80)
    struct.pack_into(">I", data, 0x80 + 0xC, title_id)
    return bytes(data)


def make_xex(path: Path, title_id: int = 0x4D5307E6) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(xex_bytes(title_id))
    return path


def package_bytes(name: str = "Halo 3", content_type: int = 0x00007000, title_id: int = 0x4D5307E6,
                  magic: bytes = b"LIVE") -> bytes:
    """An STFS package's header: its magic, content type, title ID and name (UTF-16, big-endian)."""
    data = bytearray(0xB000)
    data[0:4] = magic
    struct.pack_into(">I", data, 0x344, content_type)
    struct.pack_into(">I", data, 0x360, title_id)
    encoded = name.encode("utf-16-be")
    data[0x411:0x411 + len(encoded)] = encoded
    return bytes(data)


def make_package(folder: Path, name: str = "Halo 3", content_type: int = 0x00007000, title_id: int = 0x4D5307E6,
                 file: str = "A1B2C3D4E5F6") -> Path:
    """A package as the console keeps it: <title ID>/<content type>/<file>."""
    path = folder / f"{title_id:08X}" / f"{content_type:08X}" / file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(package_bytes(name, content_type, title_id))
    return path


def fake_install(home: Path, progress=lambda got: None, say=lambda text: None, gate=None, version: str = "") -> str:
    """What emulator.install() leaves behind, without a download: the program, its LICENSE and the record."""
    from xenia_manager import emulator
    version = version or emulator.VERSION
    progress(1_200_000)
    if gate is not None:
        gate.wait(10)
    say("Unpacking…")
    home.mkdir(parents=True, exist_ok=True)
    (home / emulator.EXE).write_bytes(b"xenia")
    (home / "LICENSE").write_text("", encoding="utf-8")
    (home / emulator.RECORD).write_text(json.dumps({"version": version, "files": [emulator.EXE, "LICENSE"]}),
                                        encoding="utf-8")
    return version


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
