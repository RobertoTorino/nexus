# SPDX-License-Identifier: GPL-3.0-or-later
"""Masking of personal data in the GUI's saved logs.

The terminal always shows the full output; only what is written to disk is masked. Values known on
this machine (host name, user name, home folder, drive serials, MAC addresses, machine id) are
replaced literally, and patterns catch the rest (IP and MAC addresses of other devices, serial
numbers in tool output, the speed test's ISP and result URL).
"""

from __future__ import annotations

import getpass
import os
import re
import socket
from pathlib import Path

_KEEP_IPV4 = ("127.", "0.0.0.0", "255.255.255.255")
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.]|\.\d)")
_MAC = re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![\w:])")
# Needs 3+ colons or a '::' so clock times (07:01:13) are left alone.
_IPV6 = re.compile(r"(?<![\w:])(?:(?:[0-9A-Fa-f]{1,4}:){3,7}[0-9A-Fa-f]{1,4}"
                   r"|(?:[0-9A-Fa-f]{1,4}:){1,6}:(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4})*)?)(?![\w:])")
_SERIAL = re.compile(r"(?i)(\"?serial(?:[ _]?number|_no)?\"?\s*[:=]\s*\"?)([A-Za-z0-9._-]{4,})")
_ISP = re.compile(r"(ISP: )[^;]+")
_RESULT_URL = re.compile(r"https://www\.speedtest\.net/result/\S+")
_ENV_USER = re.compile(r"(SUDO_USER=|USER=|LOGNAME=)(?!root\b)[^\s;]+")
_HOME_PATH = re.compile(r"(/(?:var/)?home/)[^/\s]+")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _machine_secrets() -> dict[str, str]:
    """Literal values of this machine -> replacement text."""
    found: dict[str, str] = {}
    for p in [*Path("/sys/class/nvme").glob("*/serial"), *Path("/sys/block").glob("*/device/serial"),
              *(Path("/sys/class/dmi/id") / n for n in ("product_serial", "board_serial", "chassis_serial",
                                                         "product_uuid"))]:
        value = _read(p)
        if len(value) >= 4 and value.lower() not in ("none", "default string", "to be filled by o.e.m."):
            found[value] = "<serial>"
    for p in Path("/sys/class/net").glob("*/address"):
        value = _read(p)
        if value and value != "00:00:00:00:00:00":
            found[value] = "<mac>"
    machine_id = _read(Path("/etc/machine-id"))
    if machine_id:
        found[machine_id] = "<machine-id>"
    return found


def _names() -> set[str]:
    names = set()
    for name in (socket.gethostname(), socket.gethostname().split(".")[0], getpass.getuser(),
                 os.environ.get("SUDO_USER", "")):
        if len(name) >= 3 and name not in ("root", "localhost", "localhost.localdomain"):
            names.add(name)
    return names


class Redactor:
    def __init__(self) -> None:
        self.home = str(Path.home())
        secrets = _machine_secrets()
        self._literals = sorted(secrets.items(), key=lambda kv: -len(kv[0]))
        names = sorted(_names(), key=len, reverse=True)
        # Whole words only, and not inside paths or names such as bc250-bazzite-test or bazzite:stable.
        self._names = (re.compile(r"(?<![\w.\-/:@])(?:" + "|".join(map(re.escape, names)) + r")(?![\w\-/:])")
                       if names else None)
        self._user_at = (re.compile(r"(?<=\w@)(?:" + "|".join(map(re.escape, names)) + r")\b") if names else None)

    def __call__(self, line: str) -> str:
        if self.home and self.home != "/":
            line = line.replace(self.home, "~")
        for value, mask in self._literals:
            line = line.replace(value, mask)
        line = _HOME_PATH.sub(r"\1<name>", line)
        if self._names:
            line = self._user_at.sub("<name>", line)
            line = self._names.sub("<name>", line)
        line = _ENV_USER.sub(r"\1<name>", line)
        line = _SERIAL.sub(lambda m: m.group(1) + "<serial>", line)
        line = _MAC.sub("<mac>", line)
        line = _IPV6.sub("<ip>", line)
        line = _IPV4.sub(lambda m: m.group(0) if m.group(0).startswith(_KEEP_IPV4) else "<ip>", line)
        line = _ISP.sub(r"\1<isp>", line)
        return _RESULT_URL.sub("<result-url>", line)
