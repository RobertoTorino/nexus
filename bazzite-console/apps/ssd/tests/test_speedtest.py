# SPDX-License-Identifier: GPL-3.0-or-later
"""The speed test: where its file goes, that it measures and deletes the file, and when it cannot run."""

from __future__ import annotations

from collections import namedtuple
import pytest

from ssd_check import speedtest


def test_the_home_folder_when_it_is_on_the_drive(tmp_path):
    home = tmp_path / "var" / "home" / "user"
    home.mkdir(parents=True)
    mounts = ["/boot/efi", str(tmp_path / "var"), str(tmp_path / "var" / "home")]
    assert speedtest.folder_for(mounts, home) == home.resolve() / ".cache" / "ps5-ssd-check"


def test_else_a_writable_mount_point_and_none_unmounted(tmp_path):
    stick = tmp_path / "media" / "STICK"
    stick.mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    assert speedtest.folder_for(["/proc", str(stick)], home) == stick
    assert speedtest.folder_for([], home) is None
    assert speedtest.folder_for(["/"], home) == home.resolve() / ".cache" / "ps5-ssd-check"   # a drive at / holds home


def test_it_measures_and_leaves_nothing_behind(tmp_path):
    read, write = speedtest.measure(tmp_path / "test", size=4 << 20, block=1 << 20)
    assert read > 0 and write > 0
    assert list((tmp_path / "test").iterdir()) == []


def test_existing_test_file_is_not_overwritten_or_deleted(tmp_path):
    existing = tmp_path / speedtest.NAME
    existing.write_text("keep")
    with pytest.raises(speedtest.SpeedError):
        speedtest.measure(tmp_path, size=1 << 20, block=1 << 20)
    assert existing.read_text() == "keep"


def test_a_slow_drive_stops_at_the_limit(tmp_path):
    ticks = iter(range(1000))
    read, write = speedtest.measure(tmp_path, size=64 << 20, block=1 << 20, limit=2.5,
                                    clock=lambda: next(ticks))
    assert write == pytest.approx(2 * (1 << 20) / 1e6 / 4)      # two blocks before the 2.5 s, fsync'd at tick 4
    assert not (tmp_path / speedtest.NAME).exists()


def test_not_enough_space_or_no_folder(tmp_path, monkeypatch):
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(speedtest.shutil, "disk_usage", lambda path: usage(10, 9, 1 << 20))
    with pytest.raises(speedtest.SpeedError, match="Not enough free space"):
        speedtest.measure(tmp_path, size=1 << 20)
    blocked = tmp_path / "file"
    blocked.write_text("")
    with pytest.raises(speedtest.SpeedError, match="cannot be used"):
        speedtest.measure(blocked / "sub", size=1 << 20)
