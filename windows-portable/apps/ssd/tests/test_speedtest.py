# SPDX-License-Identifier: GPL-3.0-or-later
"""speedtest.py: where the test file goes, the test itself past Windows' cache (small, in a temp folder), and what it
says when it cannot run."""

from __future__ import annotations

import sys
from collections import namedtuple
from pathlib import Path, PureWindowsPath

import pytest

from ssd_check import speedtest

OWN = PureWindowsPath(r"C:\Users\someone\AppData\Local\windows-portable-suite\windows-portable-ssd")


def test_the_file_goes_in_the_apps_folder_else_at_the_drives_root():
    assert speedtest.folder_for(["C"], OWN) == OWN                             # the app's folder is on the drive
    assert speedtest.folder_for(["d", "E"], OWN) == Path("D:\\")               # an SD card: its first letter
    assert speedtest.folder_for([], OWN) is None                               # no drive letter: nowhere to write


@pytest.mark.skipif(sys.platform != "win32", reason="the test opens its file through kernel32")
def test_it_measures_and_leaves_nothing_behind(tmp_path):
    read, write = speedtest.measure(tmp_path, size=4 << 20, block=1 << 20)
    assert read > 0 and write > 0
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(sys.platform != "win32", reason="the test opens its file through kernel32")
def test_a_slow_drive_stops_at_the_limit(tmp_path):
    ticks = iter(range(1000))
    read, write = speedtest.measure(tmp_path, size=64 << 20, block=1 << 20, limit=3, clock=lambda: next(ticks))
    assert write == pytest.approx(2 * (1 << 20) / 1e6 / 4)                   # two blocks before "second" 3, of 4
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(sys.platform != "win32", reason="the test opens its file through kernel32")
def test_not_enough_free_space_says_so(tmp_path, monkeypatch):
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(speedtest.shutil, "disk_usage", lambda folder: usage(10, 9, 1 << 20))
    with pytest.raises(speedtest.SpeedError, match="Not enough free space"):
        speedtest.measure(tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="elsewhere than Windows")
def test_off_windows_it_says_so(tmp_path):
    with pytest.raises(speedtest.SpeedError, match="Windows"):
        speedtest.measure(tmp_path)
