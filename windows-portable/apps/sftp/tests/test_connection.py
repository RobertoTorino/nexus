# SPDX-License-Identifier: GPL-3.0-or-later
"""The connection (connection.py): the BC250 app's password rules, the server's key shown as ssh shows it and kept
in known_hosts only when trusted, the fields checked before connecting, the login's home, and sshd's commands."""

from __future__ import annotations

import base64
import hashlib

import paramiko
import pytest

from fake_sftp import FakeClient, FakeSFTP
from sftp_tools import connection


@pytest.fixture(scope="module")
def key():
    return paramiko.ECDSAKey.generate()


def test_the_password_rules_are_the_bc250_apps():
    assert connection.check_password("") == ""                          # no password: the key or the agent
    assert connection.check_password("Secret#42x") == ""
    assert connection.check_password("abc") == ("The password needs 8 characters, a capital, a number and a special "
                                                "character.")
    assert connection.check_password("abcdefgh1!") == "The password needs a capital."


def test_the_fingerprint_is_ssh_s(key):
    digest = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
    assert connection.fingerprint(key) == f"ECDSA SHA256:{digest}"


def test_a_trusted_key_is_kept_in_known_hosts(tmp_path, key):
    known = tmp_path / ".ssh" / "known_hosts"
    connection.save_trusted_host_key(connection.UnknownHostKeyError("192.168.1.20", 22, key), known)
    connection.save_trusted_host_key(connection.UnknownHostKeyError("board", 2222, key), known)
    kept = paramiko.HostKeys(str(known))
    assert kept.lookup("192.168.1.20")[key.get_name()] == key
    assert kept.lookup("[board]:2222")[key.get_name()] == key


@pytest.mark.parametrize("host, port, user, said", [
    ("", 22, "me", "Fill in the host first"),
    ("board", 22, " ", "Fill in the user name first"),
    ("board", 0, "me", "The port is a number from 1 to 65535"),
])
def test_the_fields_are_checked_before_connecting(host, port, user, said):
    with pytest.raises(ValueError, match=said):
        connection.connect_ssh(host, port, user)


def test_the_home_is_bazzites(tmp_path):
    sftp = FakeSFTP(tmp_path, home="/home/me")
    assert connection.remote_home(sftp) == "/var/home/me"       # /home links to /var/home on Bazzite
    assert connection.remote_home(FakeSFTP(tmp_path, home="/srv/files")) == "/srv/files"


def test_sshd_is_started_and_its_state_read(tmp_path):
    client = FakeClient(tmp_path, {connection.SERVICE_COMMANDS["status"]: ("active\n", "", 0)})
    assert connection.server_action(client, "start") == "active"
    assert client.commands == [connection.SERVICE_COMMANDS["start"], connection.SERVICE_COMMANDS["status"]]
    assert connection.SERVICE_COMMANDS["start"].startswith("sudo -n ")      # never asks for a password


def test_a_refused_command_says_why(tmp_path):
    client = FakeClient(tmp_path, {connection.SERVICE_COMMANDS["stop"]: ("", "sudo: a password is required", 1)})
    with pytest.raises(RuntimeError, match="a password is required"):
        connection.server_action(client, "stop")
    with pytest.raises(ValueError):
        connection.server_action(client, "restart")
