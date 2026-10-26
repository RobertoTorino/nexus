# SPDX-License-Identifier: GPL-3.0-or-later
"""Bazzite's own HDMI-CEC: which mode is on, and the settings of Valve's CEC daemon (cecd) for this user.

Bazzite ships two CEC setups and `ujust cec-mode` picks one:
 * native: Valve's cecd (linux-cec), a user service; it wakes and suspends the TV with the board and turns the
   remote's keys into key presses. The one for a GPU with its own CEC adapter, as the BC-250 has.
 * dgpu: the older cec-control script with three system services (boot, sleep, power-off), for USB adapters.
With neither enabled the mode is "disabled", as `ujust cec-mode status` reports it.

cecd reads its TOML files in order, later ones winning: /usr/share/cecd, /etc/cecd and ~/.config/cecd, each a
config.toml and then config.d/*.toml. The app writes only its own fragment, 99-bc250-hdmi-cec.toml: after Bazzite's
98-bazzite-cec-mode.toml, before SteamOS Manager's 99-steamos-manager.toml, so Steam's own CEC switches win where
SteamOS Manager runs."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .runner import Result

CECD_UNIT = "cecd.service"
DGPU_UNITS = ("cec-onboot.service", "cec-onsleep.service", "cec-onpoweroff.service")
FRAGMENT = "99-bc250-hdmi-cec.toml"
NATIVE_COMMAND = "ujust cec-mode native"

# The cecd settings the app shows, with cecd's own defaults.
DEFAULTS = {"wake_tv": False, "suspend_tv": False, "allow_standby": False, "uinput": True}

Runner = Callable[[list[str]], Result]


@dataclass(frozen=True)
class Mode:
    name: str                       # "native" | "dgpu" | "disabled", as ujust cec-mode status says
    cecd_installed: bool
    cecd_running: bool

    @property
    def label(self) -> str:
        return {"native": "Native (Valve's cecd)", "dgpu": "dGPU (cec-control)"}.get(self.name, "Off")


def read_mode(runner: Runner, usr_root: Path = Path("/usr")) -> Mode:
    def enabled(*args: str) -> bool:
        result = runner(["systemctl", *args])
        return result.ok and result.out.strip().startswith("enabled")

    if enabled("--user", "is-enabled", CECD_UNIT):
        name = "native"
    elif any(enabled("is-enabled", unit) for unit in DGPU_UNITS):
        name = "dgpu"
    else:
        name = "disabled"
    running = runner(["systemctl", "--user", "is-active", CECD_UNIT])
    return Mode(name, (usr_root / "bin/cecd").is_file(), running.ok and running.out.strip() == "active")


def config_files(config_home: Path, etc_root: Path = Path("/etc"), usr_root: Path = Path("/usr")) -> list[Path]:
    """cecd's configuration files in the order it loads them."""
    files = []
    for folder in (usr_root / "share/cecd", etc_root / "cecd", config_home / "cecd"):
        files.append(folder / "config.toml")
        files += sorted((folder / "config.d").glob("*.toml"))
    return [f for f in files if f.is_file()]


def read_settings(config_home: Path, etc_root: Path = Path("/etc"), usr_root: Path = Path("/usr")) -> dict[str, bool]:
    """The settings cecd ends up with, after all its files."""
    settings = dict(DEFAULTS)
    for path in config_files(config_home, etc_root, usr_root):
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        for key in DEFAULTS:
            if isinstance(data.get(key), bool):
                settings[key] = data[key]
    return settings


def fragment_path(config_home: Path) -> Path:
    return config_home / "cecd" / "config.d" / FRAGMENT


OSD_NAME_BYTES = 14                     # cecd's limit for osd_name


def read_fragment(config_home: Path) -> dict:
    """The app's own file as it is: the switches, osd_name and the mappings table it wrote."""
    try:
        return tomllib.loads(fragment_path(config_home).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _toml(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def update_fragment(config_home: Path, **changes) -> Path:
    """Writes the app's file with *changes* on top of what it holds; a None value removes that setting. The
    mappings table (a dict) goes last, as a [mappings] section."""
    data = read_fragment(config_home)
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    mappings = data.pop("mappings", None)
    lines = ["# Written by BC250 HDMI CEC. Removed with: install.sh --uninstall --purge",
             *(f"{key} = {_toml(value)}" for key, value in data.items() if not isinstance(value, dict))]
    if mappings:
        lines += ["", "# The TV remote's buttons: UI command -> Linux key code (cecd's defaults with the app's "
                  "changes)", "[mappings]", *(f'"{button}" = {number}' for button, number in mappings.items())]
    path = fragment_path(config_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_settings(config_home: Path, settings: dict[str, bool]) -> Path:
    return update_fragment(config_home, **{key: settings[key] for key in DEFAULTS})


def osd_name_problem(name: str) -> str:
    """Why cecd would not take *name* as its OSD name; "" when it would."""
    if not name.strip():
        return "The name is empty."
    if not name.isascii() or not name.isprintable():
        return "Use plain letters, digits and punctuation: many TVs show nothing else."
    if len(name.encode()) > OSD_NAME_BYTES:
        return f"At most {OSD_NAME_BYTES} characters."
    return ""


def reload_cecd(runner: Runner) -> Result:
    """cecd reloads its configuration on SIGHUP, as `ujust cec-sleep` does it."""
    return runner(["systemctl", "--user", "kill", "-s", "HUP", CECD_UNIT])


def restart_cecd(runner: Runner) -> Result:
    """The name and the remote's mappings take effect only when cecd opens the adapter again ("Cannot change
    mappings after opening"), so those need a restart; try-restart leaves a stopped cecd stopped."""
    return runner(["systemctl", "--user", "try-restart", CECD_UNIT])
