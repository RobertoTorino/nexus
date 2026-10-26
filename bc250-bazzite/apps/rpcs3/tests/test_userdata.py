# SPDX-License-Identifier: GPL-3.0-or-later
"""RPCS3's own folder (userdata.py): vfs.yml and games.yml as RPCS3 0.0.43 writes them, its drives where they were
moved, the firmware's version as RPCS3 shows it, and the play time it counted."""

from __future__ import annotations

import time

from pathlib import Path

from conftest import write_rpcs3_files

from rpcs3_manager import userdata

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_rpcs3s_folder_follows_xdg_config_home(tmp_path):
    assert userdata.rpcs3_home() == tmp_path / "config" / "rpcs3"


def test_vfs_yml_and_the_default_drives(rpcs3_files):
    vfs = userdata.read_map(rpcs3_files / "vfs.yml")
    assert vfs["/dev_hdd0/"] == "$(EmulatorDir)dev_hdd0/" and vfs["$(EmulatorDir)"] == ""
    assert "/dev_usb***/" not in vfs and "Path" not in vfs                       # the nested map is left out
    assert userdata.drive(rpcs3_files, vfs, "/dev_hdd0/") == rpcs3_files / "dev_hdd0"
    assert userdata.drive(rpcs3_files, vfs, "/dev_flash/") == rpcs3_files / "dev_flash"
    assert userdata.drive(rpcs3_files, {}, "/games/") == rpcs3_files / "games"     # no vfs.yml: RPCS3's defaults


def test_drives_moved_elsewhere(tmp_path):
    home = write_rpcs3_files(tmp_path / "rpcs3", vfs=(
        "$(EmulatorDir): /run/media/ssd/rpcs3\n/dev_hdd0/: '/mnt/games/PS3 hdd0/'\n"
        '/dev_flash/: "$(EmulatorDir)flash/"\n'))
    vfs = userdata.read_map(home / "vfs.yml")
    assert str(userdata.drive(home, vfs, "/dev_hdd0/")) == "/mnt/games/PS3 hdd0"
    assert str(userdata.drive(home, vfs, "/dev_flash/")) == "/run/media/ssd/rpcs3/flash"
    assert str(userdata.drive(home, vfs, "/games/")) == "/run/media/ssd/rpcs3/games"


def test_games_yml(tmp_path):
    home = write_rpcs3_files(tmp_path / "rpcs3", games={"BLUS30443": "/run/media/games/PS3/Demon's Souls/",
                                                        "BLES00932": "'/games/it''s: here/'"})
    assert userdata.known_games(home) == {"BLUS30443": "/run/media/games/PS3/Demon's Souls/",
                                          "BLES00932": "/games/it's: here/"}
    assert userdata.known_games(tmp_path / "none") == {}
    (home / "games.yml").write_bytes(b"\xff\xfe")
    assert userdata.known_games(home) == {}                                       # not text: nothing, no error


def test_the_firmware_version(tmp_path):
    flash = tmp_path / "dev_flash"
    assert userdata.firmware_version(flash) == ""
    version = flash / "vsh" / "etc" / "version.txt"
    version.parent.mkdir(parents=True)
    for text, shown in (("release:04.9200:\nbuild:...", "4.92"), ("release:04.9000:", "4.90"),
                        ("release:04.8900:", "4.89"), ("release:00.3100:", "0.31"), ("nonsense", ""),
                        ("release:x.y:", "")):
        version.write_text(text)
        assert userdata.firmware_version(flash) == shown, text


def test_the_play_time_rpcs3_counted(tmp_path):
    """persistent_settings.dat: milliseconds per serial under [Playtime] (rounded up to whole seconds, as RPCS3
    shows them), the last-played date under [LastPlayed] in RPCS3's ISO form or the older spelled-out ones."""
    home = tmp_path / "rpcs3"
    assert userdata.play_times(home) == {}
    (home / "GuiConfigs").mkdir(parents=True)
    dat = home / "GuiConfigs" / "persistent_settings.dat"
    dat.write_text("[Playtime]\nBLUS30443=3723400\nNPUB30001=60000\nBLES00932=0\nBCUS98111=1\nBROKEN=x\n\n"
                   "[LastPlayed]\nBLUS30443=2026-10-24T20:15:30\nNPUB30001=October 23, 2026\n"
                   "BCUS98111=September 1 2024\n\n[Titles]\nBLUS30443=Demon's Souls\n")
    times = userdata.play_times(home)
    assert set(times) == {"BLUS30443", "NPUB30001", "BCUS98111"}                 # never played and broken left out
    assert times["BLUS30443"][0] == 3724 and times["NPUB30001"][0] == 60 and times["BCUS98111"][0] == 1
    assert time.localtime(times["BLUS30443"][1])[:6] == (2026, 10, 24, 20, 15, 30)
    assert time.localtime(times["NPUB30001"][1])[:6] == (2026, 10, 23, 0, 0, 0)
    assert time.localtime(times["BCUS98111"][1])[:6] == (2024, 9, 1, 0, 0, 0)
    assert userdata._last_played("someday") == 0 and userdata._last_played("Brumaire 3, 2026") == 0
    dat.write_text("[Playtime]\nBLUS30443=5000\n")                             # no [LastPlayed]
    assert userdata.play_times(home) == {"BLUS30443": (5, 0)}
    dat.write_bytes(b"\xff\xfe\x00")
    assert userdata.play_times(home) == {}
    assert userdata.played(3724) == "1 h 2 min" and userdata.played(90) == "1 min 30 s" and userdata.played(5) == "5 s"


# --- What the app writes for RPCS3 (owner, 24-10-2026) ----------------------------------------------------------

def test_rpcs3s_gui_settings_get_what_the_app_owns(tmp_path):
    """No CurrentSettings.ini yet: the two keys in their sections. One RPCS3 wrote: the keys set, every other line
    kept; a second run changes nothing."""
    assert userdata.prepare_gui(tmp_path, dark=False) == ["its welcome dialog off", "its own update check off"]
    path = tmp_path / userdata.GUI_SETTINGS
    assert path.read_text() == "[main_window]\ninfoBoxEnabledWelcome=false\n\n[Meta]\ncheckUpdateStart=false\n"
    stamp = path.stat().st_mtime_ns
    assert userdata.prepare_gui(tmp_path, dark=False) == [] and path.stat().st_mtime_ns == stamp
    assert userdata.prepare_gui(tmp_path, dark=True) == ["its dark style"]      # once, while none is chosen
    assert "currentStylesheet=Darker Style by TheMitoSan" in path.read_text()
    assert userdata.prepare_gui(tmp_path, dark=True) == []
    path.write_text("[GSFrame]\nvisibility=Windowed\n\n[Meta]\nattachCommandLine=false\ncheckUpdateStart=true\n"
                    "currentStylesheet=Darker Style by TheMitoSan\n\n[main_window]\nguiVolume=1\n"
                    "infoBoxEnabledWelcome=true\nlastExplorePathPUP=/somewhere\n")
    assert userdata.prepare_gui(tmp_path, dark=True) == ["its welcome dialog off", "its own update check off"]
    assert path.read_text() == ("[GSFrame]\nvisibility=Windowed\n\n[Meta]\nattachCommandLine=false\n"
                                "checkUpdateStart=false\ncurrentStylesheet=Darker Style by TheMitoSan\n\n"
                                "[main_window]\nguiVolume=1\ninfoBoxEnabledWelcome=false\nlastExplorePathPUP=/somewhere\n")
    path.write_text("[main_window]\ninfoBoxEnabledWelcome=false\n")                # one of the two set already
    assert userdata.prepare_gui(tmp_path, dark=False) == ["its own update check off"]


def test_the_pad_file_for_player_1(tmp_path):
    """Player 1 on the first controller as SDL names it, with RPCS3's default SDL mapping; two controllers of one
    name are " 1" and " 2"; a pad file RPCS3 wrote is never touched, an empty one (RPCS3's keyboard fallback) is."""
    assert userdata.pad_devices(["DualSense Edge Wireless Controller", "DualSense Edge Wireless Controller",
                                 "Xbox Series X Controller"]) == [
        "DualSense Edge Wireless Controller 1", "DualSense Edge Wireless Controller 2", "Xbox Series X Controller 1"]
    path = tmp_path / userdata.INPUT_CONFIG
    assert userdata.pads_ours(tmp_path) and userdata.pad_device(tmp_path) == ""
    assert userdata.write_pads(tmp_path, []) is False and not path.exists()
    assert userdata.write_pads(tmp_path, ["DualSense Edge Wireless Controller 1", "Other 1"])
    text = path.read_text()
    assert text.startswith(userdata.PAD_MARK + "\n" + userdata.PAD_NOTE + "\nPlayer 1 Input:\n  Handler: SDL\n"
                           '  Device: "DualSense Edge Wireless Controller 1"\n  Config:\n    Left Stick Left: LS X-\n')
    assert '    PS Button: "Back&Start,Guide"\n' in text and "    Cross: South\n" in text
    assert "    Left Stick Deadzone: 8000\n" in text and '  Buddy Device: ""\n' in text
    assert 'Player 2 Input:\n  Handler: SDL\n  Device: "Other 1"\n' in text and "Player 3" not in text
    assert userdata.pad_device(tmp_path) == "DualSense Edge Wireless Controller 1"
    assert userdata.write_pads(tmp_path, ["DualSense Edge Wireless Controller 1", "Other 1"]) is False   # the same
    assert userdata.write_pads(tmp_path, ["Other 1"]) and "DualSense" not in path.read_text()
    path.write_text("")                                                         # RPCS3's empty file
    assert userdata.pads_ours(tmp_path) and userdata.write_pads(tmp_path, ["Other 1"])
    path.write_text("Player 1 Input:\n  Handler: SDL\n  Device: DualSense Wireless Controller 1\n  Config:\n"
                    "    Cross: South\n")                                       # RPCS3's own, no mark
    assert not userdata.pads_ours(tmp_path) and userdata.write_pads(tmp_path, ["Other 1"]) is False
    assert userdata.pad_device(tmp_path) == "DualSense Wireless Controller 1"


def test_a_games_screen_in_its_own_settings(tmp_path):
    """The screen choice in custom_configs/config_<serial>.yml: made from nothing, or two lines of a file RPCS3
    wrote; read back, RPCS3's default without a file."""
    path = userdata.game_config(tmp_path, "BLUS30443")
    assert path == tmp_path / "custom_configs" / "config_BLUS30443.yml"
    assert userdata.read_screen(path) == userdata.WIDE
    userdata.write_screen(path, userdata.NARROW)
    assert path.read_text() == "Video:\n  Stretch To Display Area: false\n  Aspect ratio: 4:3\n"
    assert userdata.read_screen(path) == userdata.NARROW
    userdata.write_screen(path, userdata.FILL)
    assert path.read_text() == "Video:\n  Stretch To Display Area: true\n  Aspect ratio: 16:9\n"
    assert userdata.read_screen(path) == userdata.FILL
    path.write_text("Audio:\n  Renderer: Cubeb\nVideo:\n  Aspect ratio: 16:9\n  Vulkan:\n    Adapter: AMD\n"
                    "  Stretch To Display Area: false\n")
    userdata.write_screen(path, userdata.WIDE)
    assert path.read_text() == ("Audio:\n  Renderer: Cubeb\nVideo:\n  Aspect ratio: 16:9\n  Vulkan:\n    Adapter: AMD\n"
                                "  Stretch To Display Area: false\n")
    path.write_text("Audio:\n  Renderer: Cubeb\n")                               # no Video section
    userdata.write_screen(path, userdata.FILL)
    assert path.read_text() == "Audio:\n  Renderer: Cubeb\nVideo:\n  Stretch To Display Area: true\n  Aspect ratio: 16:9\n"
    assert userdata.SCREENS == {"wide": "16:9", "narrow": "4:3", "fill": "Fill screen"}


def test_packages_and_licenses_in_a_folder(tmp_path):
    """The folder's own files, by name, as RPCS3 takes them from a folder: not a subfolder's."""
    (tmp_path / "pkgs" / "sub").mkdir(parents=True)
    (tmp_path / "pkgs" / "b.pkg").write_bytes(b"")
    (tmp_path / "pkgs" / "A.PKG").write_bytes(b"")
    (tmp_path / "pkgs" / "sub" / "c.pkg").write_bytes(b"")
    (tmp_path / "pkgs" / "a.rap").write_bytes(b"")
    (tmp_path / "pkgs" / "d.EDAT").write_bytes(b"")
    (tmp_path / "pkgs" / "readme.txt").write_bytes(b"")
    pkgs, licenses = userdata.packages(tmp_path / "pkgs")
    assert [p.name for p in pkgs] == ["A.PKG", "b.pkg"] and [p.name for p in licenses] == ["a.rap", "d.EDAT"]
    assert userdata.packages(tmp_path / "none") == ([], [])
    hdd0 = tmp_path / "dev_hdd0"
    assert userdata.licenses(hdd0) == []
    (hdd0 / "home" / "00000001" / "exdata").mkdir(parents=True)
    (hdd0 / "home" / "00000001" / "exdata" / "x.rap").write_bytes(b"")
    (hdd0 / "home" / "00000001" / "exdata" / "y.txt").write_bytes(b"")
    assert [p.name for p in userdata.licenses(hdd0)] == ["x.rap"]


def test_a_packages_header(tmp_path):
    """The unencrypted header and metadata of a PKG file (the first 288 bytes of the owner's three Lumines
    Supernova packages): the content ID, and the PATCH flag that marks the game's update."""
    game, update, dlc = (userdata.package_info(FIXTURES / name) for name in ("game.pkg.head", "update.pkg.head",
                                                                             "dlc.pkg.head"))
    assert game.valid and game.content_id == "UP4055-NPUB30048_00-LUMINES000000001" and not game.patch
    assert update.valid and update.content_id == game.content_id and update.patch
    assert dlc.valid and dlc.content_id == "UP4055-NPUB30048_00-LUMINES000000002" and not dlc.patch
    assert game.serial == update.serial == dlc.serial == "NPUB30048"
    (tmp_path / "short.pkg").write_bytes(b"\x7fPKG")
    (tmp_path / "other.pkg").write_bytes(b"\0" * 0x200)
    for name in ("short.pkg", "other.pkg", "missing.pkg"):
        info = userdata.package_info(tmp_path / name)
        assert not info.valid and info.content_id == "" and info.serial == "" and not info.patch
    # The order RPCS3 gets them in: games and DLC by name, the updates after them, what is no package last.
    for name, head in (("A-Update.pkg", "update.pkg.head"), ("z.pkg", "dlc.pkg.head"), ("M.PKG", "game.pkg.head")):
        (tmp_path / name).write_bytes((FIXTURES / head).read_bytes())
    order = userdata.install_order([tmp_path / n for n in ("other.pkg", "A-Update.pkg", "z.pkg", "M.PKG")])
    assert [i.path.name for i in order] == ["M.PKG", "z.pkg", "A-Update.pkg", "other.pkg"]


def test_what_rpcs3s_log_says_of_an_install(tmp_path):
    """The install lines RPCS3's main window writes to its log, read back; two runs' reports added up."""
    text = """\ufeffRPCS3 v0.0.43-20133-53d44aa4 Alpha | master
·! 0:00:00.078323 GUI: PKG: Trying to install packages from dir: '/x/pkgs'
·S 0:00:00.1 GUI: Successfully copied rap file: UP4055-NPUB30048_00-LUMINES000000001.rap
·E 0:00:00.2 GUI: Could not copy edat file: bad.edat
·S 0:01:03.1 GUI: Successfully installed /x/pkgs/Game (1).pkg (title_id=NPUB30048, title=LUMINES™ Supernova, version=01.00).
·E 0:01:03.2 GUI: Failed to install /x/pkgs/b.pkg (title_id=BLUS30001, title=Other, version=01.01).
·E 0:01:03.3 GUI: Partially installed /x/pkgs/c.pkg (title_id=BLUS30002, title=Third, version=).
·! 0:01:03.4 GUI: Aborted installation of /x/pkgs/d.pkg (title_id=, title=Fourth, version=01.00).
·E 0:00:00.3 GUI: Cannot install invalid package: ''
"""
    report = userdata.install_report(text)
    assert report.installed == [("LUMINES™ Supernova", "NPUB30048")]
    assert report.failed == [("Other", "BLUS30001"), ("Third", "BLUS30002"), ("Fourth", "")]
    assert report.invalid == 1 and report.copied == ["UP4055-NPUB30048_00-LUMINES000000001.rap"]
    assert report.not_copied == ["bad.edat"] and not report.no_files and report.problems
    assert not userdata.install_report("").problems
    assert userdata.install_report("·! 0:00:00.1 GUI: PKG: Could not find any files in dir: '/x'\n").no_files
    assert userdata.read_install_report(tmp_path / "none") == userdata.InstallReport()
    (tmp_path / "RPCS3.log").write_text(text, encoding="utf-8")
    again = userdata.read_install_report(tmp_path / "RPCS3.log")
    again.extend(userdata.install_report("·S 0:00:00.1 GUI: Successfully copied edat file: e.edat\n"))
    assert again.installed == report.installed and again.copied == [report.copied[0], "e.edat"]
    assert userdata.rpcs3_log().name == "RPCS3.log" and userdata.rpcs3_log().parent.name == "rpcs3"


def test_whether_rpcs3_runs(tmp_path):
    """RPCS3's process is rpcs3, or AppRun.wrapped running rpcs3 (the AppImage's link); a zombie does not count."""
    proc = tmp_path / "proc"
    for pid, comm, state, exe in (("10", "bash", "S", "/usr/bin/bash"), ("11", "AppRun.wrapped", "S", "/x/usr/bin/rpcs3"),
                                  ("12", "rpcs3", "Z", "/y/rpcs3")):
        (proc / pid).mkdir(parents=True)
        (proc / pid / "comm").write_text(comm + "\n")
        (proc / pid / "stat").write_text(f"{pid} ({comm}) {state} 1 1\n")
        (proc / pid / "exe").symlink_to(exe)
    assert userdata.rpcs3_running(proc)
    (proc / "11" / "stat").write_text("11 (AppRun.wrapped) Z 1 1\n")
    assert not userdata.rpcs3_running(proc)
    (proc / "12" / "stat").write_text("12 (rpcs3) R 1 1\n")
    assert userdata.rpcs3_running(proc)
    (proc / "11" / "exe").unlink()
    (proc / "11" / "exe").symlink_to("/x/usr/bin/other")
    (proc / "11" / "stat").write_text("11 (AppRun.wrapped) S 1 1\n")
    (proc / "12" / "stat").write_text("12 (rpcs3) X 1 1\n")
    assert not userdata.rpcs3_running(proc)
