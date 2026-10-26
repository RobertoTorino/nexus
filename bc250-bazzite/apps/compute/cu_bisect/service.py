# SPDX-License-Identifier: GPL-3.0-or-later

"""Optional helper: installs the systemd --user unit that resumes an ``--auto`` bisect run after
every reboot/login (see bc250-cu-bisect-auto.service.example and the manual's "--auto checklist").
The launcher GUI only offers this as a convenience for the unattended path; everything it does here
is exactly what that manual section tells you to do by hand."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

UNIT_NAME = "bc250-cu-bisect-auto.service"


def unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / UNIT_NAME


def is_installed() -> bool:
    return unit_path().is_file()


def _unit_contents(script_path: str, time_secs: int, rounds: int) -> str:
    log = "%h/.local/share/bc250-cu-bisect/auto.log"
    return f"""[Unit]
Description=BC-250 CU bisect - auto-resume after reboot

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 20
ExecStart=/usr/bin/env bash {script_path} --auto -t {time_secs} -r {rounds}
StandardOutput=append:{log}
StandardError=append:{log}

[Install]
WantedBy=default.target
"""


def install(script_path: str, time_secs: int, rounds: int) -> None:
    """Writes the unit file and enables+starts it. Raises on failure (e.g. no systemd --user)."""
    path = unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_unit_contents(script_path, time_secs, rounds))

    if not shutil.which("systemctl"):
        raise RuntimeError("systemctl not found; install the unit manually (see the manual).")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", UNIT_NAME], check=True)
