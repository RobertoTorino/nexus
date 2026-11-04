# SPDX-License-Identifier: GPL-3.0-or-later

import subprocess

import pytest

from sftp_tools import local_host, server_tab
from sftp_tools.local_host import LocalSshd


def fake_run(answers: dict[str, tuple[int, str]], calls: list[list[str]]):
    def run(argv, timeout=local_host.TIMEOUT_S):
        calls.append(argv)
        code, out = answers.get(" ".join(argv[:3]), (0, ""))
        return subprocess.CompletedProcess(argv, code, out, "")
    return run


@pytest.fixture
def tools(monkeypatch):
    monkeypatch.setattr(local_host.shutil, "which", lambda tool: f"/usr/bin/{tool}")


def test_status_reads_sshd_and_the_firewall(monkeypatch, tools) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(local_host, "_run", fake_run({
        "systemctl is-active sshd": (3, "inactive\n"),
        "systemctl is-enabled sshd": (1, "disabled\n"),
        "firewall-cmd --query-service=ssh": (1, "no\n"),
    }, calls))

    state = local_host.local_status()

    assert state == LocalSshd(installed=True, active=False, enabled=False, firewall_open=False)
    assert local_host.describe(state) == (
        "sshd is stopped, does not start at boot; the firewall is closed for ssh.")


def test_status_without_firewalld_or_openssh_server(monkeypatch, tools) -> None:
    monkeypatch.setattr(local_host, "_run", fake_run({
        "rpm -q openssh-server": (1, ""),
        "firewall-cmd --state": (252, "not running"),
    }, []))

    state = local_host.local_status()

    assert not state.installed and state.firewall_open is None
    assert local_host.INSTALL_HINT in local_host.describe(state)


def test_start_enables_sshd_and_opens_the_firewall_through_pkexec() -> None:
    argv = local_host.command(True)

    assert argv[:3] == ["pkexec", "/bin/sh", "-c"]
    assert "systemctl enable --now sshd" in argv[3]
    assert "firewall-cmd --permanent --add-service=ssh && firewall-cmd --reload" in argv[3]
    assert local_host.command(False)[3] == "systemctl disable --now sshd"


def test_set_reads_the_state_again_or_says_why_it_failed(monkeypatch, tools) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(local_host, "_run", fake_run({"systemctl is-active sshd": (0, "active\n")}, calls))
    assert local_host.set_local_sshd(True).active
    assert calls[0][0] == "pkexec"

    monkeypatch.setattr(local_host, "_run", fake_run({"pkexec /bin/sh -c": (126, "")}, []))
    with pytest.raises(RuntimeError, match="Not authorized"):
        local_host.set_local_sshd(True)


def test_the_tab_shows_the_local_state_and_its_button(qapp, monkeypatch) -> None:
    monkeypatch.setattr(server_tab, "supported", lambda: False)
    tab = server_tab.ServerManagerTab()

    tab._show_local(LocalSshd(installed=True, active=True, enabled=True, firewall_open=True))
    assert tab.local_button.text() == "Stop sshd here" and tab.local_button.isEnabled()
    assert tab.local_status.text() == "sshd is running, starts at boot."

    tab._show_local(LocalSshd(installed=False, active=False, enabled=False, firewall_open=None))
    assert not tab.local_button.isEnabled()
