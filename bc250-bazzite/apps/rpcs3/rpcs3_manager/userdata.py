# SPDX-License-Identifier: GPL-3.0-or-later
"""RPCS3's own folder, ~/.config/rpcs3 (its settings, firmware, saves and installed games), as RPCS3 0.0.43 lays it
out on Linux (fs::get_config_dir, cfg_vfs): vfs.yml says where its virtual PS3 drives are, games.yml which disc games
it knows (title ID: folder), and the firmware's version is in dev_flash/vsh/etc/version.txt. The app reads these
files and never writes them; RPCS3 does that.

Both .yml files are YAML maps as RPCS3 writes them (yaml-cpp): one "key: value" a line, a value in quotes when it
needs them. The app reads only the top level of those maps (vfs.yml has a nested map for USB drives, which it does
not need), so it needs no YAML library.

The PS3's firmware (PS3UPDAT.PUP) is not ours to give: the app cannot ship it, and RPCS3 needs it to start any
game. RPCS3 installs it (--installfw) into dev_flash.

RPCS3 also counts the time spent in each game, in GuiConfigs/persistent_settings.dat (an INI file for all its name,
as RPCS3 0.0.43 writes it: gui_application::UpdatePlaytime, persistent_settings): [Playtime] holds the milliseconds
per serial, [LastPlayed] when it was last played, as an ISO date and time ("2026-10-24T20:15:30"; older RPCS3
wrote "October 24, 2026", which RPCS3 still reads, so the app does too). The app shows the sum in its header, each
game in the tip (owner, 24-10-2026: as PCSX2 Manager does).

What the app writes for RPCS3 (owner, 24-10-2026: the emulator only runs the game, the manager does the rest; as
PCSX2 Manager's pcsx2_settings), never while RPCS3 runs, since RPCS3 writes its own files when it closes:

* RPCS3's GUI settings, GuiConfigs/CurrentSettings.ini (a Qt INI, gui_settings.h): its welcome dialog off
  (ib_show_welcome; the dialog waits for a tick in "I have read the Quickstart guide" before RPCS3's window opens,
  with "Show at startup" ticked) and its own update check off (m_check_upd_start; RPCS3's window offered a newer
  build on the board and replaced the installed one with it, after which its config.yml held keys the other build
  did not know and RPCS3 asked to remove "obsolete settings"). And, once, RPCS3's dark style when the suite's theme
  is dark (m_currentStylesheet; the welcome dialog would have ticked "Use Dark Theme" for a dark desktop).
* Player 1 on the first controller, input_configs/global/Default.yml (cfg_input in pad_config.h): RPCS3 starts a
  game with the keyboard as player 1 while that file is empty (cfg_input::load), as it was on the board. The app
  writes RPCS3's SDL handler with RPCS3's own default mapping for it (sdl_pad_handler::init_config) and the
  controller as SDL names it, with RPCS3's " 1" after the name (sdl_pad_handler::enumerate_devices; a second
  controller of the same name is " 2"); a name RPCS3 has not seen yet it keeps as a device to attach when a
  controller of that name appears. In that mapping the PS Button is "Back&Start,Guide": Select (Share) and Start
  (Options) together, or the Guide button, open RPCS3's home menu in the game, with Exit Game in it; RPCS3 has
  no chord that quits a game outright (pad_thread::open_home_menu is the only pad way out). The file starts with a comment of the app's, which RPCS3's own Pads settings
  drop when they save: a file RPCS3 wrote is never touched.
* How a game fills the screen, custom_configs/config_<serial>.yml, the game's own settings in RPCS3, as its own
  window writes them (rpcs3::utils::get_custom_config_path): the PS3's picture for a wide screen (16:9), for a 4:3
  screen, or stretched to fill the window ([Video] Aspect ratio and Stretch To Display Area). A file RPCS3 wrote
  (its whole config) is changed in those two lines only; RPCS3 reads what the file has and keeps its defaults for
  the rest (cfg::decode).

One more file of another program the app only reads: RPCS3's own log, ~/.cache/rpcs3/RPCS3.log (fs::get_cache_dir;
RPCS3 starts a new one on every start and keeps the one before it as RPCS3.log.gz), for what a headless install of
packages did (owner, 24-10-2026: --installpkg without RPCS3's window; the lines main_window::InstallPackages and
HandlePackageInstallation write). The volume the desktop remembers for RPCS3's sound (found muted on the board,
24-10-2026) is core's sound.py: RPCS3's stream is named "RPCS3"."""

from __future__ import annotations

import configparser
import os
import re
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path

from bc250_core.platform import config_home
from bc250_core.theme import THEME

EMULATOR_DIR = "$(EmulatorDir)"
# vfs.yml's keys and RPCS3's defaults for them (vfs_config.h).
DRIVES = {"/dev_hdd0/": "$(EmulatorDir)dev_hdd0/", "/dev_flash/": "$(EmulatorDir)dev_flash/",
          "/games/": "$(EmulatorDir)games/"}
FIRMWARE_PAGE = "https://www.playstation.com/en-us/support/hardware/ps3/system-software/"


def rpcs3_home() -> Path:
    return config_home() / "rpcs3"


def _scalar(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] == "'":
        return text[1:-1].replace("''", "'")
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return text[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return text


def read_map(path: Path) -> dict[str, str]:
    """The top level of a YAML map as RPCS3 writes it; {} when the file is not there or cannot be read. A key whose
    value is a nested map is left out."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return {}
    found = {}
    for line in lines:
        if not line or line[0] in " \t#-" or line.startswith("---"):
            continue
        if line[0] in "'\"":
            end = line.find(line[0] + ":", 1)
            if end < 0:
                continue
            key, value = _scalar(line[:end + 1]), line[end + 2:]
        else:
            key, sep, value = line.partition(": ")
            if not sep:
                continue                        # "key:" alone: a nested map follows
        if value.strip():
            found[key] = _scalar(value)
    return found


def drive(home: Path, vfs: dict[str, str], key: str) -> Path:
    """Where one of RPCS3's virtual drives is (vfs.yml, else RPCS3's default), $(EmulatorDir) resolved."""
    emulator_dir = vfs.get(EMULATOR_DIR, "") or str(home)
    path = vfs.get(key, "") or DRIVES[key]
    return Path(path.replace(EMULATOR_DIR, emulator_dir.rstrip("/") + "/"))


def known_games(home: Path) -> dict[str, str]:
    """games.yml: the disc games RPCS3 knows, title ID: folder (RPCS3 adds a disc game when it first starts it)."""
    return read_map(home / "games.yml")


def firmware_version(dev_flash: Path) -> str:
    """The installed firmware's version as RPCS3 shows it ("4.92"); "" when none is installed. version.txt starts
    "release:04.9200:", the version between the first two colons (sysinfo.cpp: get_firmware_version)."""
    try:
        text = (dev_flash / "vsh" / "etc" / "version.txt").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    parts = text.split(":")
    if len(parts) < 3:
        return ""
    major, _, minor = parts[1].strip().partition(".")
    if not major.isdigit() or not minor.isdigit():
        return ""
    minor = minor.rstrip("0")
    return f"{int(major)}.{minor.ljust(2, '0')}"


# --- Play time --------------------------------------------------------------------------------------------------

PERSISTENT = Path("GuiConfigs") / "persistent_settings.dat"
_ISO = re.compile(r"(\d{4})-(\d\d)-(\d\d)(?:[T ](\d\d):(\d\d)(?::(\d\d))?)?(?:\.\d+)?(?:Z|[+-]\d\d:?\d\d)?")
_WORDS = re.compile(r"([A-Za-z]+) (\d{1,2}),? (\d{4})(?: (\d\d):(\d\d))?")
_MONTHS = {name: n for n, name in enumerate(("January", "February", "March", "April", "May", "June", "July",
                                             "August", "September", "October", "November", "December"), 1)}


def _last_played(text: str) -> int:
    """RPCS3's last-played date as Unix time; 0 when it is not one it ever wrote."""
    if m := _ISO.fullmatch(text.strip()):
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hour, minute, second = (int(m.group(n) or 0) for n in (4, 5, 6))
    elif m := _WORDS.fullmatch(text.strip()):
        month = _MONTHS.get(m.group(1).capitalize(), 0)
        year, day = int(m.group(3)), int(m.group(2))
        hour, minute, second = int(m.group(4) or 0), int(m.group(5) or 0), 0
    else:
        return 0
    try:
        return int(time.mktime((year, month, day, hour, minute, second, 0, 0, -1))) if month else 0
    except (OverflowError, ValueError):
        return 0


def play_times(home: Path) -> dict[str, tuple[int, int]]:
    """The play time RPCS3 counted per game, serial: (seconds, last played as Unix time, 0 when unknown); {}
    without the file. A game never played (0 ms) is left out."""
    ini = configparser.ConfigParser(interpolation=None, strict=False)
    ini.optionxform = str                               # the serials as RPCS3 writes them
    try:
        if not ini.read(home / PERSISTENT, encoding="utf-8"):
            return {}
    except (configparser.Error, UnicodeDecodeError):
        return {}
    times: dict[str, tuple[int, int]] = {}
    for serial, value in (ini.items("Playtime") if ini.has_section("Playtime") else []):
        if value.strip().isdigit() and int(value):
            last = ini.get("LastPlayed", serial, fallback="") if ini.has_section("LastPlayed") else ""
            times[serial] = (-(-int(value) // 1000), _last_played(last))      # whole seconds, as RPCS3 rounds
    return times


def played(seconds: int) -> str:
    """A play time in words: "3 h 5 min", "12 min", "40 s"."""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min" + (f" {secs} s" if secs else "")
    return f"{secs} s"


# --- What the app writes for RPCS3 ------------------------------------------------------------------------------

GUI_SETTINGS = Path("GuiConfigs") / "CurrentSettings.ini"
# The GUI settings the app owns: section, key, value, and what it did in the app's words.
GUI_OWNED = (("main_window", "infoBoxEnabledWelcome", "false", "its welcome dialog off"),
             ("Meta", "checkUpdateStart", "false", "its own update check off"))
DARK_STYLE = "Darker Style by TheMitoSan"      # RPCS3's own dark style (gui::DarkStylesheet)
INPUT_CONFIG = Path("input_configs") / "global" / "Default.yml"
PAD_MARK = "# Written by RPCS3 Manager: player 1 on the first controller, through RPCS3's SDL handler."
PAD_NOTE = "# RPCS3's own Pads settings replace this file when they are saved; the app leaves that file alone."
# RPCS3's default mapping for its SDL handler (sdl_pad_handler::init_config), as RPCS3 0.0.43 writes it.
SDL_MAPPING = (("Left Stick Left", "LS X-"), ("Left Stick Down", "LS Y-"), ("Left Stick Right", "LS X+"),
               ("Left Stick Up", "LS Y+"), ("Right Stick Left", "RS X-"), ("Right Stick Down", "RS Y-"),
               ("Right Stick Right", "RS X+"), ("Right Stick Up", "RS Y+"), ("Start", "Start"), ("Select", "Back"),
               ("PS Button", "Back&Start,Guide"), ("Square", "West"), ("Cross", "South"), ("Circle", "East"),
               ("Triangle", "North"), ("Left", "Left"), ("Down", "Down"), ("Right", "Right"), ("Up", "Up"),
               ("R1", "RB"), ("R2", "RT"), ("R3", "RS"), ("L1", "LB"), ("L2", "LT"), ("L3", "LS"),
               ("Left Stick Deadzone", "8000"), ("Right Stick Deadzone", "8000"),
               ("Left Stick Anti-Deadzone", "4259"), ("Right Stick Anti-Deadzone", "4259"))
CUSTOM_CONFIGS = "custom_configs"
WIDE, NARROW, FILL = "wide", "narrow", "fill"
SCREENS = {WIDE: "16:9", NARROW: "4:3", FILL: "Fill screen"}
# What each screen choice sets under Video: (Aspect ratio, Stretch To Display Area).
SCREEN_VALUES = {WIDE: ("16:9", "false"), NARROW: ("4:3", "false"), FILL: ("16:9", "true")}
PACKAGE_SUFFIXES = (".pkg",)
LICENSE_SUFFIXES = (".rap", ".edat")
PKG_MAGIC = b"\x7fPKG"
PKG_FLAG_PATCH = 0x10                   # in the package type (unpkg.h, pkg_flag::PKG_FLAG_PATCH): a game's update


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    work = path.with_name(f".{path.name}.{os.getpid()}")
    work.write_text(text, encoding="utf-8")
    work.replace(path)


def write_lines(path: Path, lines: list[str]) -> None:
    """*lines* as the file, one a line, ending in a newline."""
    _write(path, "\n".join(lines) + "\n")


def rpcs3_running(proc: Path = Path("/proc")) -> bool:
    """Whether RPCS3 runs: its AppImage starts usr/bin/rpcs3 through the link AppRun.wrapped, so the process is
    called either, with rpcs3 as its program; a zombie does not count, as in core's steam_running."""
    for folder in proc.glob("[0-9]*"):
        try:
            comm = (folder / "comm").read_text().strip()
            if comm != "rpcs3" and not (comm == "AppRun.wrapped" and os.readlink(folder / "exe").endswith("/rpcs3")):
                continue
            state = (folder / "stat").read_text().rsplit(")", 1)[1].split()[0]
        except (OSError, IndexError):
            continue
        if state not in ("Z", "X"):
            return True
    return False


# --- RPCS3's GUI settings ---------------------------------------------------------------------------------------

def _ini_find(lines: list[str], section: str, key: str) -> tuple[int, int]:
    """(the section's last line, the key's line) in a Qt INI, -1 for each that is not there."""
    current, end, at = None, -1, -1
    for n, line in enumerate(lines):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            current = s[1:-1]
            continue
        if current == section:
            if s:
                end = n
            if at < 0 and "=" in s and s.split("=", 1)[0].strip() == key:
                at = n
    if end < 0:
        end = next((n for n, line in enumerate(lines) if line.strip() == f"[{section}]"), -1)
    return end, at


def ini_value(lines: list[str], section: str, key: str) -> str | None:
    _end, at = _ini_find(lines, section, key)
    return lines[at].split("=", 1)[1].strip() if at >= 0 else None


def ini_set(lines: list[str], section: str, key: str, value: str) -> None:
    """Sets one key, as Qt writes it (key=value under [section]); every other line stays."""
    end, at = _ini_find(lines, section, key)
    line = f"{key}={value}"
    if at >= 0:
        lines[at] = line
    elif end >= 0:
        lines.insert(end + 1, line)
    else:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ([""] if lines else []) + [f"[{section}]", line, ""]


def prepare_gui(home: Path, dark: bool = THEME.dark) -> list[str]:
    """Brings RPCS3's GUI settings to what the app owns (GUI_OWNED, and RPCS3's dark style while none is chosen and
    *dark* says the suite is); returns what changed, [] when nothing did. OSError is the caller's; the caller makes
    sure RPCS3 does not run."""
    path = home / GUI_SETTINGS
    before = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = before.split("\n") if before else []
    done = []
    for section, key, value, said in GUI_OWNED:
        if ini_value(lines, section, key) != value:
            ini_set(lines, section, key, value)
            done.append(said)
    if dark and ini_value(lines, "Meta", "currentStylesheet") is None:
        ini_set(lines, "Meta", "currentStylesheet", DARK_STYLE)
        done.append("its dark style")
    if done:
        _write(path, "\n".join(lines) + ("" if lines and not lines[-1] else "\n"))
    return done


# --- Player 1 on the first controller ---------------------------------------------------------------------------

def pad_devices(names: list[str]) -> list[str]:
    """RPCS3's device names for the controllers as SDL names them: the name with " 1" after it, a second one of
    the same name " 2" (sdl_pad_handler::enumerate_devices)."""
    seen: dict[str, int] = {}
    devices = []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        devices.append(f"{name} {seen[name]}")
    return devices


def pads_ours(home: Path) -> bool:
    """Whether the app may write the pad file: there is none, it is empty (RPCS3 then plays with the keyboard), or
    the app wrote it. A file RPCS3's own Pads settings wrote is left alone."""
    try:
        text = (home / INPUT_CONFIG).read_text(encoding="utf-8")
    except OSError:
        return True
    return not text.strip() or text.startswith(PAD_MARK)


def pad_device(home: Path) -> str:
    """Player 1's device as the pad file names it, "" without one (RPCS3's or the app's alike)."""
    try:
        lines = (home / INPUT_CONFIG).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    player = False
    for line in lines:
        if not line.startswith(" ") and not line.startswith("#"):
            player = line.startswith("Player 1 Input:")
        elif player and line.startswith("  Device:"):
            return _scalar(line.split(":", 1)[1])
    return ""


def _yaml_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def pad_text(devices: list[str]) -> str:
    """The pad file: each controller a player, on RPCS3's SDL handler with its default mapping; the other players
    keep RPCS3's defaults (none)."""
    out = [PAD_MARK, PAD_NOTE]
    for n, device in enumerate(devices, 1):
        out += [f"Player {n} Input:", "  Handler: SDL", f"  Device: {_yaml_string(device)}", "  Config:"]
        out += [f"    {key}: {_yaml_string(value) if '&' in value or ',' in value else value}"
                for key, value in SDL_MAPPING]
        out.append('  Buddy Device: ""')
    return "\n".join(out) + "\n"


def write_pads(home: Path, devices: list[str]) -> bool:
    """Writes the pad file for *devices* when the app may (pads_ours) and it says something else; whether it did.
    OSError is the caller's; the caller makes sure RPCS3 does not run."""
    if not devices or not pads_ours(home):
        return False
    text = pad_text(devices)
    path = home / INPUT_CONFIG
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    _write(path, text)
    return True


# --- How a game fills the screen --------------------------------------------------------------------------------

def game_config(home: Path, serial: str) -> Path:
    return home / CUSTOM_CONFIGS / f"config_{serial}.yml"


def _yaml_find(lines: list[str], section: str, key: str) -> tuple[int, int]:
    """(the line of the top-level *section*, the line of *key* two spaces in under it), -1 for each not there."""
    at_section, at_key = -1, -1
    for n, line in enumerate(lines):
        if not line or line[0] == "#":
            continue
        if not line[0].isspace():
            if at_section >= 0:
                break
            if line.startswith(section + ":"):
                at_section = n
        elif at_section >= 0 and line.startswith("  ") and not line.startswith("   ") \
                and line.strip().startswith(key + ":"):
            at_key = n
            break
    return at_section, at_key


def yaml_value(lines: list[str], section: str, key: str) -> str | None:
    _at, at_key = _yaml_find(lines, section, key)
    return _scalar(lines[at_key].split(":", 1)[1]) if at_key >= 0 else None


def yaml_set(lines: list[str], section: str, key: str, value: str) -> None:
    """Sets one key of a top-level map, as RPCS3 writes it (two spaces in); every other line stays."""
    at_section, at_key = _yaml_find(lines, section, key)
    line = f"  {key}: {value}"
    if at_key >= 0:
        lines[at_key] = line
    elif at_section >= 0:
        lines.insert(at_section + 1, line)
    else:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += [f"{section}:", line]


def read_screen(path: Path) -> str:
    """The screen choice a game's own settings hold; WIDE (RPCS3's default) without one."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return WIDE
    if yaml_value(lines, "Video", "Stretch To Display Area") == "true":
        return FILL
    return NARROW if yaml_value(lines, "Video", "Aspect ratio") == "4:3" else WIDE


def write_screen(path: Path, screen: str) -> None:
    """Writes the screen choice into the game's own settings, making the file when there is none. OSError is the
    caller's; the caller makes sure RPCS3 does not run."""
    aspect, stretch = SCREEN_VALUES[screen]
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    yaml_set(lines, "Video", "Aspect ratio", aspect)
    yaml_set(lines, "Video", "Stretch To Display Area", stretch)
    write_lines(path, lines)


# --- Packages ---------------------------------------------------------------------------------------------------

def packages(folder: Path) -> tuple[list[Path], list[Path]]:
    """(the .pkg files, the .rap and .edat licenses) in *folder* itself, by name: the files RPCS3 takes from a
    folder (main_window::InstallPackages with gui::utils::get_dir_entries, QDir::Files: the folder's own files, not
    its subfolders')."""
    try:
        found = sorted((p for p in folder.iterdir() if p.is_file()), key=lambda p: p.name.lower())
    except OSError:
        return [], []
    pkgs = [p for p in found if p.suffix.lower() in PACKAGE_SUFFIXES]
    licenses = [p for p in found if p.suffix.lower() in LICENSE_SUFFIXES]
    return pkgs, licenses


@dataclass(frozen=True)
class PackageInfo:
    """What a PKG file's header says of it, unencrypted (unpkg.h: PKGHeader, then the metadata items; RPCS3's
    package_reader::read_metadata reads the same): its content ID (the serial is in it), and whether it is a
    game's update (the PATCH flag in its package type). valid is False for a file that is no PS3 package."""
    path: Path
    content_id: str = ""
    patch: bool = False
    valid: bool = False

    @property
    def serial(self) -> str:
        """NPUB30048 out of UP4055-NPUB30048_00-LUMINES000000001."""
        return self.content_id[7:16] if len(self.content_id) >= 16 else ""


def package_info(path: Path) -> PackageInfo:
    """Reads the header and the metadata items of a PKG file (the first few hundred bytes). A file that cannot be
    read, or is no PS3 package, is returned with valid False."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(0x80)
            if len(head) < 0x80 or head[:4] != PKG_MAGIC:
                return PackageInfo(path)
            meta_offset, meta_count = struct.unpack(">II", head[8:16])
            content_id = head[48:96].split(b"\0", 1)[0].decode("ascii", "replace")
            handle.seek(meta_offset)
            patch = False
            for _ in range(min(meta_count, 64)):
                item = handle.read(8)
                if len(item) < 8:
                    break
                item_id, size = struct.unpack(">II", item)
                data = handle.read(size)
                if item_id == 0x3 and size == 4:        # the package type (flags)
                    patch = bool(struct.unpack(">I", data)[0] & PKG_FLAG_PATCH)
    except (OSError, struct.error):
        return PackageInfo(path)
    return PackageInfo(path, content_id, patch, True)


def install_order(pkgs: list[Path]) -> list[PackageInfo]:
    """The order to hand RPCS3 the packages one by one: the games and their DLC first, by name, then the updates,
    by name. An update asks RPCS3 for the installed game's version (package_reader::check_target_app_version)
    and fails without the game, which in one run of RPCS3 with the whole folder (its files in name order, an
    update's name before its game's) stops everything after it; so each file goes in a run of its own, the
    updates last. A file that is no PS3 package goes last of all: RPCS3 says so in its log."""
    infos = [package_info(p) for p in pkgs]
    return sorted(infos, key=lambda i: (not i.valid, i.patch, i.path.name.lower()))


def licenses(hdd0: Path) -> list[Path]:
    """The .rap and .edat licenses RPCS3 keeps, for any of its users (dev_hdd0/home/<user>/exdata)."""
    try:
        return sorted(p for p in (hdd0 / "home").glob("*/exdata/*") if p.suffix.lower() in LICENSE_SUFFIXES)
    except OSError:
        return []


# --- RPCS3's log: what a headless install did -----------------------------------------------------------------

RPCS3_LOG = "RPCS3.log"
_INSTALLED = re.compile(r"GUI: Successfully installed (?P<path>.*) \(title_id=(?P<id>[^,]*), title=(?P<title>.*), "
                        r"version=(?P<version>[^)]*)\)\.$")
_NOT_INSTALLED = re.compile(r"GUI: (?:Failed to install|Partially installed|Aborted installation of) (?P<path>.*) "
                            r"\(title_id=(?P<id>[^,]*), title=(?P<title>.*), version=[^)]*\)\.$")
_INVALID = re.compile(r"GUI: Cannot install invalid package: '(?P<path>.*)'$")
_COPIED = re.compile(r"GUI: Successfully copied (?:rap|edat) file: (?P<name>.*)$")
_NOT_COPIED = re.compile(r"GUI: Could not copy (?:rap|edat) file: (?P<name>.*)$")
_NO_FILES = "GUI: PKG: Could not find any files in dir:"


def rpcs3_cache() -> Path:
    """RPCS3's cache folder on Linux (fs::get_cache_dir): $XDG_CACHE_HOME/rpcs3, ~/.cache/rpcs3 by default."""
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "rpcs3"


def rpcs3_log() -> Path:
    return rpcs3_cache() / RPCS3_LOG


@dataclass
class InstallReport:
    """What RPCS3's log says of an install: the games installed (title, serial), the packages it could not
    install (title, serial), how many files were no PS3 package, the licenses copied and the ones it could not
    copy, and whether it found any file at all."""
    installed: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    invalid: int = 0
    copied: list[str] = field(default_factory=list)
    not_copied: list[str] = field(default_factory=list)
    no_files: bool = False

    @property
    def problems(self) -> bool:
        return bool(self.failed or self.invalid or self.not_copied)

    def extend(self, other: InstallReport) -> None:
        """Another run's report added (RPCS3 is run once per file)."""
        self.installed += other.installed
        self.failed += other.failed
        self.invalid += other.invalid
        self.copied += other.copied
        self.not_copied += other.not_copied
        self.no_files = self.no_files or other.no_files


def install_report(text: str) -> InstallReport:
    """The install lines of one RPCS3 run, in the order RPCS3 wrote them (gui_log in main_window.cpp: the licenses
    first, then each package's result)."""
    report = InstallReport()
    for line in text.splitlines():
        line = line.rstrip()
        if (found := _INSTALLED.search(line)) is not None:
            report.installed.append((found["title"], found["id"]))
        elif (found := _NOT_INSTALLED.search(line)) is not None:
            report.failed.append((found["title"], found["id"]))
        elif _INVALID.search(line) is not None:
            report.invalid += 1
        elif (found := _COPIED.search(line)) is not None:
            report.copied.append(found["name"])
        elif (found := _NOT_COPIED.search(line)) is not None:
            report.not_copied.append(found["name"])
        elif _NO_FILES in line:
            report.no_files = True
    return report


def read_install_report(path: Path | None = None) -> InstallReport:
    """The report from RPCS3's log file (its last run); empty when there is none."""
    try:
        return install_report((path or rpcs3_log()).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return InstallReport()
