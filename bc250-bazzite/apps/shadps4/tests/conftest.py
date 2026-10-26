# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings and XDG folders in a temp folder, PS4 game folders made
here (a param.sfo written in the PS4's layout, with the fields a game has), and for Extract PKG a synthetic PKG that is
encrypted the way real packages are (pkg_builder.py), since no game package can ship with the tests."""

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
    """A param.sfo: header, one 16-byte index entry per field, the key table, then the data table."""
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


def make_game(folder: Path, title: str | None = None, title_id: str = "CUSA00001", version: str = "01.00",
              category: str = "gd", pictures: bool = False) -> Path:
    """A game folder with eboot.bin and, unless *title* is None, sce_sys/param.sfo. Returns eboot.bin."""
    (folder / "sce_sys").mkdir(parents=True)
    eboot = folder / "eboot.bin"
    eboot.write_bytes(b"\x7fELF")
    if title is not None:
        (folder / "sce_sys" / "param.sfo").write_bytes(make_sfo(
            {"APP_VER": version, "ATTRIBUTE": 0, "CATEGORY": category, "TITLE": title, "TITLE_ID": title_id}))
    if pictures:
        from PyQt6.QtGui import QColor, QImage
        for name, size, colour in (("icon0.png", (512, 512), "#ff0000"), ("pic1.png", (1920, 1080), "#00ff00")):
            image = QImage(*size, QImage.Format.Format_ARGB32)
            image.fill(QColor(colour))
            image.save(str(folder / "sce_sys" / name))
    return eboot


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="session")
def built_pkg(tmp_path_factory):
    """A small game package: sce_sys entries plus a PFS with raw, compressed, multi-block and empty files."""
    from pkg_builder import build_pkg, default_tree
    return build_pkg(tmp_path_factory.mktemp("pkg") / "synthetic.pkg", default_tree())


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    """The app keeps an .ini (AppInfo.settings_ini), so this also keeps the tests out of the Windows registry."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    return tmp_path / "settings"


def read_message(data: bytes) -> dict[int, str]:
    """The text fields of a protobuf message, by number (what the fake server reads)."""
    fields, at = {}, 0
    while at < len(data):
        key, at = data[at], at + 1
        size, at = data[at], at + 1
        fields[key >> 3], at = data[at:at + size].decode(), at + size
    return fields


class FakeShadNet:
    """A shadNet server on one end of a socket pair: sends ServerInfo (*version*), then answers each request with
    *error* after a notification, and keeps what it got. connect() is what shadnet.request() takes."""

    def __init__(self, error: int = 0, version: int = 1, first: int = 3):
        self.error, self.version, self.first = error, version, first
        self.requests: list[tuple[int, dict[int, str]]] = []
        self.addresses: list[tuple[str, int]] = []

    def connect(self, address, timeout):
        import socket
        import threading
        self.addresses.append(address)
        mine, theirs = socket.socketpair()
        threading.Thread(target=self._serve, args=(mine,), daemon=True).start()
        return theirs

    def _serve(self, sock) -> None:
        import struct
        header = struct.Struct("<BHIQ")
        with sock:
            sock.sendall(header.pack(self.first, 0, 19, 0) + struct.pack("<I", self.version))
            data = b""
            while len(data) < header.size:
                chunk = sock.recv(64)
                if not chunk:
                    return
                data += chunk
            kind, command, total, number = header.unpack(data[:header.size])
            while len(data) < total:
                data += sock.recv(total - len(data))
            size = struct.unpack_from("<I", data, header.size)[0]
            self.requests.append((command, read_message(data[header.size + 4:header.size + 4 + size])))
            sock.sendall(header.pack(2, 7, header.size + 1, 0) + b"\0")             # a notification first
            sock.sendall(header.pack(1, command, header.size + 1, number) + bytes([self.error]))
            sock.recv(64)                                                         # until the client closes


def write_shad_files(home: Path) -> Path:
    """shadPS4's folder as 0.19.0 leaves it after its first start: config.json (kept when there is one, with
    shadNet's settings added) and users.json with its four users."""
    import json
    home.mkdir(parents=True, exist_ok=True)
    try:
        config = json.loads((home / "config.json").read_text())
    except FileNotFoundError:
        config = {"Audio": {"audio_backend": 0}, "General": {"install_dirs": [], "show_splash": True}}
    config["General"].update(shad_net_enabled=False, shadnet_server="srv.shadps4.net:31313")
    users = {"Users": {"commit_hash": "c7e065d1", "user": [
        {"np_age": 30, "player_index": n, "shadnet_email": "", "shadnet_enabled": False, "shadnet_npid": "",
         "shadnet_password": "", "shadnet_token": "", "user_color": n, "user_id": 999 + n,
         "user_name": "shadPS4" if n == 1 else f"shadPS4-{n}"} for n in range(1, 5)]}}
    (home / "config.json").write_text(json.dumps(config, indent=2))
    (home / "users.json").write_text(json.dumps(users, indent=2))
    return home


@pytest.fixture
def shad_files(tmp_path):
    return write_shad_files(tmp_path / "shadPS4")
