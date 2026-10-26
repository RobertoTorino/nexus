# SPDX-License-Identifier: GPL-3.0-or-later

"""Optional helper: installs the systemd --user unit that resumes an ``--auto`` cores bisect run
after every reboot/login (see bc250-cores-bisect-auto.service.example and the manual's "--auto
checklist"). The setup GUI only offers this as a convenience for the unattended path; everything it
does here is exactly what that manual section tells you to do by hand.

The script disables and removes this unit itself once every attempt is done."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

from .options import BisectOptions

UNIT_NAME = "bc250-cores-bisect-auto.service"


def unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / UNIT_NAME


def is_installed() -> bool:
    return unit_path().is_file()


def _unit_contents(script_path: str, opts: BisectOptions) -> str:
    log = "%h/.local/share/bc250-cores-bisect/auto.log"
    # --auto is what makes the resumed run unattended, so the unit always passes it; everything
    # else (load time, rounds, load tool, rasdaemon, same-boot) comes straight from the GUI.
    args = [a for a in opts.to_args() if a != "--auto"]
    cmdline = shlex.join([script_path, "--auto", *args])
    return f"""[Unit]
Description=BC-250 cores bisect - auto-resume after reboot
# default.target starts at every user login (graphical or not); gamescope/Steam sessions
# don't always activate graphical-session.target, so don't depend on it.

[Service]
Type=oneshot
# Give the desktop a few seconds to settle before testing.
ExecStartPre=/bin/sleep 20
ExecStart=/usr/bin/env bash {cmdline}
StandardOutput=append:{log}
StandardError=append:{log}

[Install]
WantedBy=default.target
"""


def install(script_path: str, opts: BisectOptions) -> None:
    """Writes the unit file and enables+starts it. Raises on failure (e.g. no systemd --user)."""
    path = unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_unit_contents(script_path, opts))

    if not shutil.which("systemctl"):
        raise RuntimeError("systemctl not found; install the unit manually (see the manual).")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    # Deliberately "enable" and not "enable --now": the GUI starts the run in a terminal right
    # after this, and a second concurrent instance would fight it over the same state dir. The
    # unit only needs to fire on the *next* login, after the script's first auto-reboot.
    subprocess.run(["systemctl", "--user", "enable", UNIT_NAME], check=True)
