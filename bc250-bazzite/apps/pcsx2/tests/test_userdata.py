# SPDX-License-Identifier: GPL-3.0-or-later
"""PCSX2's own folder (userdata.py): where it is, which files in its bios folder count as BIOS dumps, a dump
removed with its files, and PCSX2's log of its last run read for the app's log."""

from __future__ import annotations

from conftest import make_bios

from pcsx2_manager.userdata import (Session, bios_dir, bios_files, last_session, log_file, pcsx2_home, played,
                                    remove_bios)


def test_pcsx2s_own_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert pcsx2_home() == tmp_path / "config" / "PCSX2"
    assert bios_dir(pcsx2_home()) == tmp_path / "config" / "PCSX2" / "bios"


def test_the_bios_dumps(tmp_path):
    folder = tmp_path / "bios"
    assert bios_files(folder) == []                                            # not there yet
    dump = make_bios(folder)                                                   # brings SCPH-70012.bin and its .nvm
    rom = folder / "ps2-0230e-20080220.ROM"
    rom.write_bytes(b"\0" * 64)
    (folder / "readme.txt").write_text("not a BIOS")
    (folder / "folder.bin").mkdir()
    assert bios_files(folder) == [dump, rom]                                   # .nvm and the rest left out


def test_a_dump_is_removed_with_its_files(tmp_path):
    folder = tmp_path / "bios"
    dump = make_bios(folder)
    other = make_bios(folder, "SCPH10000.BIN")
    (folder / "scph-70012.MEC").write_bytes(b"\0")                             # the same name, another case
    assert remove_bios(dump) == ["SCPH-70012.bin", "SCPH-70012.nvm", "scph-70012.MEC"]
    assert sorted(p.name for p in folder.iterdir()) == ["SCPH10000.BIN", "SCPH10000.nvm"]
    assert bios_files(folder) == [other]


EMULOG = """\
[    0.0733] PCSX2 v2.8.2
[    0.0744]   Processor        = AMD BC-250
[    0.5080]   Serial: SLUS-20328
[    0.5080]   CRC: 833fe0a4
[    1.0259] SDLInputSource: Opened gamepad 1 (instance id 1, player id 0): DualSense Edge Wireless Controller
[    9.0259] SDLInputSource: Opened gamepad 2 (instance id 2, player id 1): Xbox Series X Controller
[    9.5000] SDLInputSource: Opened gamepad 1 (instance id 3, player id 0): DualSense Edge Wireless Controller
[  352.6112] Add 346 seconds play time to SLUS-20328 -> now 346
[  352.7374] Releasing host memory for virtual systems...
"""


def test_pcsx2s_last_run(tmp_path):
    """The log's version, game, controllers (each once) and the play time PCSX2 counted; without that line (PCSX2
    did not shut down by itself) the last time stamp; without a log nothing."""
    assert last_session(tmp_path) is None
    (tmp_path / "inis").mkdir()
    (tmp_path / "inis" / "PCSX2.ini").write_text("[Folders]\nLogs = mylogs\n")
    log = log_file(tmp_path)
    assert log == tmp_path / "mylogs" / "emulog.txt"
    log.parent.mkdir()
    log.write_text(EMULOG)
    session = last_session(tmp_path)
    assert session == Session(log.stat().st_mtime, "2.8.2", "SLUS-20328", "833FE0A4", 346, True,
                              ("DualSense Edge Wireless Controller", "Xbox Series X Controller"))
    log.write_text(EMULOG.replace("[  352.6112] Add 346 seconds play time to SLUS-20328 -> now 346\n", ""))
    session = last_session(tmp_path)
    assert (session.seconds, session.counted) == (352, False)
    log.write_text("[    0.0733] PCSX2 v2.8.2\n")                               # PCSX2's window alone, no game
    assert last_session(tmp_path).serial == ""


def test_pcsx2s_play_times(tmp_path):
    from pcsx2_manager.userdata import play_times
    assert play_times(tmp_path) == {}
    (tmp_path / "inis").mkdir()
    (tmp_path / "inis" / "playtime.dat").write_text(
        "SLUS-21553                       1482                 1792814410          \n"
        "SLUS-20328                       346                  1792814849          \n"
        "SLUS-20328                       999                  1792814999          \n"             # a repeat: skipped
        "not a line\n")
    assert play_times(tmp_path) == {"SLUS-21553": (1482, 1792814410), "SLUS-20328": (346, 1792814849)}


def test_a_play_time_in_words():
    assert played(40) == "40 s" and played(60) == "1 min" and played(346) == "5 min 46 s"
    assert played(3600) == "1 h 0 min" and played(11130) == "3 h 5 min"
