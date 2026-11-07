# SPDX-License-Identifier: GPL-3.0-or-later
"""The sshd of this computer: its state, and starting or stopping it, so this computer can be the host the other one
connects to. Starting runs the wiki's "Set up the host" steps as root through polkit's password dialog (pkexec):
sshd enabled and started, and the firewall opened for ssh when firewalld runs and it is not open yet. Stopping
disables and stops sshd and leaves the firewall as it is."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

TIMEOUT_S = 15
ROOT_TIMEOUT_S = 300                    # pkexec: the password dialog waits for the user

INSTALL_HINT = "sudo rpm-ostree install openssh-server, then reboot"
_START = (
    "systemctl enable --now sshd || exit $?; "
    "if firewall-cmd --state >/dev/null 2>&1 && ! firewall-cmd --query-service=ssh >/dev/null 2>&1; then "
    "firewall-cmd --permanent --add-service=ssh && firewall-cmd --reload; fi"
)
_STOP = "systemctl disable --now sshd"


@dataclass(frozen=True)
class LocalSshd:
    installed: bool
    active: bool
    enabled: bool
    firewall_open: bool | None          # None: firewalld does not run


def supported() -> bool:
    """Only a Linux with systemd and pkexec has a local sshd the app manages."""
    return sys.platform.startswith("linux") and all(shutil.which(tool) for tool in ("systemctl", "pkexec"))


def _run(argv: list[str], timeout: int = TIMEOUT_S) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(argv, 127, "", str(error))


def local_status() -> LocalSshd:
    installed = shutil.which("rpm") is None or _run(["rpm", "-q", "openssh-server"]).returncode == 0
    active = _run(["systemctl", "is-active", "sshd"]).stdout.strip() == "active"
    enabled = _run(["systemctl", "is-enabled", "sshd"]).stdout.strip() == "enabled"
    firewall_open: bool | None = None
    if shutil.which("firewall-cmd") and _run(["firewall-cmd", "--state"]).returncode == 0:
        firewall_open = _run(["firewall-cmd", "--query-service=ssh"]).returncode == 0
    return LocalSshd(installed, active, enabled, firewall_open)


def command(start: bool) -> list[str]:
    return ["pkexec", "/bin/sh", "-c", _START if start else _STOP]


def set_local_sshd(start: bool) -> LocalSshd:
    """Starts (enables, opens the firewall) or stops (disables) sshd here, then reads the state again."""
    result = _run(command(start), ROOT_TIMEOUT_S)
    if result.returncode in (126, 127):
        raise RuntimeError("Not authorized: the password dialog was canceled or refused.")
    if result.returncode:
        message = (result.stderr or result.stdout).strip()
        raise RuntimeError(message or f"The command stopped with exit code {result.returncode}.")
    return local_status()


def describe(state: LocalSshd) -> str:
    if not state.installed:
        return f"openssh-server is not installed: {INSTALL_HINT}."
    text = "sshd is running" if state.active else "sshd is stopped"
    text += ", starts at boot" if state.enabled else ", does not start at boot"
    if state.firewall_open is False:
        text += "; the firewall is closed for ssh"
    return text + "."
