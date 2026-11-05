# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication with bc250_core from the checkout, and the settings and the suite's folders
in a temp folder (never Windows' registry); and, as the BC250 suite's BC-250 Upscaler Manager's tests make them, a fake
HelixSR: the DLL and the network files are marker bytes, a game is a folder with an FSR 3.1 DLL in it. Nothing here
needs a GPU, Steam, the network or a real HelixSR release, and no real game is touched."""

from __future__ import annotations

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

DATA = Path(__file__).resolve().parent / "data"
FAKE_DLL = b"MZ-HelixSR 1.2.0-fake-dll"
FAKE_GAME_DLL = b"MZ-amd-original-dll"
FAKE_README = "# HelixSR\n\n**Version 1.2.0** - test build\n"


def embedded_dll(dll: bytes = b"MZ-HelixSR 2.0.0-fake-dll") -> bytes:
    """A HelixSR 1.8+ DLL after its setup: the network appended, with the footer HelixSR's setup writes."""
    weights, pak = b"weights", b"kernels"
    return dll + weights + pak + b"HXSRNET1" + struct.pack("<QQQ", len(weights), len(pak), 1)


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)


@pytest.fixture(autouse=True)
def settings_in_tmp(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


def make_release(folder: Path, *, network: bool = True, ini: bool = True, readme: bool = True) -> Path:
    """An extracted HelixSR 1.x release, after its setup (what the user points the import at)."""
    from upscale_boost import backend
    folder.mkdir(parents=True, exist_ok=True)
    (folder / backend.HELIXSR_DLL).write_bytes(FAKE_DLL)
    if network:
        (folder / backend.WEIGHTS).write_bytes(b"weights")
        (folder / backend.KERNELS).write_bytes(b"kernels")
    if ini:
        (folder / backend.INI).write_text(backend.DEFAULT_INI_TEXT, encoding="utf-8")
    if readme:
        (folder / "README.md").write_text(FAKE_README, encoding="utf-8")
    (folder / "helixsr-setup.ps1").write_text("# setup\n", encoding="utf-8")
    return folder


def make_payload(folder: Path, version: str = "2.0.0", optiscaler: bool = False) -> Path:
    """An imported HelixSR 2.x payload: the DLL with its network built in, the README naming the version."""
    from upscale_boost import backend
    folder.mkdir(parents=True, exist_ok=True)
    (folder / backend.HELIXSR_DLL).write_bytes(embedded_dll(f"MZ-HelixSR {version}-fake".encode()))
    (folder / "README.md").write_text(f"# HelixSR {version}\n", encoding="utf-8")
    if optiscaler:
        opti = folder / backend.OPTISCALER_DIR
        opti.mkdir()
        (opti / "OptiScaler.dll").write_bytes(b"MZ OptiScaler dll")
        (opti / "OptiScaler.ini").write_text("[Upscalers]\nDx12Upscaler=auto\n\n[Libraries]\nFfxDx12Path=auto\n",
                                             encoding="utf-8")
        (opti / "fakenvapi.dll").write_bytes(b"MZ fakenvapi")
        (opti / "fakenvapi.ini").write_text("[fakenvapi]\n", encoding="utf-8")
    return folder


def make_game(root: Path, name: str = "SomeGame", fsr: bool = True) -> Path:
    """A game folder with the FSR DLL in a nested Win64 folder, as Unreal games have it, and its .exe."""
    from upscale_boost import backend
    game = root / name
    win64 = game / "Engine" / "Plugins" / "FSR3" / "ThirdParty" / "Win64"
    win64.mkdir(parents=True)
    if fsr:
        (win64 / backend.UPSCALER_DLL).write_bytes(FAKE_GAME_DLL)
    shipping = game / name / "Binaries" / "Win64"
    shipping.mkdir(parents=True)
    (shipping / f"{name}-Win64-Shipping.exe").write_bytes(b"MZ" * 50)
    (game / "UnrealCEFSubProcess.exe").write_bytes(b"MZ" * 500)
    return game


def make_steam(root: Path, games: dict[str, bool], app_id: int = 1000) -> Path:
    """A Steam folder with a library: steamapps\\common\\<game> (with an FSR DLL where *games* says so) and an
    appmanifest for each."""
    steam = root / "Steam"
    (steam / "userdata").mkdir(parents=True)
    common = steam / "steamapps" / "common"
    common.mkdir(parents=True)
    for n, (name, fsr) in enumerate(games.items()):
        make_game(common, name, fsr)
        (steam / "steamapps" / f"appmanifest_{app_id + n}.acf").write_text(
            f'"AppState"\n{{\n\t"appid"\t\t"{app_id + n}"\n\t"installdir"\t\t"{name}"\n}}\n', encoding="utf-8")
    return steam


@pytest.fixture
def release(tmp_path: Path) -> Path:
    return make_release(tmp_path / "HelixSR-v1.2.0")


@pytest.fixture
def payload(tmp_path: Path) -> Path:
    """A complete, imported 1.x payload (separate network files)."""
    return make_release(tmp_path / "payload")


@pytest.fixture
def game(tmp_path: Path) -> Path:
    return make_game(tmp_path / "steamapps" / "common")
