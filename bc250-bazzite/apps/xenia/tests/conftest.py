# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings and XDG folders in a temp folder, and Xbox 360 games made
here: a disc image with its game partition's magic (sparse, at the partition's place), an XEX with its execution
info, and an STFS package with its content type, name and title ID."""

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


def make_iso(path: Path, partition: int = 0) -> Path:
    """An Xbox 360 disc image: "MICROSOFT*XBOX*MEDIA" in sector 32 of a game partition at *partition* (a sparse
    file, so a real disc's place costs no space)."""
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
