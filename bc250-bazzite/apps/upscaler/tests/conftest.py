# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication and a fake HelixSR payload in a temporary folder. The DLL and the
network files are just marker bytes; nothing here needs a GPU, Steam or a real HelixSR release."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.append(str(CORE))              # bc250_core from the checkout, as the installer bundles it; last, so
                                            # tests is still this app's

FAKE_DLL = b"MZ-HelixSR 1.2.0-fake-dll"
FAKE_GAME_DLL = b"MZ-amd-original-dll"
FAKE_README = "# HelixSR\n\n**Version 1.2.0** - test build\n"


def embedded_dll(dll: bytes = FAKE_DLL) -> bytes:
    """A HelixSR 1.8+ DLL after its setup: the network appended, with the footer HelixSR's setup writes."""
    import struct
    weights, pak = b"weights", b"kernels"
    return dll + weights + pak + b"HXSRNET1" + struct.pack("<QQQ", len(weights), len(pak), 1)


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    """QSettings files go to tmp_path, never into the user's own settings. On Windows the native format is the
    registry, which setPath() cannot redirect, so there QSettings(org, app) becomes the same call with IniFormat."""
    from PyQt6.QtCore import QSettings
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))     # the portal's notice files (bc250_core.upstream)
    for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
        QSettings.setPath(fmt, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    if sys.platform == "win32":
        from upscaler import __main__ as main_module, main_window

        class FileSettings(QSettings):
            def __init__(self, *args):
                if args and isinstance(args[0], str):
                    args = (QSettings.Format.IniFormat, QSettings.Scope.UserScope, *args)
                super().__init__(*args)

        for module in (main_module, main_window):
            monkeypatch.setattr(module, "QSettings", FileSettings)
    return tmp_path / "settings"


def make_release(folder: Path, *, network: bool = True, ini: bool = True, readme: bool = True) -> Path:
    """Lay out an extracted HelixSR release (what the user points the import at)."""
    from upscaler import backend
    folder.mkdir(parents=True, exist_ok=True)
    (folder / backend.HELIXSR_DLL).write_bytes(FAKE_DLL)
    if network:
        (folder / backend.WEIGHTS).write_bytes(b"weights")
        (folder / backend.KERNELS).write_bytes(b"kernels")
    if ini:
        (folder / backend.INI).write_text(backend.DEFAULT_INI_TEXT, encoding="utf-8")
    if readme:
        (folder / "README.md").write_text(FAKE_README, encoding="utf-8")
    (folder / "helixsr-setup.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    return folder


@pytest.fixture
def release(tmp_path: Path) -> Path:
    return make_release(tmp_path / "HelixSR-v1.2.0")


@pytest.fixture
def payload(tmp_path: Path) -> Path:
    """A complete, imported payload."""
    return make_release(tmp_path / "payload")


@pytest.fixture
def game(tmp_path: Path) -> Path:
    """A game folder with the FSR DLL in a nested Win64 folder, like Unreal games have."""
    from upscaler import backend
    root = tmp_path / "steamapps" / "common" / "SomeGame"
    win64 = root / "Engine" / "Plugins" / "FSR3" / "ThirdParty" / "Win64"
    win64.mkdir(parents=True)
    (win64 / backend.UPSCALER_DLL).write_bytes(FAKE_GAME_DLL)
    (root / "SomeGame.exe").write_bytes(b"MZ")
    return root
