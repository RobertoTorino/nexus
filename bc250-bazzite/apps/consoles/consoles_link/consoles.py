# SPDX-License-Identifier: AGPL-3.0-or-later
"""The consoles the board is registered with, and the input the window takes for registering: the PSN account ID,
the console's PIN and the optional login passcode.

The keys a console hands out at registration let anyone on the network start a session as this account, so they
live in their own file, readable only by the user: ~/.config/bc250-console-link/consoles.json (mode 0600)."""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .regist import Registration
from .stream_options import StreamOptions
from .target import Target

FILE_NAME = "consoles.json"


@dataclass(frozen=True)
class RegisteredConsole:
    host_id: str                        # from discovery; "" when registered by address only
    nickname: str
    address: str
    target: Target
    regist_key: bytes
    rp_key: bytes
    mac: bytes = b""
    rp_key_type: int = 0
    login_pin: str = ""
    options: StreamOptions = StreamOptions()   # the stream settings (stream_options.py)

    @property
    def ps5(self) -> bool:
        return self.target.ps5

    @property
    def key(self) -> str:
        """Identifies the console in the file: its host id, else its MAC address."""
        return self.host_id or self.mac.hex()

    @classmethod
    def from_registration(cls, registration: Registration, address: str, host_id: str = "") -> RegisteredConsole:
        return cls(host_id=host_id, nickname=registration.nickname, address=address, target=registration.target,
                   regist_key=registration.regist_key, rp_key=registration.rp_key, mac=registration.mac,
                   rp_key_type=registration.rp_key_type)

    def to_json(self) -> dict:
        data = asdict(self)
        data["target"] = int(self.target)
        for name in ("regist_key", "rp_key", "mac"):
            data[name] = getattr(self, name).hex()
        data["options"] = self.options.to_json()
        return data

    @classmethod
    def from_json(cls, data: dict) -> RegisteredConsole:
        return cls(host_id=str(data.get("host_id", "")), nickname=str(data.get("nickname", "")),
                   address=str(data["address"]), target=Target(int(data["target"])),
                   regist_key=bytes.fromhex(data["regist_key"]), rp_key=bytes.fromhex(data["rp_key"]),
                   mac=bytes.fromhex(data.get("mac", "")), rp_key_type=int(data.get("rp_key_type", 0)),
                   login_pin=str(data.get("login_pin", "")),
                   options=StreamOptions.from_json(data.get("options")))


class ConsoleStore:
    def __init__(self, folder: Path):
        self.path = folder / FILE_NAME

    def load(self) -> list[RegisteredConsole]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError):
            return []
        consoles = []
        for entry in data.get("consoles", []) if isinstance(data, dict) else []:
            try:
                consoles.append(RegisteredConsole.from_json(entry))
            except (KeyError, TypeError, ValueError):
                continue                                # one broken entry does not hide the others
        return consoles

    def save(self, consoles: list[RegisteredConsole]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"consoles": [console.to_json() for console in consoles]}, indent=2) + "\n"
        temp = self.path.with_suffix(".tmp")
        # Created 0600 from the start, so the keys are never readable by others, not even for a moment.
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(temp, 0o600)
        os.replace(temp, self.path)

    def put(self, console: RegisteredConsole) -> list[RegisteredConsole]:
        """Add or replace (same console: same key) and save; returns the new list."""
        consoles = [c for c in self.load() if c.key != console.key]
        consoles.append(console)
        self.save(consoles)
        return consoles

    def remove(self, key: str) -> list[RegisteredConsole]:
        consoles = [c for c in self.load() if c.key != key]
        self.save(consoles)
        return consoles


OLD_APP_ID = "bc250-remote-play"         # the app's name until 13-10-2026: BC250 Remote Play


def migrate_old_config(config_home: Path, app_id: str) -> bool:
    """Moves the settings and registered consoles of BC250 Remote Play (the app's former name) to this app's
    folder, once: only when the new folder does not exist yet. True when something moved."""
    old, new = config_home / OLD_APP_ID, config_home / app_id
    if not old.is_dir() or new.exists():
        return False
    old.rename(new)
    old_ini = new / f"{OLD_APP_ID}.ini"
    if old_ini.exists():
        old_ini.rename(new / f"{app_id}.ini")
    return True


def parse_account_id(text: str) -> bytes:
    """The PSN account ID as the 8 bytes registration sends: either the number PSN gives (decimal) or that number
    already encoded the way the reference shows it (base64 of the 8 bytes, little-endian, e.g. "AAECAwQFBgc=")."""
    text = text.strip()
    if text.isdigit():
        value = int(text)
        if not 0 < value < 1 << 64:
            raise ValueError("The account ID number is out of range.")
        return value.to_bytes(8, "little")
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raw = b""
    if len(raw) != 8:
        raise ValueError("Enter the PSN account ID as a number, or as the 12-character code that ends with '='.")
    return raw


def format_account_id(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def parse_pin(text: str) -> int:
    text = text.strip().replace(" ", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError("The PIN has 8 digits: the console shows it under Link Device (PS5) or Add Device (PS4).")
    return int(text)


def parse_login_pin(text: str) -> str:
    text = text.strip()
    if text and (len(text) != 4 or not text.isdigit()):
        raise ValueError("The login passcode has 4 digits (leave it empty when the account has none).")
    return text
