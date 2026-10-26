# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/suites.py: the suites of a checkout, the default one, their systems, and the suite a release tag names by
its prefix."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("nexus_suites", TOOLS / "suites.py")
suites = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suites)


def make(root: Path, name: str, system: str = "", prefix: str = "") -> Path:
    folder = root / name
    (folder / "portal").mkdir(parents=True)
    (folder / "portal" / "apps.toml").write_text("")
    if system:
        (folder / "SYSTEM").write_text(system + "\n")
    if prefix:
        (folder / "TAG_PREFIX").write_text(prefix + "\n")
    return folder


@pytest.fixture
def two(tmp_path) -> Path:
    make(tmp_path, "bc250-bazzite", "bazzite")
    make(tmp_path, "windows-portable", "windows", "wp-")
    (tmp_path / "nexus").mkdir()                                     # a folder without a portal is no suite
    return tmp_path


def test_the_suites_and_their_systems(two):
    assert [p.name for p in suites.suites(two)] == ["bc250-bazzite", "windows-portable"]
    assert [suites.system(p) for p in suites.suites(two)] == ["bazzite", "windows"]
    assert [suites.tag_prefix(p) for p in suites.suites(two)] == ["", "wp-"]
    assert suites.system(two / "nexus") == suites.tag_prefix(two / "nexus") == ""


def test_the_default_is_the_suite_without_a_prefix(two, tmp_path):
    assert suites.suite(root=two) == two / "bc250-bazzite"
    assert suites.suite("windows-portable", two) == two / "windows-portable"
    with pytest.raises(LookupError, match="no suite 'nexus'"):
        suites.suite("nexus", two)
    (two / "windows-portable" / "TAG_PREFIX").unlink()               # two without a prefix: say which
    with pytest.raises(LookupError, match="say which with --suite"):
        suites.suite(root=two)


def test_a_tag_names_its_suite(two):
    assert suites.of_tag("wp-portal-v0.1.0", two) == (two / "windows-portable", "portal", "0.1.0")
    assert suites.of_tag("wp-test-v1.2.3", two) == (two / "windows-portable", "test", "1.2.3")
    assert suites.of_tag("portal-v10.1.0", two) == (two / "bc250-bazzite", "portal", "10.1.0")
    assert suites.of_tag("cu-unlock-v0.2.0", two) == (two / "bc250-bazzite", "cu-unlock", "0.2.0")
    assert suites.of_tag("wp-v1.0.0", two) == (two / "bc250-bazzite", "wp", "1.0.0")   # the prefix, then no app
    for bad in ("portal", "portal-v1.0", "Portal-v1.0.0", "wp-portal-1.0.0"):
        with pytest.raises(LookupError, match="TAG_PREFIX"):
            suites.of_tag(bad, two)


def test_one_suite_laid_out_as_the_root(tmp_path):
    """The tools' test repositories: the root is the suite."""
    (tmp_path / "portal").mkdir()
    (tmp_path / "portal" / "apps.toml").write_text("")
    assert suites.suites(tmp_path) == [tmp_path] == [suites.suite(root=tmp_path)]
    assert suites.of_tag("portal-v0.1.0", tmp_path) == (tmp_path, "portal", "0.1.0")


def test_the_command_line():
    run = lambda *args: subprocess.run([sys.executable, str(TOOLS / "suites.py"), *args], capture_output=True,
                                       text=True)
    assert run().stdout.split() == [p.name for p in suites.suites()]
    assert run("--default").stdout.strip() == "bc250-bazzite"
    assert run("--system", "bazzite").stdout.split() == ["bc250-bazzite"]
    assert run("--tag", "portal-v1.0.0").stdout.split() == ["bc250-bazzite", "portal", "1.0.0"]
    result = run("--tag", "nothing")
    assert result.returncode == 1 and "not <app>-v<x.y.z>" in result.stderr
