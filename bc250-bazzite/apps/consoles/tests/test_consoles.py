# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import stat

import pytest

from consoles_link.consoles import (ConsoleStore, RegisteredConsole, format_account_id, parse_account_id,
                                        parse_login_pin, parse_pin)
from consoles_link.target import Target

CONSOLE = RegisteredConsole(host_id="AABBCCDDEEFF", nickname="Living room", address="192.168.1.20",
                            target=Target.PS5_1, regist_key=b"1a2b3c4d", rp_key=bytes(range(16)),
                            mac=bytes.fromhex("0cfe45a1b2c3"), rp_key_type=2)


def test_store_round_trip_and_mode(tmp_path):
    store = ConsoleStore(tmp_path / "bc250-console-link")
    store.put(CONSOLE)
    assert store.load() == [CONSOLE]
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_put_replaces_the_same_console(tmp_path):
    store = ConsoleStore(tmp_path)
    store.put(CONSOLE)
    moved = RegisteredConsole(**{**CONSOLE.__dict__, "address": "192.168.1.30"})
    assert store.put(moved) == [moved]


def test_remove(tmp_path):
    store = ConsoleStore(tmp_path)
    store.put(CONSOLE)
    assert store.remove(CONSOLE.key) == [] and store.load() == []


def test_a_broken_file_or_entry_is_skipped(tmp_path):
    store = ConsoleStore(tmp_path)
    store.path.write_text("not json")
    assert store.load() == []
    store.path.write_text('{"consoles": [{"address": "x"}, ' + __import__("json").dumps(CONSOLE.to_json()) + "]}")
    assert store.load() == [CONSOLE]


def test_key_falls_back_to_the_mac():
    assert RegisteredConsole(**{**CONSOLE.__dict__, "host_id": ""}).key == "0cfe45a1b2c3"


@pytest.mark.parametrize("text, raw", [
    ("AAECAwQFBgc=", bytes(range(8))),
    ("506097152", (506097152).to_bytes(8, "little")),
    (" 4782394583276428394 ", (4782394583276428394).to_bytes(8, "little")),
])
def test_account_id_forms(text, raw):
    assert parse_account_id(text) == raw


@pytest.mark.parametrize("text", ["", "abc", "0", str(1 << 64), "AAECAwQFBg==", "my_online_name"])
def test_bad_account_ids(text):
    with pytest.raises(ValueError):
        parse_account_id(text)


def test_account_id_round_trip():
    assert parse_account_id(format_account_id(bytes(range(8)))) == bytes(range(8))


def test_pins():
    assert parse_pin("1234 5678") == 12345678
    with pytest.raises(ValueError):
        parse_pin("1234567")
    assert parse_login_pin("") == "" and parse_login_pin("0420") == "0420"
    with pytest.raises(ValueError):
        parse_login_pin("12a4")


def test_settings_of_the_former_name_move_once(tmp_path):
    from consoles_link.consoles import migrate_old_config
    old = tmp_path / "bc250-remote-play"
    old.mkdir()
    (old / "consoles.json").write_text('{"consoles": []}')
    (old / "consoles.json").chmod(0o600)
    (old / "bc250-remote-play.ini").write_text("[General]\naccount_id=x\n")
    assert migrate_old_config(tmp_path, "bc250-console-link")
    new = tmp_path / "bc250-console-link"
    assert not old.exists() and (new / "consoles.json").stat().st_mode & 0o777 == 0o600
    assert (new / "bc250-console-link.ini").read_text().endswith("account_id=x\n")
    # Once: a new folder is never overwritten.
    old.mkdir()
    (old / "consoles.json").write_text("older")
    assert not migrate_old_config(tmp_path, "bc250-console-link")
    assert (new / "consoles.json").read_text() == '{"consoles": []}'
