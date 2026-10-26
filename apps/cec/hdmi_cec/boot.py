# SPDX-License-Identifier: GPL-3.0-or-later
"""The boot part: before anyone logs in, the board's name on the TV and, when chosen, the TV turned on and switched to
the board. Everything else in the app runs in the desktop session; at boot nothing of it runs yet, so the TV shows
whatever name the adapter got ("Playback" from Bazzite's cec-control) and nothing turns it on.

This file runs as root and needs only the standard library. The app runs it through pkexec with the system python3 in
isolated mode (-I) to install or remove the boot part, and the installed copy runs at boot:
 * /etc/udev/rules.d/99-bc250-hdmi-cec-boot.rules starts bc250-hdmi-cec-boot.service when a CEC adapter appears. On
   the BC-250 that is when the DP-to-HDMI converter reports CEC, which may be only once the TV is turned on (the
   owner's board, 12-10-2026: 2.5 minutes after boot, when the TV was turned on).
 * The service runs once per boot (it stays active). It waits until the adapter sees a display, configures it as a
   playback device with the board's name and, with wake, sends Image View On and Active Source. It is ordered before
   the display manager and tells systemd it is ready then, or after READY_S without a display, so the TV is on before
   the login screen sets its mode, and the login screen waits at most READY_S.
 * For GUARD_S it then keeps the name: Bazzite's cec-control, which a udev rule of Bazzite runs when the Bluetooth
   adapter appears (also with its CEC services switched off), configures the adapter as "Playback" without a name.
   It steps aside when Valve's CEC daemon runs: that one names the adapter from its own setting.
 * /etc/bc250-hdmi-cec/boot.json holds the name and whether to wake the TV; boot.py next to it is the copy that runs.

KDE's login screen has its own display settings, not the user's: at 1080p120 with more than 8 bits per color the
converter may leave a TV that comes on later black there (display.py). greeter-display copies the user's
kwinoutputconfig.json to the login screen's user, as KDE's Apply Plasma Settings (System Settings, Login Screen) does.

The cec-ctl messages are the same as in cec.py, which this file cannot import (it runs on its own); the tests check
that they match."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SYSTEM_PYTHON = "/usr/bin/python3"
FOLDER = "bc250-hdmi-cec"                       # in /etc: boot.py and boot.json
UNIT = "bc250-hdmi-cec-boot.service"
RULE = "99-bc250-hdmi-cec-boot.rules"
MANUAL_URL = "https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/cec/"
OSD_NAME_BYTES = 14                             # as bazzite.OSD_NAME_BYTES
NO_ADDRESS = "f.f.f.f"
READY_S = 8                                     # the longest the login screen waits for a display
GUARD_S = 60                                    # how long the name is kept after boot
STEP_S = 2
# The display manager's unit and the user its login screen runs as: KDE's two keep kwinoutputconfig.json there.
GREETERS = {"plasmalogin.service": "plasmalogin", "sddm.service": "sddm"}
KWIN_OUTPUTS = "kwinoutputconfig.json"

Runner = Callable[[list[str]], "Result"]


@dataclass(frozen=True)
class Result:
    code: int
    out: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def run(argv: list[str]) -> Result:
    try:
        done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Result(127, str(exc))
    return Result(done.returncode, done.stdout)


def log(text: str) -> None:
    print(text, flush=True)


# --- The files ---------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Paths:
    etc: Path = Path("/etc")

    @property
    def folder(self) -> Path:
        return self.etc / FOLDER

    @property
    def script(self) -> Path:
        return self.folder / "boot.py"

    @property
    def config(self) -> Path:
        return self.folder / "boot.json"

    @property
    def unit(self) -> Path:
        return self.etc / "systemd/system" / UNIT

    @property
    def rule(self) -> Path:
        return self.etc / "udev/rules.d" / RULE


@dataclass(frozen=True)
class Config:
    name: str
    wake: bool


def name_problem(name: str) -> str:
    """As bazzite.osd_name_problem: what cecd and most TVs take."""
    if not name.strip():
        return "The name is empty."
    if not name.isascii() or not name.isprintable():
        return "Use plain letters, digits and punctuation: many TVs show nothing else."
    if len(name.encode()) > OSD_NAME_BYTES:
        return f"At most {OSD_NAME_BYTES} characters."
    return ""


def read_config(paths: Paths) -> Config | None:
    try:
        data = json.loads(paths.config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, str) or name_problem(name):
        return None
    return Config(name, data.get("wake") is True)


def installed(paths: Paths) -> Config | None:
    """The boot part's settings when all of it is there, else None."""
    if not (paths.script.is_file() and paths.unit.is_file() and paths.rule.is_file()):
        return None
    return read_config(paths)


def outdated(paths: Paths, own: Path = Path(__file__)) -> bool:
    """Whether the installed copy differs from this file: another version of the app installed it."""
    try:
        return paths.script.read_bytes() != own.read_bytes()
    except OSError:
        return True


def unit_text() -> str:
    return "\n".join([
        "[Unit]",
        "Description=BC250 HDMI CEC: the board's name on the TV at boot, and the TV on",
        f"Documentation={MANUAL_URL}",
        "Before=display-manager.service",
        "",
        "[Service]",
        "Type=notify",
        "RemainAfterExit=yes",
        f"ExecStart={SYSTEM_PYTHON} -I {Paths().script} run",
        "TimeoutStartSec=30",
        "",
    ])


def rule_text() -> str:
    return "\n".join([
        "# Written by BC250 HDMI CEC: its boot part starts when a CEC adapter appears (once per boot).",
        f'ACTION=="add", SUBSYSTEM=="cec", KERNEL=="cec[0-9]*", TAG+="systemd", ENV{{SYSTEMD_WANTS}}+="{UNIT}"',
        "",
    ])


def write(path: Path, data: bytes) -> None:
    """Root-owned, readable by everyone, written whole."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.new")
    temp.write_bytes(data)
    temp.chmod(0o644)
    temp.replace(path)


def relabel(run: Runner, *paths: Path) -> None:
    """The SELinux labels of the folders the files are in (Fedora, Bazzite)."""
    if shutil.which("restorecon"):
        run(["restorecon", "-R", *map(str, paths)])


# --- What the app asks for, as root ------------------------------------------------------------------------------

def install(paths: Paths, name: str, wake: bool, run: Runner = run, own: Path = Path(__file__)) -> None:
    problem = name_problem(name)
    if problem:
        raise ValueError(problem)
    write(paths.script, own.read_bytes())
    write(paths.config, (json.dumps({"name": name, "wake": wake}, indent=2) + "\n").encode())
    write(paths.unit, unit_text().encode())
    write(paths.rule, rule_text().encode())
    relabel(run, paths.folder, paths.unit, paths.rule)
    run(["systemctl", "daemon-reload"])
    run(["udevadm", "control", "--reload"])


def uninstall(paths: Paths, run: Runner = run) -> None:
    run(["systemctl", "stop", UNIT])
    for path in (paths.rule, paths.unit, paths.config, paths.script):
        path.unlink(missing_ok=True)
    try:
        paths.folder.rmdir()
    except OSError:
        pass
    run(["systemctl", "daemon-reload"])
    run(["udevadm", "control", "--reload"])


def greeter_user(paths: Paths) -> str:
    """The user KDE's login screen runs as ("plasmalogin" or "sddm"); "" for another display manager (GDM keeps its
    display settings elsewhere) or none."""
    try:
        unit = (paths.etc / "systemd/system/display-manager.service").readlink().name
    except OSError:
        return ""
    return GREETERS.get(unit, "")


def greeter_display(paths: Paths, source: Path, run: Runner = run, getpwnam: Callable | None = None) -> Path:
    """Copies *source* (a user's kwinoutputconfig.json) to the login screen's user; returns where it went."""
    if getpwnam is None:
        import pwd                                  # Linux only; the app imports this file on Windows too
        getpwnam = pwd.getpwnam
    user = greeter_user(paths)
    if not user:
        raise ValueError("The login screen is not KDE's (Plasma Login or SDDM): it keeps its display settings "
                         "elsewhere.")
    data = source.read_bytes()
    if not isinstance(json.loads(data), list):
        raise ValueError(f"{source} is not KDE's display settings.")
    entry = getpwnam(user)
    config = Path(entry.pw_dir) / ".config"
    if not config.is_dir():
        config.mkdir(mode=0o755)
        os.chown(config, entry.pw_uid, entry.pw_gid)
    target = config / KWIN_OUTPUTS
    write(target, data)
    os.chown(target, entry.pw_uid, entry.pw_gid)
    relabel(run, target)
    return target


# --- Asked for by the app ----------------------------------------------------------------------------------------

def command(args: list[str], own: Path = Path(__file__)) -> list[str]:
    """This file as root, through polkit's password dialog."""
    python = SYSTEM_PYTHON if Path(SYSTEM_PYTHON).is_file() else sys.executable
    return ["pkexec", python, "-I", str(own.resolve()), *args]


def answer(code: int, out: str) -> str:
    """What went wrong ("" when nothing did): main() prints one JSON line; pkexec exits with 126 or 127 when the
    password dialog is canceled."""
    if code in (126, 127):
        return "Not authorized: the password dialog was canceled or refused."
    for line in reversed(out.strip().splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            return "" if data.get("ok") else str(data.get("error") or "It failed without saying why.")
    return f"The helper stopped with exit code {code} without an answer:\n{out.strip()}"


# --- At boot -----------------------------------------------------------------------------------------------------

_FIELD = re.compile(r"^\s*(?P<key>[A-Za-z][A-Za-z ]*?)\s*:\s*(?P<value>.*?)\s*$")


@dataclass(frozen=True)
class Adapter:
    device: str
    physical_address: str = NO_ADDRESS
    osd_name: str = ""
    configured: bool = False

    @property
    def has_display(self) -> bool:
        return self.physical_address not in ("", NO_ADDRESS)


def parse_info(device: str, text: str) -> Adapter:
    """What cec.parse_info reads, the part needed here."""
    values: dict[str, str] = {}
    configured = False
    for line in text.splitlines():
        match = _FIELD.match(line)
        if match is None:
            continue
        if match["key"] == "Logical Address":
            configured = True
        else:
            values.setdefault(match["key"], match["value"])
    return Adapter(device, values.get("Physical Address", NO_ADDRESS), values.get("OSD Name", "").strip("'"),
                   configured)


def configure(device: str, name: str) -> list[str]:
    return ["-d", device, "--playback", "--osd-name", name]


def set_osd_name(device: str, name: str) -> list[str]:
    return ["-d", device, "-s", "--to", "0", "--set-osd-name", f"name={name}"]


def image_view_on(device: str) -> list[str]:
    return ["-d", device, "-s", "--to", "0", "--image-view-on"]


def active_source(device: str, physical_address: str) -> list[str]:
    return ["-d", device, "-s", "--to", "15", "--active-source", f"phys-addr={physical_address}"]


def notify(state: str) -> None:
    """sd_notify(3) without libsystemd."""
    path = os.environ.get("NOTIFY_SOCKET", "")
    if not path:
        return
    if path.startswith("@"):
        path = "\0" + path[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(path)
            sock.sendall(state.encode())
    except OSError:
        pass


def cecd_running(proc: Path = Path("/proc")) -> bool:
    """Valve's CEC daemon, run by any user."""
    for comm in proc.glob("[0-9]*/comm"):
        try:
            if comm.read_text().strip() == "cecd":
                return True
        except OSError:
            continue
    return False


class Boot:
    def __init__(self, config: Config, run: Runner = run, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, notify: Callable[[str], None] = notify,
                 cecd: Callable[[], bool] = cecd_running, dev_root: Path = Path("/dev")):
        self.config, self.run, self.sleep, self.clock, self.notify = config, run, sleep, clock, notify
        self.cecd, self.dev_root = cecd, dev_root

    def ctl(self, args: list[str]) -> Result:
        return self.run(["cec-ctl", *args])

    def find(self) -> Adapter | None:
        """The first adapter that sees a display, as cec.pick does."""
        found = sorted((p for p in self.dev_root.glob("cec*") if p.name[3:].isdigit()), key=lambda p: int(p.name[3:]))
        for device in map(str, found):
            result = self.ctl(["-d", device])
            if result.ok:
                adapter = parse_info(device, result.out)
                if adapter.has_display:
                    return adapter
        return None

    def name(self, adapter: Adapter) -> None:
        self.ctl(configure(adapter.device, self.config.name))
        self.ctl(set_osd_name(adapter.device, self.config.name))

    def wake(self, adapter: Adapter) -> None:
        self.ctl(image_view_on(adapter.device))
        self.ctl(active_source(adapter.device, adapter.physical_address))

    def loop(self) -> int:
        start = self.clock()
        ready = done = False
        while True:
            if self.cecd():
                log("Valve's CEC daemon runs: it names the adapter itself")
                done = True
                break
            adapter = self.find()
            if adapter is not None and not done:
                self.name(adapter)
                if self.config.wake:
                    self.wake(adapter)
                log(f"{adapter.device}: named {self.config.name}"
                    + (f", turned the TV on and switched it to {adapter.physical_address}" if self.config.wake else ""))
                done = True
            elif adapter is not None and (not adapter.configured or adapter.osd_name != self.config.name):
                self.name(adapter)
                log(f"{adapter.device}: was configured again as {adapter.osd_name or 'nothing'}; "
                    f"named {self.config.name} again")
            elapsed = self.clock() - start
            if not ready and (done or elapsed >= READY_S):
                if not done:
                    log(f"no display seen yet; the login screen goes on, the name follows within {GUARD_S} s")
                self.notify("READY=1")
                ready = True
            if elapsed >= GUARD_S:
                break
            self.sleep(STEP_S)
        if not done:
            log(f"no CEC adapter saw a display within {GUARD_S} s; nothing sent")
        if not ready:
            self.notify("READY=1")
        return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="boot.py", description=__doc__.split("\n\n")[0])
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("run", help="at boot, from the service")
    add = actions.add_parser("install", help="install or update the boot part")
    add.add_argument("--name", required=True)
    add.add_argument("--wake", action="store_true", help="also turn the TV on and switch it to the board")
    actions.add_parser("uninstall", help="remove the boot part")
    greeter = actions.add_parser("greeter-display", help="copy a kwinoutputconfig.json to the login screen")
    greeter.add_argument("source", type=Path)
    args = parser.parse_args(argv)
    paths = Paths(Path(os.environ.get("BC250_SYSTEM_ROOT", "/")) / "etc")      # another root only for testing

    if args.action == "run":
        config = read_config(paths)
        if config is None:
            log(f"{paths.config} is missing or broken; nothing to do")
            notify("READY=1")
            return 0
        return Boot(config).loop()
    try:
        if args.action == "install":
            install(paths, args.name, args.wake)
        elif args.action == "uninstall":
            uninstall(paths)
        else:
            greeter_display(paths, args.source)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
