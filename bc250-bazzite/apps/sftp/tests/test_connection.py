# SPDX-License-Identifier: GPL-3.0-or-later

from unittest.mock import Mock, patch

import paramiko
import pytest

from sftp_tools.connection import (
    TrustOnRequestPolicy,
    UnknownHostKeyError,
    connect_ssh,
    run_server_action,
    save_trusted_host_key,
)


def test_connect_ssh_uses_strict_host_key_checking() -> None:
    client = Mock()
    with patch("sftp_tools.connection.paramiko.SSHClient", return_value=client):
        result = connect_ssh(" example.test ", 2222, " user ")

    assert result is client
    client.load_system_host_keys.assert_called_once_with()
    client.set_missing_host_key_policy.assert_called_once()
    assert isinstance(
        client.set_missing_host_key_policy.call_args.args[0],
        TrustOnRequestPolicy,
    )
    client.connect.assert_called_once_with(
        hostname="example.test",
        port=2222,
        username="user",
        password=None,
        key_filename=None,
        timeout=10,
        banner_timeout=10,
        auth_timeout=10,
        compress=True,
    )
    # Verify set_keepalive is called with default interval (15 seconds)
    client.get_transport().set_keepalive.assert_called_once_with(15)


def test_connect_ssh_compression_is_negotiated_by_connect_only() -> None:
    # paramiko negotiates zlib from connect(compress=True); the transport's security options take only a tuple
    # or list, and changing them after the handshake has no effect.
    client = Mock()
    client.get_transport.return_value.get_security_options.return_value = paramiko.SecurityOptions(Mock())
    with patch("sftp_tools.connection.paramiko.SSHClient", return_value=client):
        assert connect_ssh("example.test", 22, "user", compression=True) is client

    assert client.connect.call_args.kwargs["compress"] is True


@pytest.mark.parametrize(
    ("host", "port", "known_hosts_name"),
    [
        ("example.test", 22, "example.test"),
        ("example.test", 2200, "[example.test]:2200"),
    ],
)
def test_unknown_host_policy_reports_identity_and_key(
    host: str, port: int, known_hosts_name: str
) -> None:
    key = paramiko.RSAKey.generate(1024)
    policy = TrustOnRequestPolicy(host, port)

    with pytest.raises(UnknownHostKeyError) as error:
        policy.missing_host_key(Mock(), host, key)

    assert error.value.known_hosts_name == known_hosts_name
    assert error.value.key == key


def test_save_trusted_host_key_adds_key_to_user_known_hosts(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    key = paramiko.RSAKey.generate(1024)
    error = UnknownHostKeyError("example.test", 2200, key)

    known_hosts = save_trusted_host_key(error)

    host_keys = paramiko.HostKeys(str(known_hosts))
    assert host_keys.lookup("[example.test]:2200")["ssh-rsa"] == key
    assert known_hosts.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    ("host", "port", "username", "message"),
    [
        (" ", 22, "user", "host"),
        ("host", 0, "user", "Port"),
        ("host", 22, " ", "user"),
    ],
)
def test_connect_ssh_rejects_invalid_parameters(
    host: str, port: int, username: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        connect_ssh(host, port, username)


def test_connect_ssh_closes_client_after_connection_failure() -> None:
    client = Mock()
    client.connect.side_effect = OSError("connection refused")
    with patch("sftp_tools.connection.paramiko.SSHClient", return_value=client):
        with pytest.raises(OSError, match="connection refused"):
            connect_ssh("example.test", 22, "user", reconnect_count=0)
    client.close.assert_called_once_with()


def test_connect_ssh_retries_on_failure() -> None:
    client = Mock()
    # Fail twice, then succeed on third attempt
    client.connect.side_effect = [
        OSError("connection refused"),
        OSError("connection refused"),
        None,  # Success
    ]
    client.get_transport.return_value = Mock()
    with patch("sftp_tools.connection.paramiko.SSHClient", return_value=client):
        result = connect_ssh("example.test", 22, "user", reconnect_count=2, reconnect_delay=0)
    
    assert result is client
    assert client.connect.call_count == 3
    # Client should be closed twice (after each failure) + once more for cleanup? 
    # Actually, no - we only close on exceptions, and on the final success we return without closing
    assert client.close.call_count == 2


def test_connect_ssh_does_not_retry_host_key_error() -> None:
    client = Mock()
    client.connect.side_effect = UnknownHostKeyError("example.test", 22, Mock())
    with patch("sftp_tools.connection.paramiko.SSHClient", return_value=client):
        with pytest.raises(UnknownHostKeyError):
            connect_ssh("example.test", 22, "user", reconnect_count=2)
    
    # Should only attempt once, not retry for host key errors
    assert client.connect.call_count == 1


def test_server_action_uses_only_approved_command() -> None:
    client = Mock()
    stdout = Mock()
    stdout.read.return_value = b"active\n"
    stdout.channel.recv_exit_status.return_value = 0
    stderr = Mock()
    stderr.read.return_value = b""
    client.exec_command.return_value = (Mock(), stdout, stderr)

    assert run_server_action(client, "status") == "active"
    client.exec_command.assert_called_once_with(
        "systemctl show -p ActiveState --value sshd",
        timeout=15,
    )


def test_server_action_rejects_unrecognized_command() -> None:
    client = Mock()
    with pytest.raises(ValueError, match="Unsupported server action"):
        run_server_action(client, "status; rm -rf /")
    client.exec_command.assert_not_called()


def test_server_action_reports_remote_errors() -> None:
    client = Mock()
    stdout = Mock()
    stdout.read.return_value = b""
    stdout.channel.recv_exit_status.return_value = 1
    stderr = Mock()
    stderr.read.return_value = b"sudo: a password is required"
    client.exec_command.return_value = (Mock(), stdout, stderr)

    with pytest.raises(RuntimeError, match="sudo: a password is required"):
        run_server_action(client, "restart")
