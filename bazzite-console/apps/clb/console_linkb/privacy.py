# SPDX-License-Identifier: GPL-3.0-or-later
"""Personal details hidden in the window and the log: the account's tokens, the gamertag, the consoles' IDs and
network addresses.

A token is never shown, not even in part. A console ID keeps its last 4 characters (F4001234ABCD5678 shows as
••••••••••••5678), enough to tell two consoles apart. The gamertag is a name, so it is hidden whole where it is
logged; the window shows it to the person signed in. mask() hides the values it was told about and, in free text,
anything that looks like a token, an IPv4 or IPv6 address, so a line it was not told about is covered too."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable

DOT = "•"
KEEP = 4                                    # characters of a console ID that stay visible
NAME_MASK = DOT * 6                         # a gamertag, whatever its length
TOKEN_MASK = "[token]"

_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d]|\.\d)")
_IPV6 = re.compile(r"(?<![0-9A-Fa-f:])[0-9A-Fa-f]*:[0-9A-Fa-f:]*:[0-9A-Fa-f:]*(?![0-9A-Fa-f:])")   # checked below
# JWTs (parts joined by dots) and the other tokens (long runs of base64 and URL-safe base64)
_B64 = r"[A-Za-z0-9_\-+/=]"
_TOKEN = re.compile(rf"(?<![A-Za-z0-9_\-.+/=])(?:{_B64}{{16,}}(?:\.{_B64}{{8,}})+|{_B64}{{40,}})")
_CONSOLE_ID = re.compile(r"(?<![0-9A-F])F[0-9A-F]{15}(?![0-9A-F])")


def _ipv6(match: re.Match) -> str:
    try:
        ipaddress.IPv6Address(match.group(0))
    except ValueError:
        return match.group(0)                           # a time (22:49:04) or other text with colons
    return DOT * 3


def mask_id(text: str) -> str:
    """A console ID with only its last 4 characters."""
    text = text.strip()
    if len(text) <= KEEP:
        return DOT * len(text)
    return DOT * (len(text) - KEEP) + text[-KEEP:]


def mask(text: str, names: Iterable[str] = (), ids: Iterable[str] = ()) -> str:
    """*text* with the *names* (gamertags) and *ids* (console IDs) hidden, and every token, console ID and network
    address in it too."""
    for name in names:
        if name:
            text = text.replace(name, NAME_MASK)
    for value in ids:
        if value:
            text = text.replace(value, mask_id(value))
    text = _TOKEN.sub(TOKEN_MASK, text)
    text = _CONSOLE_ID.sub(lambda m: mask_id(m.group(0)), text)
    text = _IPV6.sub(_ipv6, text)
    return _IPV4.sub(lambda m: f"{DOT * 3}.{DOT * 3}.{DOT * 3}." + m.group(0).rsplit(".", 1)[1], text)
