# SPDX-License-Identifier: GPL-3.0-or-later

"""The SSH connection: host key handling, connecting, and the commands run on the server (sshd status, start, stop,
restart, sshd_config)."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import paramiko


SERVICE_COMMANDS = {
    "status": "systemctl show -p ActiveState --value sshd",
    "start": "sudo -n systemctl start sshd",
    "stop": "sudo -n systemctl stop sshd",
    "restart": "sudo -n systemctl restart sshd",
}


class UnknownHostKeyError(paramiko.SSHException):
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

    def missing_host_key(
        self,
        client: paramiko.SSHClient,
        hostname: str,
        key: paramiko.PKey,
    ) -> None:
        raise UnknownHostKeyError(self.host, self.port, key)


def save_trusted_host_key(error: UnknownHostKeyError) -> Path:
    ssh_directory = Path.home() / ".ssh"
    known_hosts = ssh_directory / "known_hosts"
    ssh_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        ssh_directory.chmod(0o700)

    host_keys = paramiko.HostKeys()
    if known_hosts.exists():
        host_keys.load(str(known_hosts))
    host_keys.add(error.known_hosts_name, error.key.get_name(), error.key)
    host_keys.save(str(known_hosts))
    if os.name != "nt":
        known_hosts.chmod(0o600)
    return known_hosts


def connect_ssh(
    host: str,
    port: int,
    username: str,
    password: str = "",
    key_filename: str = "",
    timeout: int = 10,
    compression: bool = True,
    keepalive_interval: int = 15,
    reconnect_count: int = 2,
    reconnect_delay: int = 5,
) -> paramiko.SSHClient:
    if not host.strip():
        raise ValueError("Enter a host name or IP address.")
    if not username.strip():
        raise ValueError("Enter a user name.")
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535.")

    last_error = None
    for attempt in range(reconnect_count + 1):
        try:
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(TrustOnRequestPolicy(host.strip(), port))
            client.connect(
                hostname=host.strip(),
                port=port,
                username=username.strip(),
                password=password or None,
                key_filename=key_filename or None,
                timeout=timeout,
                banner_timeout=timeout,
                auth_timeout=timeout,
                compress=compression,
            )
            if keepalive_interval > 0:
                client.get_transport().set_keepalive(keepalive_interval)
            return client
        except UnknownHostKeyError:
            # Host key errors should not retry
            if attempt > 0:
                # Clean up client before raising
                try:
                    client.close()
                except Exception:
                    pass
            raise
        except Exception as error:
            last_error = error
            client_to_close = locals().get('client')
            if client_to_close is not None:
                try:
                    client_to_close.close()
                except Exception:
                    pass

            # If we have retries left, wait and try again
            if attempt < reconnect_count:
                time.sleep(reconnect_delay)
            else:
                # No more retries, raise the last error
                raise

    # Fallback (should not reach here)
    if last_error:
        raise last_error
    raise RuntimeError("Connection failed")


def run_server_action(client: paramiko.SSHClient, action: str) -> str:
    try:
        command = SERVICE_COMMANDS[action]
    except KeyError:
        raise ValueError(f"Unsupported server action: {action}") from None

    _stdin, stdout, stderr = client.exec_command(command, timeout=15)
    output = stdout.read().decode("utf-8", errors="replace").strip()
    error = stderr.read().decode("utf-8", errors="replace").strip()
    exit_code = stdout.channel.recv_exit_status()
    if exit_code:
        raise RuntimeError(error or output or f"Remote command failed ({exit_code}).")
    return output


SSHD_CONFIG_PATH = "/etc/ssh/sshd_config"
_SAVE_SSHD_CONFIG = (
    'f=$(mktemp) && cat > "$f" && sudo -n sshd -t -f "$f" && '
    f"sudo -n cp -p {SSHD_CONFIG_PATH} {SSHD_CONFIG_PATH}.bak && "
    f'sudo -n install -m 600 -o root -g root "$f" {SSHD_CONFIG_PATH}; '
    'rc=$?; rm -f "$f"; exit $rc'
)


def _exec(client: paramiko.SSHClient, command: str, data: str = "") -> str:
    stdin, stdout, stderr = client.exec_command(command, timeout=30)
    if data:
        stdin.write(data)
    stdin.channel.shutdown_write()
    output = stdout.read().decode("utf-8", errors="replace")
    error = stderr.read().decode("utf-8", errors="replace").strip()
    exit_code = stdout.channel.recv_exit_status()
    if exit_code:
        raise RuntimeError(error or output.strip() or f"Remote command failed ({exit_code}).")
    return output


def read_sshd_config(client: paramiko.SSHClient) -> str:
    return _exec(client, f"cat {SSHD_CONFIG_PATH}")


def write_sshd_config(client: paramiko.SSHClient, content: str) -> None:
    """Validate with ``sshd -t``, back up the current file, then install."""
    if content and not content.endswith("\n"):
        content += "\n"
    _exec(client, _SAVE_SSHD_CONFIG, content)


def server_status_after_action(client: paramiko.SSHClient, action: str) -> str:
    if action != "status":
        run_server_action(client, action)
    return run_server_action(client, "status")


def validate_password_requirements(password: str) -> tuple[bool, str]:
    """(is_valid, error message). An empty password is fine: the connection then uses an SSH key only."""
    if not password:
        return True, ""

    errors = []
    if len(password) < 8:
        errors.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("at least 1 uppercase letter")
    if not re.search(r"[0-9]", password):
        errors.append("at least 1 number")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?.]", password):
        errors.append("at least 1 special character (!@#$%^&*()_+-=[]{}|;:,.<>?.)")

    if errors:
        return False, "Password must have: " + ", ".join(errors)
    return True, ""
