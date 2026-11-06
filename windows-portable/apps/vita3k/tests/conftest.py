# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication with bc250_core from the checkout, and the settings and the suite's folders
in a temp folder (never Windows' registry); and, as the BC250 suite's Vita3K Manager's tests make them, PS Vita games
made here (a param.sfo written in the PlayStation's layout, in ux0\\app as Vita3K installs them) and Vita3K's portable
folder as build 4186 leaves it beside Vita3K.exe: fixtures/config-4186.yml is the config.yml it wrote on its first
start (the BC250 suite's fixture: the file is the same on every system)."""

from __future__ import annotations

import gc
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
CONFIG_4186 = Path(__file__).resolve().parent / "fixtures" / "config-4186.yml"


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


def make_game(vita_fs: Path, title: str = "Game", title_id: str = "PCSB00001", version: str = "01.00",
              pictures: bool = False, eboot: bool = True, folder: str | None = None, kind: str = "app") -> Path:
    """A game as Vita3K installs it: ux0\\app\\<title ID> with eboot.bin and sce_sys\\param.sfo (and, with *pictures*,
    icon0.png and pic0.png); *kind* "patch" or "addcont" puts it in ux0\\patch or ux0\\addcont instead. Returns its
    folder."""
    game = vita_fs / "ux0" / kind / (folder or title_id)
    (game / "sce_sys").mkdir(parents=True)
    if eboot:
        (game / "eboot.bin").write_bytes(b"SCE\0")
    (game / "sce_sys" / "param.sfo").write_bytes(make_sfo(
        {"APP_VER": version, "ATTRIBUTE": 0, "CATEGORY": "gd" if kind == "app" else "gp", "STITLE": title[:10],
         "TITLE": title, "TITLE_ID": title_id}))
    if pictures:
        from PyQt6.QtGui import QColor, QImage
        for name, size, color in (("icon0.png", (128, 128), "#ff0000"), ("pic0.png", (960, 544), "#00ff00")):
            image = QImage(*size, QImage.Format.Format_ARGB32)
            image.fill(QColor(color))
            image.save(str(game / "sce_sys" / name), "PNG")
    return game


def _sfo(title: str, title_id: str, category: str = "gd") -> bytes:
    return make_sfo({"APP_VER": "01.00", "CATEGORY": category, "STITLE": title[:10], "TITLE": title,
                     "TITLE_ID": title_id})


def make_vpk(path: Path, title: str, title_id: str, category: str = "gd") -> Path:
    """A .vpk (or .zip: the same archive) of a dumped game: eboot.bin and sce_sys\\param.sfo."""
    import zipfile
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("eboot.bin", b"SCE\0")
        archive.writestr("sce_sys/param.sfo", _sfo(title, title_id, category))
    return path


def make_dump(folder: Path, title: str, title_id: str) -> Path:
    """A dumped game's folder, as it is put in Games\\Vita: eboot.bin and sce_sys\\param.sfo."""
    (folder / "sce_sys").mkdir(parents=True)
    (folder / "eboot.bin").write_bytes(b"SCE\0")
    (folder / "sce_sys" / "param.sfo").write_bytes(_sfo(title, title_id))
    return folder


def make_pkg(path: Path, title_id: str) -> Path:
    """The head of a PS Vita .pkg: its magic and, at 0x30, its content ID with the title ID in it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x7fPKG" + b"\0" * (0x30 - 4) + f"UP0001-{title_id}_00-0000000000000000".encode() + b"\0" * 16)
    return path


def write_config(home: Path) -> Path:
    """Vita3K's portable folder with the config.yml build 4186 writes on its first start."""
    path = home / "portable" / "config.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CONFIG_4186.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    return path


def install_firmware(vita_fs: Path, system: bool = True, fonts: bool = True, preinstalled: bool = False) -> None:
    """What Vita3K leaves of the firmware's files: vs0, sa0 and pd0 with something in them."""
    for folder, wanted, inside in (("vs0", system, "vsh/shell/shell.self"), ("sa0", fonts, "data/font/pvf/ltn0.pvf"),
                                   ("pd0", preinstalled, "app/NPXS10007/eboot.bin")):
        if wanted:
            path = vita_fs / folder / inside
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\0")


def fake_install(home: Path, progress=lambda got: None, say=lambda text: None, gate=None, version: str = "",
                 firmware: bool = False) -> str:
    """What emulator.install() leaves behind, without a download: the program, its portable folder and the record
    (and, when asked, the firmware and its fonts in Vita3K's storage)."""
    from vita3k_manager import emulator
    version = version or emulator.VERSION
    progress(12_000_000)
    if gate is not None:
        gate.wait(10)
    say("Unpacking…")
    home.mkdir(parents=True, exist_ok=True)
    (home / emulator.EXE).write_bytes(b"vita3k")
    (home / "data").mkdir(exist_ok=True)
    (home / "data" / "fonts.txt").write_text("", encoding="utf-8")
    (home / emulator.PORTABLE).mkdir(exist_ok=True)
    (home / emulator.RECORD).write_text(json.dumps({"version": version, "files": [emulator.EXE, "data/fonts.txt"]}),
                                        encoding="utf-8")
    if firmware:
        install_firmware(home / emulator.PORTABLE / "fs")
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
    # create_app() (test_main_window.py) installs the tooltip filter on this app, and no aboutToQuit takes it off
    # without an event loop: left on, it can crash pytest's final garbage collection (core's conftest, 06-11-2026).
    from bc250_core.widgets import RoundedToolTip
    RoundedToolTip.uninstall()
    gc.collect()


@pytest.fixture(autouse=True)
def settings_in_tmp(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
