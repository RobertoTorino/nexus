# SPDX-License-Identifier: GPL-3.0-or-later
"""Vita3K's own folders as build 4186 lays them out on Linux (app::init_paths): its settings in ~/.config/Vita3K
(config.yml), and the PS Vita's storage, its "Vita FS", in ~/.local/share/Vita3K/Vita3K, or where config.yml's
pref-path says (Settings > Emulator > storage folder). The app reads config.yml, and writes the two lines it owns
(OWNED; owner, 03-11-2026, from the Windows Portable Suite's Vita3K Manager): Vita3K's welcome window off
(show-welcome) and its own update check off (check-for-updates-mode 0, UPDATE_STARTUP_OFF), which could replace the
pinned build. Never while Vita3K runs: it writes its settings back when it closes.

config.yml is a YAML map as Vita3K writes it (yaml-cpp, between "---" and "..."): one "key: value" a line at the top
level, lists below their key indented. The app reads only the top level, so it needs no YAML library.

The PS Vita's firmware is not ours to give: the app cannot ship it, and Vita3K needs it to start most games. It
comes in three files, each named PSP2UPDAT.PUP and each downloaded from Sony: the system software (it fills vs0,
os0), the font package (sa0) and the preinstalled apps (pd0). Vita3K installs any of them (--firmware) and counts a
part as installed when its folder holds anything (app::get_firmware_state); its own window warns before a game when
the firmware or the fonts are missing. The preinstalled apps are optional.

Vita3K says nothing of a file it could not use: it quits as after an install (on a file that is no PUP it only
warns that the PUP had no version.txt). What it installed shows in the files it wrote, all of them new."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from bc250_core.platform import config_home, data_home

APP_NAME = "Vita3K"
FIRMWARE_PAGE = "https://www.playstation.com/en-us/support/hardware/psvita/system-software/"
# Sony's files that Vita3K's own welcome window links to (through short links, resolved here).
FONTS_URL = ("http://dus01.psp2.update.playstation.net/update/psp2/image/2019_0924/"
             "sd_8b5f60b56c3da8365b973dba570c53a5/PSP2UPDAT.PUP?dest=us")
PREINSTALL_URL = ("http://dus01.psp2.update.playstation.net/update/psp2/image/2022_0209/"
                  "pre_efd1ef6c1cc2fe92e72e9e783e421237/PSP2UPDAT.PUP?dest=us")
# The lines of config.yml the app owns: key, value, and what it did in the app's words.
OWNED = (("show-welcome", "false", "its welcome window off"),
         ("check-for-updates-mode", "0", "its update check off"))


def config_dir() -> Path:
    return config_home() / APP_NAME


def default_storage() -> Path:
    return data_home() / APP_NAME / APP_NAME


def config_path(config: Path) -> Path:
    """config.yml in Vita3K's settings folder *config*."""
    return config / "config.yml"


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


def prepare(config: Path) -> list[str]:
    """config.yml's lines the app owns (OWNED) set; what was changed, for the output. The caller makes sure Vita3K
    does not run."""
    changed = set(set_values(config_path(config), {key: value for key, value, _what in OWNED}))
    return [what for key, _value, what in OWNED if key in changed]


def storage(config: Path) -> Path:
    """The Vita FS: config.yml's pref-path, else Vita3K's default."""
    pref = read_map(config / "config.yml").get("pref-path", "")
    return Path(pref) if pref else default_storage()


@dataclass(frozen=True)
class Firmware:
    system: bool                        # the system software (vs0): Vita3K needs it for most games
    fonts: bool                         # the font package (sa0): needed for the text of many games
    preinstalled: bool                  # the preinstalled apps (pd0): optional

    @property
    def ready(self) -> bool:
        """What Vita3K checks before it starts a game."""
        return self.system and self.fonts


def _filled(folder: Path) -> bool:
    try:
        return folder.is_dir() and any(folder.iterdir())
    except OSError:
        return False


def firmware(vita_fs: Path) -> Firmware:
    return Firmware(_filled(vita_fs / "vs0"), _filled(vita_fs / "sa0"), _filled(vita_fs / "pd0"))


def _written(folder: Path, since: float) -> bool:
    """Whether a file below *folder* was written at *since* or later."""
    for root, _dirs, files in os.walk(folder):
        for name in files:
            try:
                if os.stat(os.path.join(root, name)).st_mtime >= since:
                    return True
            except OSError:
                continue
    return False


def firmware_written(vita_fs: Path, since: float) -> Firmware:
    """The parts of the firmware Vita3K wrote at *since* (a time.time()) or later: what one --firmware installed."""
    return Firmware(_written(vita_fs / "vs0", since) or _written(vita_fs / "os0", since),
                    _written(vita_fs / "sa0", since), _written(vita_fs / "pd0", since))
