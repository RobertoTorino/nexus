# SPDX-License-Identifier: GPL-3.0-or-later
"""The SSH connection, as the BC250 suite's SFTP Tools makes it: the server's key checked against known_hosts (a new
one trusted only when asked), connecting with a password or a key, and the commands run on the server (sshd's state,
start, stop, its sshd_config read). Qt-free.

known_hosts is %USERPROFILE%\\.ssh\\known_hosts, the one Windows' own OpenSSH client uses; the app adds a key to it
only when the person trusts it, and never removes one."""

from __future__ import annotations

import base64
import hashlib
import posixpath
import re
from pathlib import Path

import paramiko

TIMEOUT = 10                    # s: the connection, the server's banner and the login
KEEPALIVE = 15                  # s between keep-alives on an idle connection

SERVICE_COMMANDS = {
    "status": "systemctl show -p ActiveState --value sshd",
    "start": "sudo -n systemctl start sshd",
    "stop": "sudo -n systemctl stop sshd",
}
SSHD_CONFIG_PATH = "/etc/ssh/sshd_config"
# The password rules of the BC250 app (connection.validate_password_requirements): a password without a key
SPECIAL = r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?.]"


def known_hosts_file(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".ssh" / "known_hosts"


class UnknownHostKeyError(paramiko.SSHException):
    """The server's key is not in known_hosts: the app shows its fingerprint and connects once it is trusted."""

    def __init__(self, host: str, port: int, key: paramiko.PKey) -> None:
        super().__init__(f"Server {host} is not in known_hosts.")
        self.host = host
        self.port = port
        self.key = key

    @property
    def known_hosts_name(self) -> str:
        if self.port == 22:
            return self.host
        return f"[{self.host}]:{self.port}"


class TrustOnRequestPolicy(paramiko.MissingHostKeyPolicy):
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    def missing_host_key(self, client: paramiko.SSHClient, hostname: str, key: paramiko.PKey) -> None:
        raise UnknownHostKeyError(self.host, self.port, key)


def fingerprint(key: paramiko.PKey) -> str:
    """The key as ssh shows it: its type and SHA256:<base64>, the line to compare with the server's own
    (ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub on the server)."""
    digest = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode("ascii").rstrip("=")
    kind = key.get_name().removeprefix("ssh-").split("-")[0].upper()       # ED25519, RSA, ECDSA
    return f"{kind} SHA256:{digest}"


def save_trusted_host_key(error: UnknownHostKeyError, known_hosts: Path | None = None) -> Path:
    """The server's key added to known_hosts (made when missing); the file."""
    known_hosts = known_hosts or known_hosts_file()
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    host_keys = paramiko.HostKeys()
    if known_hosts.exists():
        host_keys.load(str(known_hosts))
    host_keys.add(error.known_hosts_name, error.key.get_name(), error.key)
    host_keys.save(str(known_hosts))
    return known_hosts


def check_password(password: str) -> str:
    """What a password without a key still needs, "" when it is fine (an empty one is: the connection then uses the
    default keys and the SSH agent). The BC250 app's rules: 8 characters, a capital, a number and a special
    character."""
    if not password:
        return ""
    missing = []
    if len(password) < 8:
        missing.append("8 characters")
    if not re.search(r"[A-Z]", password):
        missing.append("a capital")
    if not re.search(r"[0-9]", password):
        missing.append("a number")
    if not re.search(SPECIAL, password):
        missing.append("a special character")
    if not missing:
        return ""
    listed = missing[0] if len(missing) == 1 else f"{', '.join(missing[:-1])} and {missing[-1]}"
    return f"The password needs {listed}."


def connect_ssh(host: str, port: int, username: str, password: str = "", key_filename: str = "",
                compression: bool = True, known_hosts: Path | None = None,
                timeout: int = TIMEOUT) -> paramiko.SSHClient:
    """The connection, logged in; UnknownHostKeyError for a server whose key is not trusted yet. With a key, the
    password is its passphrase."""
    if not host.strip():
        raise ValueError("Fill in the host first: its name or IP address.")
    if not username.strip():
        raise ValueError("Fill in the user name first.")
    if not 1 <= port <= 65535:
        raise ValueError("The port is a number from 1 to 65535.")
    client = paramiko.SSHClient()
    known_hosts = known_hosts or known_hosts_file()
    if known_hosts.is_file():
        client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(TrustOnRequestPolicy(host.strip(), port))
    try:
        client.connect(hostname=host.strip(), port=port, username=username.strip(), password=password or None,
                       key_filename=key_filename or None, timeout=timeout, banner_timeout=timeout,
                       auth_timeout=timeout, compress=compression)
    except Exception:
        client.close()
        raise
    transport = client.get_transport()
    if transport is not None:
        transport.set_keepalive(KEEPALIVE)
    return client


def remote_home(sftp: paramiko.SFTPClient) -> str:
    """Where the server's files start: the login's home (/var/home/<user> on Bazzite, where /home links to)."""
    try:
        home = sftp.normalize(".")
    except OSError:
        return "/"
    if home.startswith("/home/"):
        home = "/var" + home
    return posixpath.normpath(home) if home else "/"


def _exec(client: paramiko.SSHClient, command: str) -> str:
    _stdin, stdout, stderr = client.exec_command(command, timeout=30)
    output = stdout.read().decode("utf-8", errors="replace")
    error = stderr.read().decode("utf-8", errors="replace").strip()
    exit_code = stdout.channel.recv_exit_status()
    if exit_code:
        raise RuntimeError(error or output.strip() or f"The server's command failed ({exit_code}).")
    return output


def server_action(client: paramiko.SSHClient, action: str) -> str:
    """sshd started or stopped (*action*), then its state as systemd says it: active, inactive, failed. The steps
    need sudo without a password on the server (sudo -n): when it asks for one, the error says so and nothing
    changes."""
    if action not in SERVICE_COMMANDS:
        raise ValueError(f"Unsupported server action: {action}")
    if action != "status":
        _exec(client, SERVICE_COMMANDS[action])
    return _exec(client, SERVICE_COMMANDS["status"]).strip()


def read_sshd_config(client: paramiko.SSHClient) -> str:
    return _exec(client, f"cat {SSHD_CONFIG_PATH}")
