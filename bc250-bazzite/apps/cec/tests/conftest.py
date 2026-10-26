# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings in a temp folder, and a fake BC-250 with amdgpu's CEC
adapter on DP-1 and a Xiaomi Mi TV behind it. The cec-ctl output is what the owner's board printed (11-10-2026):
NACK with CEC off in the TV, ACK, POWER_ON and TOPOLOGY_TV after it was switched on."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it
sys.path.insert(0, str(Path(__file__).resolve().parent))

INFO = """Driver Info:
\tDriver Name                : amdgpu
\tAdapter Name               : DP-1
\tCapabilities               : 0x0000037e
\t\tLogical Addresses
\t\tTransmit
\t\tPassthrough
\t\tRemote Control Support
\t\tMonitor All
\t\tNeeds HPD
\t\tConnector Info
\t\tReply Vendor ID
\tDriver version             : 7.2.8
\tAvailable Logical Addresses: 4
\tDRM Connector Info         : card 1, connector 87
\tPhysical Address           : 1.0.0.0
\tLogical Address Mask       : 0x0010
\tCEC Version                : 2.0
\tVendor ID                  : 0x000c03 (HDMI)
\tOSD Name                   : 'Playback'
\tLogical Addresses          : 1 (Allow RC Passthrough)

\t  Logical Address          : 4 (Playback Device 1)
\t    Primary Device Type    : Playback
\t    Logical Address Type   : Playback
\t    All Device Types       : Playback
\t    RC TV Profile          : None
\t    Device Features        :
\t\tNone

"""

UNCONFIGURED = (INFO.split("\tLogical Addresses          :")[0]
                .replace("Logical Address Mask       : 0x0010", "Logical Address Mask       : 0x0000")
                + "\tLogical Addresses          : 0 \n")

TOPOLOGY = INFO + "\n\tTopology:\n\n\t    1.0.0.0: Playback Device 1\n"
TOPOLOGY_TV = INFO + "\n\tTopology:\n\n\t    0.0.0.0: TV\n\t        1.0.0.0: Playback Device 1\n"

NACK = """Transmit from Playback Device 1 to TV (4 to 0):
GIVE_DEVICE_POWER_STATUS (0x8f)
\tSequence: 82 Tx Timestamp: 87994.730395s
\tTx, Not Acknowledged (1), Max Retries
"""

POWER_ON = """
Transmit from Playback Device 1 to TV (4 to 0):
GIVE_DEVICE_POWER_STATUS (0x8f)
    Received from TV (0):
    REPORT_POWER_STATUS (0x90):
\tpwr-state: on (0x00)
\tSequence: 126 Tx Timestamp: 89061.825312s Rx Timestamp: 89061.918533s
\tApproximate response time: 21 ms
"""

ACK = """
Transmit from Playback Device 1 to TV (4 to 0):
POLL
\tSequence: 125 Tx Timestamp: 89061.761256s
"""

# The EDID base block of the owner's TV, cut to what the app reads: the header and the monitor name descriptor.
EDID = bytearray(128)
EDID[0:8] = bytes.fromhex("00ffffffffffff00")
EDID[54 + 18 * 3:54 + 18 * 4] = b"\0\0\0\xfc\0" + b"Mi TV\n" + b" " * 7


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
    return tmp_path / "settings"


@pytest.fixture
def dev_root(tmp_path) -> Path:
    root = tmp_path / "dev"
    root.mkdir()
    (root / "cec0").touch()
    return root


@pytest.fixture
def sys_root(tmp_path) -> Path:
    root = tmp_path / "sys"
    connector = root / "class/drm/card1-DP-1"
    connector.mkdir(parents=True)
    (connector / "edid").write_bytes(bytes(EDID))
    (connector / "status").write_text("connected\n")
    return root


@pytest.fixture
def usr_root(tmp_path) -> Path:
    root = tmp_path / "usr"
    (root / "bin").mkdir(parents=True)
    (root / "bin/cecd").touch()
    return root


@pytest.fixture
def etc_root(tmp_path) -> Path:
    root = tmp_path / "etc"
    root.mkdir()
    return root
