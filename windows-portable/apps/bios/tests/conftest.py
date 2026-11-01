# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication with bc250_core from the checkout, the settings and the suite's folders
in a temp folder (never Windows' registry), and synthetic BIOS files (fake_bios.py, the BC250 suite's): a flash image
with stored values, and a maker's update (ASUS's version marker, no stored values) in a zip."""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as a release bundles it
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_bios  # noqa: E402

ASUS_MARKER = b"$AsusTestVer$\0\0\0RC00XA.123\0\0\0"


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


@pytest.fixture
def image() -> bytes:
    return fake_bios.image()


@pytest.fixture
def bios_file(tmp_path, image) -> Path:
    """A flash image: setup screens, stored values (Mode On) and defaults; SMBIOS names it P9.99."""
    path = tmp_path / "files" / "bios.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image)
    return path


@pytest.fixture
def update_zip(tmp_path, image) -> Path:
    """A maker's update as it is downloaded: a zip with the image (ASUS's version marker in it) and a note."""
    path = tmp_path / "files" / "RC00XAAS123.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("RC00XAAS.123", image + ASUS_MARKER)
        archive.writestr("readme.txt", "Flash it with EZ Flash.")
    return path
