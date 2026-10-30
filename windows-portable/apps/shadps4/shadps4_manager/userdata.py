# SPDX-License-Identifier: GPL-3.0-or-later
"""shadPS4's own folder, user\\ beside shadPS4.exe (emulator.py: its portable mode), as the BC250 suite's shadPS4
Manager reads and writes it (its userdata.py): the system module folder from its config.json and which system modules
are there, the time spent in each game (its play_time.txt), the quit hotkeys (input_config\\global.ini), and the users
and shadNet settings (its users.json). shadPS4 writes these files; the app writes the shadNet settings, which shadPS4
has no place for, the settings of the Settings pane (shadps4_settings.py) and the quit hotkeys. Both JSON files are
written as shadPS4 writes them (indented by two, no newline at the end), and every other setting in them stays as it
is; never while shadPS4 runs, which writes its own copy back.

On the handheld shadPS4's own window never shows, so shadPS4 may not have run when the shadNet account is set up:
users.json is then made with shadPS4 0.20.0's four default users (user_manager.cpp, CreateDefaultUsers), which shadPS4
reads as its own. The game folders are the app's (library.py), as in the suite's other managers: shadPS4 starts a game
from its path and needs no list of them.

System modules are libraries of the PS4's firmware (.sprx), which the app cannot ship: they come from the user's own
console. shadPS4 0.20.0 loads these from the folder when a game asks for them (sysmodule_internal.cpp); for some it
has its own version and does without, for the others a game that needs one does not run without it."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

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
MODULE_SUFFIXES = (".sprx",)            # the system modules, as the Modules folder holds them


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


def sync_modules(source: Path, target: Path) -> list[str]:
    """The system modules (.sprx) put in *source*, the app's Modules folder (owner, 30-10-2026: drop them there, the
    app takes care of them), copied into shadPS4's module folder *target* when they are new or changed (another size
    or time; copy2 keeps the time), so an unchanged folder copies nothing. Returns the names copied, sorted; [] when
    *source* is missing or empty. OSError when a file cannot be read or written."""
    try:
        found = sorted((entry for entry in source.iterdir()
                        if entry.is_file() and entry.suffix.lower() in MODULE_SUFFIXES),
                       key=lambda entry: entry.name.casefold())
    except OSError:
        return []
    copied = []
    for module in found:
        destination = target / module.name
        try:
            there, here = destination.stat(), module.stat()
            if there.st_size == here.st_size and int(there.st_mtime) == int(here.st_mtime):
                continue
        except OSError:
            pass
        target.mkdir(parents=True, exist_ok=True)
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
# Back + Start (View + Menu on the handheld's controller, Share + Options on a DualShock 4 or DualSense) is a pair
# every controller has; shadPS4 gives a combination priority over its single buttons, so View alone stays the
# touchpad. Its own default goes in as well: shadPS4 adds it only to a global.ini with no hotkey_quit.
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
    temporary.write_bytes((text + "".join(f"{line}\n" for line in missing)).encode("utf-8"))   # its lines kept
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


def default_users() -> dict:
    """users.json as shadPS4 0.20.0 makes it before its first start (CreateDefaultUsers, every field of its User with
    its default), without the commit_hash it adds: shadPS4 writes the file again with its own when it starts."""
    return {"Users": {"user": [
        {"user_id": 999 + n, "user_color": n, "user_name": "shadPS4" if n == 1 else f"shadPS4-{n}",
         "player_index": n, "shadnet_npid": "", "shadnet_password": "", "shadnet_token": "", "shadnet_email": "",
         "shadnet_enabled": False, "np_country": "us", "np_language": "en", "np_age": 30,
         "np_date_of_birth": "1994-01-01"} for n in range(1, 5)]}}


def _users_list(data: dict) -> list:
    users = data.get("Users")
    listed = users.get("user") if isinstance(users, dict) else None
    return listed if isinstance(listed, list) else []


def _users(data: dict) -> list[User]:
    return [User(int(u.get("user_id", 0)), str(u.get("user_name", "")), str(u.get("shadnet_npid", "")),
                 str(u.get("shadnet_password", "")), str(u.get("shadnet_email", "")),
                 bool(u.get("shadnet_enabled", False)))
            for u in _users_list(data) if isinstance(u, dict) and isinstance(u.get("user_id"), int)]


def read_users(home: Path) -> list[User]:
    """shadPS4's users in its order: its four default users when it never ran (no users.json, which save_shadnet
    then makes), [] when the file cannot be read."""
    try:
        data = json.loads((home / "users.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = default_users()
    except (OSError, ValueError):
        return []
    return _users(data) if isinstance(data, dict) else []


def shadnet_on(config: dict) -> bool:
    """shadPS4's own switch for shadNet (its settings window's "Enable ShadNet"), for all users."""
    return bool(_network(config, "shad_net_enabled"))


def shadnet_server(config: dict) -> str:
    server = _network(config, "shadnet_server")
    return server if isinstance(server, str) and server.strip() else DEFAULT_SERVER


def signing_in(config: dict, users: list[User]) -> list[User]:
    """The users shadPS4 signs in with when a game starts."""
    return [u for u in users if u.shadnet and u.npid] if shadnet_on(config) else []


def _write_json(path: Path, data: dict) -> None:
    """As shadPS4 writes it, through a temporary file, so a cut-off write never leaves half a file."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
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


def save_shadnet(home: Path, user_id: int, npid: str, password: str, email: str, on: bool, server: str) -> None:
    """The user's shadNet account in users.json, and in config.json the server and shadPS4's switch: on when the
    user's shadNet is on, off when no user's is. Before shadPS4's first start both files are made (users.json with
    its default users, config.json with only these keys, in its Network section; shadPS4 adds the rest). shadPS4 must
    not run now (it would write its own copy back). UserDataError when a file cannot be read or written."""
    config = _read_for_writing(home / "config.json")
    users = _read_for_writing(home / "users.json") or default_users()
    listed = [u for u in _users_list(users) if isinstance(u, dict)]
    user = next((u for u in listed if u.get("user_id") == user_id), None)
    if user is None:
        raise UserDataError(f"shadPS4 has no user {user_id}.")
    user.update(shadnet_npid=npid, shadnet_password=password, shadnet_email=email, shadnet_enabled=on)
    # 0.20.0 has a Network section and no longer reads these from General once it is there.
    if isinstance(config.get("Network"), dict) or not isinstance(config.get("General"), dict):
        section = config.setdefault("Network", {})
    else:
        section = config["General"]
    if not isinstance(section, dict):
        raise UserDataError("shadPS4's settings are not what shadPS4 writes.")
    section["shad_net_enabled"] = any(bool(u.get("shadnet_enabled")) for u in listed)
    section["shadnet_server"] = server
    try:
        home.mkdir(parents=True, exist_ok=True)
        _write_json(home / "users.json", users)
        _write_json(home / "config.json", config)
    except OSError as error:
        raise UserDataError(f"shadPS4's settings could not be written: {error}") from error
