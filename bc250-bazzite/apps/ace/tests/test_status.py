# SPDX-License-Identifier: GPL-3.0-or-later
from ace_queues.status import Status, parse, verdict

FRESH = """Board: BC-250 (1002:13fe)
Kernel: 7.2.8-ogc5.1.fc44.x86_64
System Mesa: 26.2.4
Build: none
Driver: not installed
Test: none
All apps: off
Launch options: /usr/local/bin/bc250-ace-queues-run %command%
"""


def status(**changes: str) -> Status:
    s = parse(FRESH)
    return Status({**s.fields, **changes})


def test_parse_reads_each_line_once():
    s = parse(FRESH + "Build: something later\nnot a field\n")
    assert s.get("Build") == "none" and s.launch_options.endswith("%command%")
    assert s.is_bc250 and not s.built and not s.installed and not s.tested and not s.all_apps


def test_build_and_driver_versions():
    s = status(Build="Mesa 26.2.4, 2026-10-10 16:00 UTC", Driver="installed, Mesa 26.2.3")
    assert s.built and s.build_mesa == "26.2.4" and not s.build_outdated
    assert s.installed and s.driver_mesa == "26.2.3" and s.install_outdated
    s = status(**{"Build": "Mesa 26.2.4, x", "System Mesa": "26.2.5"})
    assert s.build_outdated
    s = status(**{"Build": "Mesa 26.2.4, x", "System Mesa": "unknown"})
    assert not s.build_outdated


def test_verdicts():
    assert verdict(Status())[0] == "Unknown"
    assert verdict(status(Board="no BC-250 found (1002:13fe)"))[:2] == ("No BC-250", "bad")
    assert verdict(status())[0] == "Not built"
    assert verdict(status(Build="Mesa 26.2.4, x"))[0] == "Not installed"
    installed = {"Build": "Mesa 26.2.4, x", "Driver": "installed, Mesa 26.2.4"}
    assert verdict(status(**installed, Test="not run with this driver"))[:2] == ("Test needed", "warn")
    assert verdict(status(**installed, Test="passed on kernel 7.2.7; test again on this one"))[0] == "Test needed"
    assert verdict(status(**installed, Test="failed (2026-10-10 18:00); see the test log"))[:2] == ("Test failed", "bad")
    assert verdict(status(**installed, Test="passed on this kernel (2026-10-10 18:00)"))[:2] == ("Ready", "ok")
    assert verdict(status(**installed, Test="passed on this kernel (x)", **{"All apps": "on"}))[0] == "On for all apps"
