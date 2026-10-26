# SPDX-License-Identifier: GPL-3.0-or-later
from mesh_shaders.status import Status, parse, verdict

FRESH = """Board: BC-250 (1002:13fe)
Kernel: 7.2.8-ogc5.1.fc44.x86_64
System Mesa: 26.2.4
DirectMesh: v1.3.1, Mesa 26.2.1, suite patch 1a2b3c4d
Build: none
Driver: not installed
Test: none
Launch options: /usr/local/bin/bc250-mesh-shaders-run %command%
"""
BUILT = "DirectMesh v1.3.1, Mesa 26.2.1, suite patch 1a2b3c4d, 2026-10-13 19:42 UTC"


def status(**changes: str) -> Status:
    s = parse(FRESH)
    return Status({**s.fields, **changes})


def test_parse_reads_each_line_once():
    s = parse(FRESH + "Build: something later\nnot a field\n")
    assert s.get("Build") == "none" and s.launch_options.endswith("%command%")
    assert s.is_bc250 and not s.built and not s.installed and not s.tested
    assert s.directmesh == "v1.3.1, Mesa 26.2.1, suite patch 1a2b3c4d" and s.driver == ""


def test_build_and_driver():
    s = status(Build=BUILT, Driver=f"installed, {BUILT}")
    assert s.built and not s.build_outdated
    assert s.installed and s.driver == BUILT and not s.install_outdated
    s = status(Build=BUILT.replace("19:42", "20:15"), Driver=f"installed, {BUILT}")
    assert s.install_outdated


def test_a_build_of_an_older_directmesh_is_outdated():
    s = status(Build="DirectMesh v1.3, Mesa 26.2.1, 2026-10-05 10:00 UTC")
    assert s.build_outdated
    assert status(Build="DirectMesh v1.3.1, Mesa 26.2.1, 2026-10-13 19:42 UTC").build_outdated     # no suite patch
    assert status(Build=BUILT.replace("1a2b3c4d", "9f8e7d6c")).build_outdated
    assert not status(Build=BUILT, DirectMesh="").build_outdated


def test_verdicts():
    assert verdict(Status())[0] == "Unknown"
    assert verdict(status(Board="no BC-250 found (1002:13fe or 1002:143f)"))[:2] == ("No BC-250", "bad")
    assert verdict(status(Board="BC-250 (1002:143f)"))[0] == "Not built"
    assert verdict(status(Build=BUILT))[0] == "Not installed"
    installed = {"Build": BUILT, "Driver": f"installed, {BUILT}"}
    assert verdict(status(**installed, Test="not run with this driver"))[:2] == ("Test needed", "warn")
    assert verdict(status(**installed, Test="passed on kernel 7.2.7; test again on this one"))[0] == "Test needed"
    assert verdict(status(**installed, Test="failed (2026-10-13 21:00); see the test log"))[:2] == ("Test failed", "bad")
    assert verdict(status(**installed, Test="passed on this kernel (2026-10-13 21:00)"))[:2] == ("Ready", "ok")
