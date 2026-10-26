# SPDX-License-Identifier: GPL-3.0-or-later
"""What kind of network interface a name is, as the kernel shows it in /sys/class/net, so the Values tab can say
"enp4s0 (Ethernet)" rather than the bare name."""

from __future__ import annotations

from pathlib import Path

NET = Path("/sys/class/net")
ETHER = "1"                             # ARPHRD_ETHER, in the interface's type file


def kind(name: str, root: Path = NET) -> str:
    """Wi-Fi, Ethernet, Virtual (a bridge, VPN or container network: no device of its own) or "" when unknown."""
    folder = root / name
    if (folder / "wireless").is_dir() or (folder / "phy80211").exists():
        return "Wi-Fi"
    try:
        arp_type = (folder / "type").read_text().strip()
    except OSError:
        return ""
    if not (folder / "device").exists():
        return "Virtual"
    return "Ethernet" if arp_type == ETHER else ""


def label(name: str, root: Path = NET) -> str:
    found = kind(name, root)
    return f"{name} ({found})" if found else name
