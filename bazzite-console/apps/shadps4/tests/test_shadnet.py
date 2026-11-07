# SPDX-License-Identifier: GPL-3.0-or-later
"""shadNet's protocol (shadnet.py) against a fake server: the requests as shadPS4 0.19.0 sends them, the answers and
errors, a server that is not shadNet or another version, and the server address and name rules."""

from __future__ import annotations

import pytest
from conftest import FakeShadNet

from shadps4_manager import shadnet
from shadps4_manager.shadnet import Server, ShadNetError

SERVER = Server("srv.example", 31313)


def test_create_an_account():
    fake = FakeShadNet()
    shadnet.create_account(SERVER, "Player_1", "pässword", "me@example.com", connect=fake.connect)
    assert fake.addresses == [("srv.example", 31313)]
    # Without a key none is sent, as protobuf leaves out an empty field.
    assert fake.requests == [(shadnet.CREATE, {1: "Player_1", 2: "pässword", 4: "me@example.com"})]
    keyed = FakeShadNet()
    shadnet.create_account(SERVER, "Player_1", "x", "me@example.com", "s3cret", connect=keyed.connect)
    assert keyed.requests[0][1][5] == "s3cret"


@pytest.mark.parametrize("error, says", [(23, "registration key"), (11, "name is taken"),
                                         (13, "email address exists"), (99, "error 99")])
def test_the_server_refuses_an_account(error, says):
    with pytest.raises(ShadNetError, match=says):
        shadnet.create_account(SERVER, "Player_1", "x", "me@example.com", connect=FakeShadNet(error).connect)


def test_try_a_sign_in():
    fake = FakeShadNet()
    shadnet.try_sign_in(SERVER, "Player_1", "secret", connect=fake.connect)
    assert fake.requests == [(shadnet.LOGIN, {1: "Player_1", 2: "secret"})]
    with pytest.raises(ShadNetError, match="password is wrong"):
        shadnet.try_sign_in(SERVER, "Player_1", "nope", connect=FakeShadNet(8).connect)


def test_not_shadnet_another_version_or_no_server():
    with pytest.raises(ShadNetError, match="not a shadNet server"):
        shadnet.try_sign_in(SERVER, "Player_1", "x", connect=FakeShadNet(first=1).connect)
    with pytest.raises(ShadNetError, match="another shadNet version"):
        shadnet.try_sign_in(SERVER, "Player_1", "x", connect=FakeShadNet(version=2).connect)

    def refused(address, timeout):
        raise ConnectionRefusedError(111, "Connection refused")
    with pytest.raises(ShadNetError, match="could not be reached: Connection refused"):
        shadnet.try_sign_in(SERVER, "Player_1", "x", connect=refused)


def test_a_packet_as_shadps4_builds_it():
    assert shadnet.packet(shadnet.LOGIN, 1, b"\x0a\x01a") == (
        b"\x00" + b"\x00\x00" + (15 + 4 + 3).to_bytes(4, "little") + (1).to_bytes(8, "little")
        + (3).to_bytes(4, "little") + b"\x0a\x01a")


def test_server_address_and_name():
    assert shadnet.parse_server("srv.shadps4.net:31313") == Server("srv.shadps4.net", 31313)
    assert shadnet.parse_server(" 192.168.1.20 ") == Server("192.168.1.20", 31313)
    for wrong in ("", ":31313", "host:port", "host:70000", "my host:31313"):
        with pytest.raises(ShadNetError):
            shadnet.parse_server(wrong)
    assert shadnet.check_npid("Player_1") == "" and shadnet.check_npid("a-b") == ""
    assert shadnet.check_npid("ab") and shadnet.check_npid("seventeen_letters") and shadnet.check_npid("a b c")


def test_the_server_answers_without_a_sign_in():
    fake = FakeShadNet()
    shadnet.server_answers(SERVER, connect=fake.connect)
    assert fake.addresses == [("srv.example", 31313)] and fake.requests == []      # nothing sent
    with pytest.raises(ShadNetError, match="another shadNet version"):
        shadnet.server_answers(SERVER, connect=FakeShadNet(version=2).connect)


# Lines of shadPS4 0.19.0's log (client.cpp), as its logger writes them.
LOGGED_IN = ("[ShadNet] <Info> (shadPS4:ShadNet) client.cpp:703 HandleLoginReply: Logged in npid='Player_1' userId=7 "
             "friends=0")
REJECTED = "[ShadNet] <Error> (shadPS4:ShadNet) client.cpp:740 HandleLoginReply: Login rejected error code 8"
DROPPED = "[ShadNet] <Warning> (ShadNet:Reader) client.cpp:226 ReaderThread: Reader header recv failed, disconnecting"
OTHER = "[Lib.Pad] <Info> (Game:Main) pad.cpp:346 scePadOpen: called user_id = 1000"


def test_shadps4s_session_from_its_newest_log(tmp_path):
    import os
    assert shadnet.session(tmp_path / "none") == ("", "")
    old, new = tmp_path / "shadps4.log", tmp_path / "CUSA11624.log"
    old.write_text(LOGGED_IN + "\n")
    new.write_text(OTHER + "\n")
    os.utime(old, (1, 1))
    assert shadnet.session(tmp_path) == ("", "")                                  # the newest has no sign-in yet
    new.write_text("\n".join([OTHER, LOGGED_IN, OTHER]))
    assert shadnet.session(tmp_path) == ("online", "Player_1")
    new.write_text("\n".join([LOGGED_IN, DROPPED]))
    assert shadnet.session(tmp_path) == ("offline", "shadPS4 lost the connection to the server")
    new.write_text(REJECTED)
    assert shadnet.session(tmp_path) == ("offline", "shadPS4's sign-in was refused: the password is wrong")
