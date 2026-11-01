# SPDX-License-Identifier: AGPL-3.0-or-later
"""Personal details hidden in the window and the log: the PSN account ID, the PSN online ID and the consoles'
addresses (owner's decisions, 13-10-2026).

Only the end stays visible: the last 4 characters of the account ID (as a number or as the 12-character code), the
last part of an address (192.168.1.20 shows as •••.•••.•••.20). The online ID is a name, so it is hidden whole.
Masker hides the values it was told about and, in free text, anything that looks like an IPv4 address, an account
number or an account code, so a line it was not told about is covered too."""

from __future__ import annotations

import ipaddress
import re

DOT = "•"
KEEP = 4                                 # characters of the account ID that stay visible
NAME_MASK = DOT * 6                      # an online ID, whatever its length

_IPV4 = re.compile(r"(?<!\d)(?<!\d\.)(?:\d{1,3}\.){3}\d{1,3}(?!\.?\d)")      # a full stop after it may end a sentence
_ACCOUNT_NUMBER = re.compile(r"(?<!\d)\d{15,20}(?!\d)")
_ACCOUNT_CODE = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{11}=")


def mask_id(text: str) -> str:
    """An account ID with only its last 4 characters."""
    text = text.strip()
    if len(text) <= KEEP:
        return DOT * len(text)
    return DOT * (len(text) - KEEP) + text[-KEEP:]


def mask_address(text: str) -> str:
    """An address with only its last part: •••.•••.•••.20, or ••••:…:5 for IPv6; a name keeps its last 4."""
    text = text.strip()
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return mask_id(text)
    if address.version == 4:
        return f"{DOT * 3}.{DOT * 3}.{DOT * 3}.{text.rsplit('.', 1)[1]}"
    return f"{DOT * 4}:…:{text.rsplit(':', 1)[1]}"


class Masker:
    """Masks the personal details in a piece of text: the ones it knows (remember()) and the shapes above."""

    def __init__(self):
        self.known: dict[str, str] = {}

    def remember(self, *, account: str = "", online_id: str = "", address: str = "") -> bool:
        """A value to hide; True when it is new (the window then shows its text again)."""
        new = False
        for value, mask in ((account, mask_id), (online_id, lambda _: NAME_MASK), (address, mask_address)):
            value = value.strip()
            if value and value not in self.known:
                self.known[value] = mask(value)
                new = True
        return new

    def mask(self, text: str) -> str:
        for value in sorted(self.known, key=len, reverse=True):          # the longest first: one may hold another
            text = text.replace(value, self.known[value])
        text = _IPV4.sub(lambda m: mask_address(m.group()), text)
        text = _ACCOUNT_NUMBER.sub(lambda m: mask_id(m.group()), text)
        return _ACCOUNT_CODE.sub(lambda m: mask_id(m.group()), text)
