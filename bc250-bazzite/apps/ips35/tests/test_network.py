# SPDX-License-Identifier: GPL-3.0-or-later
"""The interfaces' kinds, from a fake /sys/class/net as the kernel shows it."""

from __future__ import annotations

from usb_ips35 import network
from conftest import interfaces


def test_kinds(tmp_path):
    root = interfaces(tmp_path)
    assert [network.kind(n, root) for n in ("enp4s0", "wlan0", "virbr0", "tun0", "gone")] == \
        ["Ethernet", "Wi-Fi", "Virtual", "Virtual", ""]
    assert network.label("enp4s0", root) == "enp4s0 (Ethernet)" and network.label("gone", root) == "gone"
