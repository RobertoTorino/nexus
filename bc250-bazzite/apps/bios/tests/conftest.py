# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings in a temp folder, a synthetic BIOS image (fake_bios.py), a
table made from it, and a fake /sys with the board's DMI data and UEFI variables."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_bios  # noqa: E402

AMD_GUID = "3a997502-647a-4c82-998e-52ef9486a247"


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
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return tmp_path / "settings"


@pytest.fixture
def image() -> bytes:
    return fake_bios.image()


@pytest.fixture
def dump_file(tmp_path, image) -> Path:
    path = tmp_path / "bios.bin"
    path.write_bytes(image)
    return path


@pytest.fixture
def stock(monkeypatch):
    """Makes the synthetic BIOS a known stock release, P9.99."""
    from bios_reader import bios
    sha = hashlib.sha256(fake_bios.form_package()).hexdigest()
    monkeypatch.setattr(bios, "STOCK", {"P9.99": {"date": "01/02/2023", "amdsetup_size": 16,
                                                  "formsets": {str(fake_bios.FORMSET).upper(): sha}}})


def write(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else (data + "\n").encode())


@pytest.fixture
def sys_root(tmp_path) -> Path:
    """A running board with BIOS P9.99: DMI data and the runtime UEFI variables (no Setup, as on the BC-250)."""
    root = tmp_path / "sys"
    dmi = root / "class/dmi/id"
    write(dmi / "bios_vendor", "Vendor Inc.")
    write(dmi / "bios_version", "P9.99")
    write(dmi / "bios_date", "01/02/2023")
    efivars = root / "firmware/efi/efivars"
    write(efivars / f"AmdSetup-{AMD_GUID}", b"\x07\0\0\0" + bytes(16))
    write(efivars / "Timeout-8be4df61-93ca-11d2-aa0d-00e098032b8c", b"\x07\0\0\0\x05\0")
    return root


@pytest.fixture
def tables_dir(tmp_path, dump_file) -> Path:
    from bios_reader import bios
    folder = tmp_path / "tables"
    folder.mkdir()
    name, data = bios.build_table(dump_file)
    (folder / name).write_bytes(data)
    return folder
