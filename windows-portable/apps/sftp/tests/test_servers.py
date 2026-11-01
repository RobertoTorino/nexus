# SPDX-License-Identifier: GPL-3.0-or-later
"""The servers remembered and the settings (servers.py): the newest first, never a password, one entry a server,
a value that cannot be read left out; a setting steps through its values, its first the default."""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from sftp_tools import servers
from sftp_tools.servers import Server


def settings(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "app.ini"), QSettings.Format.IniFormat)


def test_servers_are_remembered_newest_first(tmp_path):
    kept = settings(tmp_path)
    assert servers.servers(kept) == [] and servers.last(kept) == Server("")
    servers.remember(kept, Server("board", 22, "me"))
    servers.remember(kept, Server("nas", 2222, "admin", "C:/keys/id_ed25519"))
    servers.remember(kept, Server("BOARD", 22, "me", "C:/keys/board"))         # the same server, its key changed
    assert servers.servers(kept) == [Server("BOARD", 22, "me", "C:/keys/board"),
                                     Server("nas", 2222, "admin", "C:/keys/id_ed25519")]
    assert "password" not in str(kept.value(servers.SERVERS_KEY))
    servers.forget(kept, Server("nas", 2222, "admin"))
    assert [s.label for s in servers.servers(kept)] == ["me@BOARD"]
    for _ in range(servers.MOST + 2):
        servers.remember(kept, Server(f"host{_}"))
    assert len(servers.servers(kept)) == servers.MOST


def test_a_label_and_what_cannot_be_read(tmp_path):
    assert Server("nas", 2222, "admin").label == "admin@nas:2222" and Server("board").label == "board"
    kept = settings(tmp_path)
    kept.setValue(servers.SERVERS_KEY, '[{"host": "ok"}, {"host": 3}, {"host": "x", "port": 99999}, "no"]')
    assert servers.servers(kept) == [Server("ok")]
    kept.setValue(servers.SERVERS_KEY, "not json")
    assert servers.servers(kept) == []
    servers.keep_last(kept, Server("board", 22, "me"))
    assert servers.last(kept) == Server("board", 22, "me")


def test_a_setting_steps_through_its_values(tmp_path):
    kept = settings(tmp_path)
    assert servers.EXISTS.value(kept) == "skip"
    assert servers.EXISTS.shown(kept) == "If a file is there already: Skip it"
    assert servers.EXISTS.step(kept) == "overwrite" and servers.EXISTS.step(kept) == "skip"
    assert [servers.LIMIT.step(kept) for _ in range(5)] == ["1024", "5120", "10240", "51200", "0"]
    kept.setValue("settings/hidden", "maybe")
    assert servers.HIDDEN.value(kept) == "off"
