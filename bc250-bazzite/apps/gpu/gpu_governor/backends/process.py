# SPDX-License-Identifier: GPL-3.0-or-later
"""Subprocess helper shared by the backends."""

from __future__ import annotations

import subprocess


def run(args: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    """Run a command and never raise: a missing tool or a timeout look like a failed command.
    Keeps the GUI usable on a system without systemd (development) and on a hung polkit agent."""
    try:
        return subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        return subprocess.CompletedProcess(args, 127, "", f"{args[0]}: command not found")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", f"{args[0]}: timed out after {timeout:.0f}s")
    except OSError as exc:
        return subprocess.CompletedProcess(args, 1, "", str(exc))
