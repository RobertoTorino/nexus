# SPDX-License-Identifier: GPL-3.0-or-later
"""Vita3K's own files, which in its portable mode are all in portable\\ beside Vita3K.exe (emulator.py's folder, "home"
below), as build 4186 lays them out there (app::init_paths): its settings in config.yml, its log in vita3k.log (written
anew at every start) and the PS Vita's storage, its "Vita FS", in fs\\.

config.yml is a YAML map as Vita3K writes it (yaml-cpp, between "---" and "..."): one "key: value" a line at the top
level, lists below their key indented. The app reads and writes only the top level, so it needs no YAML library.
Vita3K reads every key it knows and keeps its default for a key the file does not name (config::update_members), and
writes the whole file again when it starts, so a line the app wrote stays.

What the app writes in config.yml (prepare; the BC250 suite's rule, owner 24-10-2026: the emulator only runs the
game, the manager does the rest), never while Vita3K runs: a game full screen (boot-apps-full-screen: owner,
29-10-2026, Vita3K's own frontend boots the game from Steam), its welcome window off (show-welcome) and its own update
check off (check-for-updates-mode 0, UPDATE_STARTUP_OFF), which would offer a build the app was not tried with.

The PS Vita's firmware is not ours to give: the app cannot ship it, and Vita3K needs it to start most games. It
comes in three files, each named PSP2UPDAT.PUP and each downloaded from Sony: the system software (it fills vs0,
os0), the font package (sa0) and the preinstalled apps (pd0). Vita3K installs any of them (--firmware) and counts a
part as installed when its folder holds anything (app::get_firmware_state); its own window warns before a game when
the firmware or the fonts are missing. The preinstalled apps are optional.

Vita3K says nothing of a file it could not use: it quits as after an install (on a file that is no PUP it only
warns that the PUP had no version.txt). What it installed shows in the files it wrote, all of them new: the parts of
the firmware (firmware_written), and a game, an update or extra content in ux0\\app, ux0\\patch or ux0\\addcont
(content_written)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import emulator

CONFIG = "config.yml"
LOG = "vita3k.log"
FIRMWARE_PAGE = "https://www.playstation.com/en-us/support/hardware/psvita/system-software/"
# Sony's files that Vita3K's own welcome window links to (through short links, resolved here).
FONTS_URL = ("http://dus01.psp2.update.playstation.net/update/psp2/image/2019_0924/"
             "sd_8b5f60b56c3da8365b973dba570c53a5/PSP2UPDAT.PUP?dest=us")
PREINSTALL_URL = ("http://dus01.psp2.update.playstation.net/update/psp2/image/2022_0209/"
                  "pre_efd1ef6c1cc2fe92e72e9e783e421237/PSP2UPDAT.PUP?dest=us")
FIRMWARE_SUFFIXES = (".pup",)
ARCHIVE_SUFFIXES = (".vpk", ".zip")
PACKAGE_SUFFIXES = (".pkg",)
# config.yml's lines the app owns: (key, value, what it is, for the log)
OWNED = (("boot-apps-full-screen", "true", "games full screen"),
         ("show-welcome", "false", "its welcome window off"),
         ("check-for-updates-mode", "0", "its update check off"))
CONTENT = (("app", "game"), ("patch", "update"), ("addcont", "extra content"))   # ux0's folders, what each holds
ZRIF = re.compile(r"[A-Za-z0-9+/=_-]+")


def folder(home: Path) -> Path:
    return emulator.portable_folder(home)


def config_path(home: Path) -> Path:
    return folder(home) / CONFIG


def vita_fs(home: Path) -> Path:
    """The PS Vita's storage: in portable mode always fs\\ in the portable folder (config::init_config)."""
    return folder(home) / "fs"


def log_path(home: Path) -> Path:
    return folder(home) / LOG


# --- config.yml --------------------------------------------------------------------------------------------------

def _scalar(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] == "'":
        return text[1:-1].replace("''", "'")
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return text[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return text


def _lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []


def read_map(path: Path) -> dict[str, str]:
    """The top level of a YAML map as Vita3K writes it; {} when the file is not there or cannot be read. A key whose
    value is a list or a map below it is left out."""
    found = {}
    for line in _lines(path):
        if not line or line[0] in " \t#-." or line.startswith("---"):
            continue
        key, sep, value = line.partition(": ")
        if sep and value.strip():
            found[_scalar(key)] = _scalar(value)
    return found


def set_values(path: Path, values: dict[str, str]) -> list[str]:
    """Top-level lines of *path* set to *values* ("key: value"), every other line kept; a key the file does not name
    goes before its end ("..."), and a file that is not there is made. The keys changed; the file is written only
    when one did. OSError is the caller's; the caller makes sure Vita3K does not run."""
    lines = _lines(path) or ["---", "..."]
    changed = []
    for key, value in values.items():
        line = f"{key}: {value}"
        at = next((n for n, text in enumerate(lines) if text.partition(":")[0] == key), None)
        if at is not None:
            if _scalar(lines[at].partition(":")[2]) != value:
                lines[at] = line
                changed.append(key)
            continue
        end = next((n for n, text in enumerate(lines) if text.strip() == "..."), len(lines))
        lines.insert(end, line)
        changed.append(key)
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return changed


def prepare(home: Path) -> list[str]:
    """config.yml's lines the app owns (OWNED) set; what was changed, for the log. The caller makes sure Vita3K does
    not run."""
    changed = set(set_values(config_path(home), {key: value for key, value, _what in OWNED}))
    return [what for key, _value, what in OWNED if key in changed]


# --- The firmware ------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Firmware:
    system: bool                        # the system software (vs0): Vita3K needs it for most games
    fonts: bool                         # the font package (sa0): needed for the text of many games
    preinstalled: bool                  # the preinstalled apps (pd0): optional

    @property
    def ready(self) -> bool:
        """What Vita3K checks before it starts a game."""
        return self.system and self.fonts


def _filled(path: Path) -> bool:
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return False


def firmware(fs: Path) -> Firmware:
    return Firmware(_filled(fs / "vs0"), _filled(fs / "sa0"), _filled(fs / "pd0"))


def _written(path: Path, since: float) -> bool:
    """Whether a file below *path* was written at *since* or later."""
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                if os.stat(os.path.join(root, name)).st_mtime >= since:
                    return True
            except OSError:
                continue
    return False


def firmware_written(fs: Path, since: float) -> Firmware:
    """The parts of the firmware Vita3K wrote at *since* (a time.time()) or later: what one --firmware installed."""
    return Firmware(_written(fs / "vs0", since) or _written(fs / "os0", since),
                    _written(fs / "sa0", since), _written(fs / "pd0", since))


def firmware_parts(parts: Firmware) -> str:
    """The parts as a sentence: "the system software and the font package"; "" for none."""
    named = [part for part, there in (("the system software", parts.system), ("the font package", parts.fonts),
                                      ("the preinstalled apps", parts.preinstalled)) if there]
    return named[0] if len(named) == 1 else ", ".join(named[:-1]) + " and " + named[-1] if named else ""


# --- The games, updates and extra content ------------------------------------------------------------------------

def content_written(fs: Path, since: float) -> list[tuple[str, str]]:
    """What Vita3K installed at *since* or later: (what it is, the title ID), a game in ux0\\app, an update in
    ux0\\patch, extra content in ux0\\addcont, each by its title's folder."""
    found = []
    for kind, what in CONTENT:
        try:
            folders = sorted(p for p in (fs / "ux0" / kind).iterdir() if p.is_dir())
        except OSError:
            continue
        found += [(what, path.name) for path in folders if _written(path, since)]
    return found


def is_dump(path: Path) -> bool:
    """Whether *path* is a dumped game's own folder, with sce_sys\\param.sfo. Vita3K installs whatever has one in a
    folder it is given and in every folder below (get_contents_path), so the app gives it only such a folder."""
    try:
        return (path / "sce_sys" / "param.sfo").is_file()
    except OSError:
        return False


def check_zrif(text: str) -> str:
    """"" when *text* can be a zRIF, a package's license key (NoNpDrm's: zlib-compressed and in base64, starting with
    KO5i), else why not."""
    if not text:
        return "The license key is empty: paste the package's zRIF."
    if not text.startswith("KO5i") or not ZRIF.fullmatch(text):
        return "That is no zRIF: a package's license key starts with KO5i and holds letters, digits, + / = only."
    return ""
