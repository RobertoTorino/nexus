# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app writes in PPSSPP's settings (userdata.py): the notice of a newer release off, every other line as
PPSSPP wrote it (owner, 03-11-2026, from the Windows Portable Suite's PPSSPP Manager)."""

from __future__ import annotations

from pathlib import Path

from ppsspp_manager import emulator, userdata


def test_prepare_turns_the_notice_off_and_keeps_the_rest(tmp_path):
    path = userdata.settings_path(tmp_path)
    assert userdata.prepare(tmp_path) == ["its notice of a newer release off"]      # no file yet: made
    assert path.read_text() == "[General]\nCheckForNewVersion = False\n"
    stamp = path.stat().st_mtime_ns
    assert userdata.prepare(tmp_path) == [] and path.stat().st_mtime_ns == stamp   # nothing to do: not written
    path.write_text("[General]\nFirstRun = False\ncheckfornewversion = True\nLanguage = en_US\n\n[Graphics]\n"
                    "VSync = False\n")
    assert userdata.prepare(tmp_path) == ["its notice of a newer release off"]
    assert path.read_text() == ("[General]\nFirstRun = False\nCheckForNewVersion = False\nLanguage = en_US\n\n"
                                "[Graphics]\nVSync = False\n")                      # in place, whatever its case
    path.write_text("[Graphics]\nVSync = False\n")
    userdata.prepare(tmp_path)
    assert path.read_text() == "[Graphics]\nVSync = False\n\n[General]\nCheckForNewVersion = False\n"


def test_the_byte_order_mark_ppsspp_writes_is_kept(tmp_path):
    """PPSSPP writes the file with a UTF-8 byte order mark: the first section is still found behind it, and the
    mark stays."""
    path = userdata.settings_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("\ufeff[General]\nFirstRun = False\n")
    assert userdata.prepare(tmp_path) == ["its notice of a newer release off"]
    assert path.read_text() == "\ufeff[General]\nFirstRun = False\nCheckForNewVersion = False\n"
    assert userdata.read_lines(path) == (["[General]", "FirstRun = False", "CheckForNewVersion = False"], True)


def test_ini_lines():
    lines = ["[General]", "A = 1", "", "[Other]", "B = 2"]
    assert userdata.ini_value(lines, "general", "a") == "1" and userdata.ini_value(lines, "General", "B") is None
    userdata.ini_set(lines, "General", "C", "3")
    assert lines == ["[General]", "A = 1", "C = 3", "", "[Other]", "B = 2"]           # after the section's last line


def test_ppsspp_running_sees_the_appimages_process(tmp_path):
    proc = tmp_path / "proc"
    for pid, comm, state in (("10", "steam", "S"), ("11", "ppsspp.AppImage", "Z")):
        (proc / pid).mkdir(parents=True)
        (proc / pid / "comm").write_text(comm + "\n")
        (proc / pid / "stat").write_text(f"{pid} ({comm}) {state} 1 1 1\n")
    assert not emulator.running(proc)                                                # a zombie does not count
    (proc / "11" / "stat").write_text("11 (ppsspp.AppImage) S 1 1 1\n")
    assert emulator.running(proc)
    assert not emulator.running(Path("/nonexistent"))
