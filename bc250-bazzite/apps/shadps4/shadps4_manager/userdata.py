# SPDX-License-Identifier: GPL-3.0-or-later
"""shadPS4's own folder, ~/.local/share/shadPS4 (its saves, settings and system modules): the game folders and the
system module folder from its config.json, which system modules are there, the time spent in each game (its
play_time.txt), and the users and shadNet settings (its users.json). shadPS4 writes these files; the app writes the
shadNet settings, which shadPS4 has no place for, the settings of the Settings tab (shadps4_settings.py), a game
folder taken out (one is added through shadPS4's own --add-game-folder), and the quit hotkeys in
input_config/global.ini. Both JSON files are written as shadPS4 writes them (indented by two, no newline at the
end), and every other setting in them stays as it is; never while shadPS4 runs, which writes its own copy back.

System modules are libraries of the PS4's firmware (.sprx), which the app cannot ship: they come from the user's own
console. shadPS4 0.20.0 loads these from the folder when a game asks for them (sysmodule_internal.cpp); for some it
has its own version and does without, for the others a game that needs one does not run without it."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from bc250_core.platform import data_home

from .shadnet import DEFAULT_SERVER

# shadPS4 0.20.0 has no replacement of its own for these.
NEEDED = (
    "libSceUlt.sprx", "libSceAvPlayerStreaming.sprx", "libSceJpegDec.sprx", "libSceJson.sprx", "libSceJson2.sprx",
    "libSceCesCs.sprx", "libSceAt9Enc.sprx", "libSceAudiodec.sprx", "libSceAudiodecCpu.sprx",
    "libSceAudiodecCpuDdp.sprx", "libSceAudiodecCpuM4aac.sprx", "libSceAudiodecCpuDtsHdLbr.sprx",
    "libSceAudiodecCpuHevag.sprx", "libSceFreeTypeOt.sprx", "libSceFreeTypeOl.sprx", "libSceFreeTypeOptOl.sprx",
    "libSceBeisobmf.sprx", "libSceBemp2sys.sprx", "libSceWkFontConfig.sprx", "libScePsmKitSystem.sprx",
    "libSceDepth.sprx", "libScePadTracker.sprx", "libSceMoveTracker.sprx", "libSceXml.sprx",
)
# Used when they are there; shadPS4 has its own version of these.
OPTIONAL = (
    "libSceNgs2.sprx", "libSceAvPlayer.sprx", "libSceRtc.sprx", "libSceJpegEnc.sprx", "libScePngDec.sprx",
    "libScePngEnc.sprx", "libSceFont.sprx", "libSceFontFt.sprx", "libSceRudp.sprx", "libSceSystemGesture.sprx",
)


def shadps4_home() -> Path:
    return data_home() / "shadPS4"


def read_config(home: Path) -> dict:
    """shadPS4's config.json; {} when it is not there (shadPS4 never ran) or cannot be read."""
    try:
        config = json.loads((home / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return config if isinstance(config, dict) else {}


def _general(config: dict) -> dict:
    general = config.get("General")
    return general if isinstance(general, dict) else {}


def _network(config: dict, key: str):
    """A shadNet setting where shadPS4 reads it: 0.19.0 keeps them in General, 0.20.0 in Network, and takes one from
    General only while Network does not have it (a config from before 0.20.0)."""
    network = config.get("Network")
    if isinstance(network, dict) and key in network:
        return network[key]
    return _general(config).get(key)


def game_folders(config: dict) -> list[Path]:
    """The game folders shadPS4 knows and has switched on, in its order."""
    folders = _general(config).get("install_dirs")
    if not isinstance(folders, list):
        return []
    return [Path(item["path"]) for item in folders
            if isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"]
            and item.get("enabled", True)]


def modules_folder(home: Path, config: dict) -> Path:
    """Where shadPS4 looks for system modules: its setting, else sys_modules in its folder."""
    chosen = _general(config).get("sys_modules_dir")
    return Path(chosen) if isinstance(chosen, str) and chosen else home / "sys_modules"


@dataclass(frozen=True)
class Modules:
    folder: Path
    needed: tuple[str, ...]             # of NEEDED, the ones there
    optional: tuple[str, ...]           # of OPTIONAL, the ones there

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(name for name in NEEDED if name not in self.needed)

    @property
    def complete(self) -> bool:
        return not self.missing


def check_modules(folder: Path) -> Modules:
    try:
        present = {entry.name for entry in folder.iterdir() if entry.is_file()}
    except OSError:
        present = set()
    return Modules(folder, tuple(n for n in NEEDED if n in present), tuple(n for n in OPTIONAL if n in present))


def install_modules(source: Path, target: Path) -> list[str]:
    """The system modules (.sprx) in the folder *source* (a copy of the PS4's firmware libraries) copied into
    shadPS4's module folder *target*, made when it is not there; a file there of the same name is replaced. Returns
    the names copied, sorted. OSError when a file cannot be read or written."""
    found = sorted((entry for entry in source.iterdir() if entry.is_file() and entry.suffix.lower() == ".sprx"),
                   key=lambda entry: entry.name.casefold())
    if not found:
        return []
    target.mkdir(parents=True, exist_ok=True)
    copied = []
    for module in found:
        destination = target / module.name
        if not (destination.exists() and destination.samefile(module)):
            shutil.copy2(module, destination)
        copied.append(module.name)
    return copied


# --- Play time -------------------------------------------------------------------------------------------------

PLAY_TIME = "play_time.txt"


def play_times(home: Path) -> dict[str, tuple[int, float]]:
    """The time spent in each game, as shadPS4 0.20.0 counts it (Emulator::UpdatePlayTime): play_time.txt in its
    folder, a line per game, "<Id> <hours>:<mm>:<ss> <last played, Unix time>" (an older line without the last
    time is read too). Id to (seconds, last played or 0); {} without the file."""
    try:
        lines = (home / PLAY_TIME).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    times = {}
    for line in lines:
        words = line.split()
        if len(words) < 2:
            continue
        try:
            hours, minutes, seconds = (int(part) for part in words[1].split(":"))
            last = float(words[2]) if len(words) > 2 else 0.0
        except ValueError:
            continue
        times[words[0]] = (hours * 3600 + minutes * 60 + seconds, last)
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


# --- Quit hotkeys ----------------------------------------------------------------------------------------------

# shadPS4's quit window (Cross or Enter quits, Circle or Escape cancels) opens only on Ctrl+Shift+End by default: the
# End key alone, not the keypad's End (a keyboard without an End key of its own), and from no controller button.
# Back + Start (Share + Options on a DualShock 4 or DualSense, View + Menu on an Xbox controller) is a pair every
# controller has; shadPS4 gives a combination priority over its single buttons, so Share alone stays the touchpad.
# shadPS4 reads controllers without the window's focus too, so a game Steam started takes them while the keyboard
# stays with Big Picture. Its own default goes in as well: shadPS4 adds it only to a global.ini with no hotkey_quit.
QUIT_BINDINGS = ("hotkey_quit = lctrl, lshift, end", "hotkey_quit = lctrl, lshift, kp1",
                 "hotkey_quit = back, options")
GLOBAL_INI_HEADER = ("# Anything put here will be loaded for all games,\n"
                     "# alongside the game's config or default.ini depending on your preference.\n")


def _binding(line: str) -> str:
    """A line as shadPS4 reads it: without spaces."""
    return "".join(line.split())


def add_quit_bindings(home: Path) -> list[str]:
    """Adds the lines of QUIT_BINDINGS that input_config/global.ini lacks, each line as it is, after shadPS4's own
    header in a file that is not there yet (shadPS4 then adds the rest of its defaults). Returns the lines added.
    shadPS4 reads the file when a game starts (or on F8), so it may run meanwhile. OSError when it cannot be written."""
    path = home / "input_config" / "global.ini"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = None
    present = {_binding(line) for line in (text or "").splitlines()}
    missing = [line for line in QUIT_BINDINGS if _binding(line) not in present]
    if not missing:
        return []
    if text is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = GLOBAL_INI_HEADER
    elif text and not text.endswith("\n"):
        text += "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text + "".join(f"{line}\n" for line in missing), encoding="utf-8")
    temporary.replace(path)
    return missing


# --- Users and shadNet -----------------------------------------------------------------------------------------

class UserDataError(Exception):
    pass


@dataclass(frozen=True)
class User:
    """One of shadPS4's users (users.json; 0.20.0 makes four, the first is player 1) with its shadNet account."""
    user_id: int
    name: str
    npid: str = ""
    password: str = ""
    email: str = ""
    shadnet: bool = False                   # shadNet switched on for this user


def _users_list(data: dict) -> list:
    users = data.get("Users")
    listed = users.get("user") if isinstance(users, dict) else None
    return listed if isinstance(listed, list) else []


def read_users(home: Path) -> list[User]:
    """shadPS4's users in its order; [] when it never ran (no users.json) or the file cannot be read."""
    try:
        data = json.loads((home / "users.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    return [User(int(u.get("user_id", 0)), str(u.get("user_name", "")), str(u.get("shadnet_npid", "")),
                 str(u.get("shadnet_password", "")), str(u.get("shadnet_email", "")),
                 bool(u.get("shadnet_enabled", False)))
            for u in _users_list(data) if isinstance(u, dict) and isinstance(u.get("user_id"), int)]


def shadnet_on(config: dict) -> bool:
    """shadPS4's own switch for shadNet (its settings window's "Enable ShadNet"), for all users."""
    return bool(_network(config, "shad_net_enabled"))


def shadnet_server(config: dict) -> str:
    server = _network(config, "shadnet_server")
    return server if isinstance(server, str) and server.strip() else DEFAULT_SERVER


def _write_json(path: Path, data: dict) -> None:
    """As shadPS4 writes it, through a temporary file, so a cut-off write never leaves half a file."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _read_for_writing(path: Path) -> dict:
    """A JSON file of shadPS4's to change: {} when it is not there; UserDataError when it cannot be read or is not
    what shadPS4 writes (it is never written over then)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise UserDataError(f"shadPS4's settings could not be read: {error}") from error
    if not isinstance(data, dict):
        raise UserDataError("shadPS4's settings are not what shadPS4 writes.")
    return data


def write_config(home: Path, section: str, name: str, value) -> None:
    """One key of config.json set, every other key kept; the file made when there is none (shadPS4 adds its
    defaults to it when it starts). UserDataError when it cannot be read or written; the caller makes sure shadPS4
    does not run."""
    path = home / "config.json"
    config = _read_for_writing(path)
    group = config.setdefault(section, {})
    if not isinstance(group, dict):
        raise UserDataError("shadPS4's settings are not what shadPS4 writes.")
    group[name] = value
    try:
        home.mkdir(parents=True, exist_ok=True)
        _write_json(path, config)
    except OSError as error:
        raise UserDataError(f"shadPS4's settings could not be written: {error}") from error


def remove_game_folder(home: Path, folder: Path) -> None:
    """*folder* taken out of shadPS4's game folders (General.install_dirs in config.json), as shadPS4's own Remove
    Folder does; its games stay where they are. UserDataError as write_config."""
    path = home / "config.json"
    config = _read_for_writing(path)
    general = config.get("General")
    folders = general.get("install_dirs") if isinstance(general, dict) else None
    if not isinstance(folders, list):
        return
    general["install_dirs"] = [item for item in folders
                               if not (isinstance(item, dict) and item.get("path") == str(folder))]
    try:
        _write_json(path, config)
    except OSError as error:
        raise UserDataError(f"shadPS4's settings could not be written: {error}") from error


def save_shadnet(home: Path, user_id: int, npid: str, password: str, email: str, on: bool, server: str) -> None:
    """The user's shadNet account in users.json, and in config.json the server and shadPS4's switch: on when the
    user's shadNet is on, off when no user's is. shadPS4 must have run once (it makes both files) and must not run
    now (it would write its own copy back). UserDataError when a file is missing or cannot be read or written."""
    try:
        config = json.loads((home / "config.json").read_text(encoding="utf-8"))
        users = json.loads((home / "users.json").read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise UserDataError("shadPS4 has not run yet: start it once (shadPS4 settings), then try again.") from error
    except (OSError, ValueError) as error:
        raise UserDataError(f"shadPS4's settings could not be read: {error}") from error
    if not isinstance(config, dict) or not isinstance(users, dict):
        raise UserDataError("shadPS4's settings are not what shadPS4 writes.")
    listed = [u for u in _users_list(users) if isinstance(u, dict)]
    user = next((u for u in listed if u.get("user_id") == user_id), None)
    if user is None:
        raise UserDataError(f"shadPS4 has no user {user_id}.")
    user.update(shadnet_npid=npid, shadnet_password=password, shadnet_email=email, shadnet_enabled=on)
    # 0.20.0 has a Network section and no longer reads these from General once it is there.
    section = config["Network"] if isinstance(config.get("Network"), dict) else config.setdefault("General", {})
    if not isinstance(section, dict):
        raise UserDataError("shadPS4's settings are not what shadPS4 writes.")
    section["shad_net_enabled"] = any(bool(u.get("shadnet_enabled")) for u in listed)
    section["shadnet_server"] = server
    try:
        _write_json(home / "users.json", users)
        _write_json(home / "config.json", config)
    except OSError as error:
        raise UserDataError(f"shadPS4's settings could not be written: {error}") from error


def shadps4_running(proc: Path = Path("/proc")) -> bool:
    """Whether shadPS4 runs (its AppImage, or the program inside it), which writes its own settings back."""
    for entry in proc.glob("[0-9]*"):
        try:
            name = (entry / "comm").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if name == "shadps4" or name.startswith("Shadps4-sdl"):
            return True
    return False
