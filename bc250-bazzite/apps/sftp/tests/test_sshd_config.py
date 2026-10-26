# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from sftp_tools import connection


class Chan:
    def __init__(self, code):
        self.code = code

    def shutdown_write(self):
        pass

    def recv_exit_status(self):
        return self.code


class Stream:
    def __init__(self, data=b"", code=0):
        self.data, self.channel, self.written = data, Chan(code), ""

    def read(self):
        return self.data

    def write(self, text):
        self.written += text


class Client:
    def __init__(self, out=b"", err=b"", code=0):
        self.out, self.err, self.code = out, err, code
        self.commands, self.stdin = [], None

    def exec_command(self, command, timeout=None):
        self.commands.append(command)
        self.stdin = Stream()
        return self.stdin, Stream(self.out, self.code), Stream(self.err)


def test_read():
    c = Client(out=b"Port 22\n")
    assert connection.read_sshd_config(c) == "Port 22\n"


def test_write_validates_and_adds_newline():
    c = Client()
    connection.write_sshd_config(c, "Port 2222")
    assert c.stdin.written == "Port 2222\n"
    assert "sshd -t" in c.commands[0]


def test_write_failure_raises():
    c = Client(err=b"bad config", code=255)
    with pytest.raises(RuntimeError, match="bad config"):
        connection.write_sshd_config(c, "x")
