# SPDX-License-Identifier: GPL-3.0-or-later
"""A server for the tests without a network: FakeSFTP is paramiko's SFTPClient on a folder (the server's / is
*root*), FakeClient the SSH connection with its commands answered from a table."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import paramiko


class FakeSFTP:
    def __init__(self, root: Path, home: str = "/var/home/me"):
        self.root, self.home = root, home
        self.closed = False
        (root / home.lstrip("/")).mkdir(parents=True, exist_ok=True)

    def local(self, path: str) -> Path:
        return self.root / path.lstrip("/")

    def normalize(self, path: str) -> str:
        return self.home if path == "." else path

    def stat(self, path: str) -> paramiko.SFTPAttributes:
        return paramiko.SFTPAttributes.from_stat(os.stat(self.local(path)), Path(path).name)

    def lstat(self, path: str) -> paramiko.SFTPAttributes:
        return paramiko.SFTPAttributes.from_stat(os.lstat(self.local(path)), Path(path).name)

    def listdir_attr(self, path: str) -> list[paramiko.SFTPAttributes]:
        folder = self.local(path)
        if not folder.is_dir():
            raise FileNotFoundError(2, "No such file", path)
        return [paramiko.SFTPAttributes.from_stat(os.lstat(child), child.name) for child in sorted(folder.iterdir())]

    def mkdir(self, path: str) -> None:
        self.local(path).mkdir()

    def put(self, local: str, remote: str, callback=None) -> None:
        shutil.copyfile(local, self.local(remote))
        size = os.path.getsize(local)
        if callback is not None:
            callback(size, size)

    def get(self, remote: str, local: str, callback=None) -> None:
        shutil.copyfile(self.local(remote), local)
        size = os.path.getsize(local)
        if callback is not None:
            callback(size, size)

    def remove(self, path: str) -> None:
        self.local(path).unlink()

    def rmdir(self, path: str) -> None:
        self.local(path).rmdir()

    def close(self) -> None:
        self.closed = True


class _Channel:
    def __init__(self, code: int):
        self.code = code

    def recv_exit_status(self) -> int:
        return self.code

    def shutdown_write(self) -> None:
        pass


class _Stream:
    def __init__(self, text: str = "", code: int = 0):
        self.text, self.channel = text, _Channel(code)

    def read(self) -> bytes:
        return self.text.encode()

    def write(self, data) -> None:
        pass


class FakeTransport:
    def __init__(self):
        self.active = True

    def is_active(self) -> bool:
        return self.active

    def set_keepalive(self, _seconds: int) -> None:
        pass


class FakeClient:
    """The connection: open_sftp() on *root*, and exec_command() answered from *answers* (command: (output, error,
    exit code)); every command run is in *commands*."""

    def __init__(self, root: Path, answers: dict[str, tuple[str, str, int]] | None = None):
        self.root = root
        self.answers = answers or {}
        self.commands: list[str] = []
        self.transport = FakeTransport()
        self.channels: list[FakeSFTP] = []

    def open_sftp(self) -> FakeSFTP:
        channel = FakeSFTP(self.root)
        self.channels.append(channel)
        return channel

    def get_transport(self) -> FakeTransport:
        return self.transport

    def exec_command(self, command: str, timeout: int = 0):
        self.commands.append(command)
        output, error, code = self.answers.get(command, ("", "", 0))
        return _Stream(), _Stream(output, code), _Stream(error, code)

    def close(self) -> None:
        self.transport.active = False
