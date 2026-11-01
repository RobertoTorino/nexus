# SPDX-License-Identifier: GPL-3.0-or-later
"""The servers connected to before, the newest first, as the BC250 app's profiles keep them: the host, the port, the
user name and the key, never a password or a passphrase. A server is remembered when a connection to it works (on a
handheld, typing a profile's name is the hard way), and forgotten on request. They are kept in the app's settings
(%APPDATA%\\windows-portable-suite\\windows-portable-sftp.ini), under servers.

And the app's settings, the BC250 app's that a handheld needs, each a row whose A steps to its next value."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

SERVERS_KEY = "servers"
LAST_KEY = "connection"         # the fields as they were last left: host, port, user, key
MOST = 6                        # servers remembered


@dataclass(frozen=True)
class Server:
    host: str
    port: int = 22
    user: str = ""
    key: str = ""               # a private key's path, "" for the default keys and the SSH agent

    @property
    def label(self) -> str:
        """user@host, :port when not 22."""
        where = self.host if self.port == 22 else f"{self.host}:{self.port}"
        return f"{self.user}@{where}" if self.user else where

    def same(self, other: "Server") -> bool:
        return (self.host.casefold(), self.port, self.user) == (other.host.casefold(), other.port, other.user)


def _parse(value: object) -> Server | None:
    if not isinstance(value, dict):
        return None
    host, port, user, key = value.get("host"), value.get("port", 22), value.get("user", ""), value.get("key", "")
    if not isinstance(host, str) or not host or not isinstance(port, int) or isinstance(port, bool) \
            or not isinstance(user, str) or not isinstance(key, str) or not 1 <= port <= 65535:
        return None
    return Server(host, port, user, key)


def _load(settings, name: str) -> object:
    try:
        return json.loads(str(settings.value(name, "") or "null"))
    except ValueError:
        return None


def servers(settings) -> list[Server]:
    """The servers remembered, the newest first; a value that cannot be read is left out."""
    data = _load(settings, SERVERS_KEY)
    found = [_parse(item) for item in data] if isinstance(data, list) else []
    return [server for server in found if server is not None]


def _save(settings, kept: list[Server]) -> None:
    settings.setValue(SERVERS_KEY, json.dumps([asdict(server) for server in kept[:MOST]]))


def remember(settings, server: Server) -> None:
    """*server* first, an older entry of it gone."""
    _save(settings, [server, *(other for other in servers(settings) if not other.same(server))])


def forget(settings, server: Server) -> None:
    _save(settings, [other for other in servers(settings) if not other.same(server)])


def last(settings) -> Server:
    """The fields as they were left (an empty host the first time)."""
    return _parse(_load(settings, LAST_KEY)) or Server("")


def keep_last(settings, server: Server) -> None:
    settings.setValue(LAST_KEY, json.dumps(asdict(server)))


@dataclass(frozen=True)
class Setting:
    """A row of the Settings pane: its key in the settings, its label and its values with their text, the first the
    default."""
    key: str
    label: str
    values: tuple[tuple[str, str], ...]

    def value(self, settings) -> str:
        value = str(settings.value(f"settings/{self.key}", self.values[0][0]))
        return value if value in dict(self.values) else self.values[0][0]

    def shown(self, settings) -> str:
        return f"{self.label}: {dict(self.values)[self.value(settings)]}"

    def step(self, settings) -> str:
        """The next value, kept; the new one."""
        keys = [key for key, _text in self.values]
        value = keys[(keys.index(self.value(settings)) + 1) % len(keys)]
        settings.setValue(f"settings/{self.key}", value)
        return value


EXISTS = Setting("exists", "If a file is there already", (("skip", "Skip it"), ("overwrite", "Overwrite it")))
HIDDEN = Setting("hidden", "Hidden files", (("off", "Not shown"), ("on", "Shown")))
LIMIT = Setting("limit", "Speed limit", (("0", "None"), ("1024", "1 MB/s"), ("5120", "5 MB/s"),
                                         ("10240", "10 MB/s"), ("51200", "50 MB/s")))
TIMES = Setting("times", "Downloaded files", (("keep", "The server's times"), ("now", "The download's time")))
COMPRESSION = Setting("compression", "Compression", (("on", "On"), ("off", "Off")))
SOUND = Setting("sound", "Sound when a transfer is done", (("on", "On"), ("off", "Off")))
SETTINGS = (EXISTS, HIDDEN, LIMIT, TIMES, COMPRESSION, SOUND)
