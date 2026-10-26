# SPDX-License-Identifier: GPL-3.0-or-later
"""The user service that runs the watcher with the desktop session: bc250-hdmi-cec-watch.service in
~/.config/systemd/user. Its options are the watcher's jobs (RESTART, PAUSE); the app writes the unit with the jobs
that are on, enables and (re)starts it, and stops and removes it when none is. install.sh --uninstall removes it too,
since it starts the app's own files. The unit is the only record of the jobs: jobs() reads them back from it."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .runner import Result

UNIT = "bc250-hdmi-cec-watch.service"
RESTART = "--restart-picture"
PAUSE = "--pause-media"

Runner = Callable[[list[str]], Result]


def unit_path(config_dir: Path) -> Path:
    return config_dir / "systemd" / "user" / UNIT


def unit_text(python: str, root: Path, options: list[str]) -> str:
    return "\n".join([
        "[Unit]",
        "Description=BC250 HDMI CEC: what happens when the TV turns off and on",
        "After=graphical-session.target",
        "PartOf=graphical-session.target",
        "",
        "[Service]",
        f"WorkingDirectory={root}",
        f"ExecStart={' '.join([python, '-m', 'hdmi_cec.watcher', *options])}",
        "Restart=on-failure",
        "RestartSec=30",
        "",
        "[Install]",
        "WantedBy=graphical-session.target",
        "",
    ])


def enabled(run: Runner, config_dir: Path) -> bool:
    result = run(["systemctl", "--user", "is-enabled", UNIT])
    return unit_path(config_dir).is_file() and result.ok and result.out.strip().startswith("enabled")


def jobs(run: Runner, config_dir: Path) -> set[str]:
    """The options of the running setup: empty when the service is not installed and enabled."""
    if not enabled(run, config_dir):
        return set()
    text = unit_path(config_dir).read_text(encoding="utf-8")
    return {option for option in (RESTART, PAUSE) if option in text}


def enable(run: Runner, config_dir: Path, python: str, root: Path, options: list[str]) -> Result:
    path = unit_path(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(unit_text(python, root, options), encoding="utf-8")
    run(["systemctl", "--user", "daemon-reload"])
    run(["systemctl", "--user", "enable", UNIT])
    return run(["systemctl", "--user", "restart", UNIT])           # new options take effect now


def set_jobs(run: Runner, config_dir: Path, python: str, root: Path, options: set[str]) -> Result:
    """Installs the service with *options*, or removes it when there are none."""
    if not options:
        disable(run, config_dir)
        return Result(0, "")
    return enable(run, config_dir, python, root, [o for o in (RESTART, PAUSE) if o in options])


def disable(run: Runner, config_dir: Path) -> None:
    path = unit_path(config_dir)
    if not path.is_file():
        return
    run(["systemctl", "--user", "disable", "--now", UNIT])
    path.unlink()
    run(["systemctl", "--user", "daemon-reload"])
