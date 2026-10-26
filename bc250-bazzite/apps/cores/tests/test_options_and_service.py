# SPDX-License-Identifier: GPL-3.0-or-later
"""The bisect GUI's choices as a bc250-cores-bisect.sh command line, and the --auto resume unit."""

from __future__ import annotations

import shlex

import pytest

from cores_bisect import service
from cores_bisect.options import LOAD_TOOLS, BisectOptions


def test_defaults_are_the_scripts_own():
    assert BisectOptions().to_args() == ["-t", "600", "-r", "3"]
    assert BisectOptions().validate() == []


def test_every_switch_reaches_the_command_line():
    opts = BisectOptions(time_secs=900, rounds=5, same_boot=True, unattended=True, load_tool="both", rasdaemon=True)
    assert opts.to_args() == ["-t", "900", "-r", "5", "--load", "both", "--rasdaemon", "--same-boot", "--auto"]
    assert shlex.split(opts.to_command("/opt/bc250-cores-bisect/bc250-cores-bisect.sh"))[:2] == [
        "bash", "/opt/bc250-cores-bisect/bc250-cores-bisect.sh"]


@pytest.mark.parametrize(("opts", "message"), [
    (BisectOptions(time_secs=30), "at least 60 seconds"),
    (BisectOptions(rounds=0), "between 1 and 9"),
    (BisectOptions(rounds=10), "between 1 and 9"),
    (BisectOptions(load_tool="prime95"), "Load tool must be one of"),
])
def test_validation(opts, message):
    assert any(message in error for error in opts.validate())


def test_load_tools():
    assert LOAD_TOOLS == ("stress-ng", "mprime", "both")


def test_unit_resumes_with_the_gui_settings_and_always_auto():
    text = service._unit_contents("/opt/x/bc250-cores-bisect.sh", BisectOptions(load_tool="mprime", unattended=True))
    assert "ExecStart=/usr/bin/env bash /opt/x/bc250-cores-bisect.sh --auto -t 600 -r 3 --load mprime" in text
    assert text.count("--auto") == 1
    assert "StandardOutput=append:%h/.local/share/bc250-cores-bisect/auto.log" in text


def test_install_enables_the_unit_without_starting_it(monkeypatch):
    """enable, not enable --now: the GUI starts the run itself, a second instance would share its state."""
    calls = []
    monkeypatch.setattr(service.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(service.subprocess, "run", lambda args, check: calls.append(args))
    service.install("/opt/x/bc250-cores-bisect.sh", BisectOptions())
    assert service.is_installed()
    assert calls == [["systemctl", "--user", "daemon-reload"],
                     ["systemctl", "--user", "enable", "bc250-cores-bisect-auto.service"]]
