# SPDX-License-Identifier: GPL-3.0-or-later
"""The thermal guard: a system service that watches the GPU and CPU temperatures, also while no app is open, and
acts at three limits on the hotter of the two:
 * warn: a desktop notification (and a line in the journal);
 * cool: every fan channel of the board's SuperIO to full speed, and the governor's performance mode off;
 * shut down: when the temperature stays at or above the limit for hold_s seconds, a clean `systemctl poweroff`.
   The one place in the suite that powers the board off by itself (owner, 16-10-2026): it protects the hardware.
Each limit re-arms REARM_C below the warning, as the Governor's alerts do; the fans then go back to what they were
(the firmware curve, or a manual value). Performance mode stays off: turning it back on is the user's choice.

This file runs as root and needs only the standard library. The app runs it through pkexec with the system python3
in isolated mode (-I) to install or remove the guard, and the installed copy runs as the service:
 * /etc/bc250-fan-control/guard.py is that copy, guard.json next to it holds the limits;
 * /etc/systemd/system/bc250-fan-control-guard.service starts it at boot and restarts it when it stops;
 * /run/bc250-fan-control/state.json is what the guard saw last and its recent events, for the app to show.

The window imports this file for reading the sensors, so the two read the same thing."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

SYSTEM_PYTHON = "/usr/bin/python3"
FOLDER = "bc250-fan-control"                    # in /etc and /run
UNIT = "bc250-fan-control-guard.service"
MANUAL_URL = "https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/fan/"
APP_NAME = "BC-250 Fan Control"
STEP_S = 2.0
REARM_C = 5                                     # as the Governor's alerts (alerts.HYSTERESIS_C)
FAN_STOP_S = 10                                 # a fan that turned and reads 0 RPM this long has stopped
EVENTS = 30                                     # kept in the state file
STALE_S = 15                                    # a state file older than this: the guard is not running
VALID_C = (1.0, 150.0)                          # outside this a reading is a broken sensor, never a reason to act
FULL_PWM = 255
FAN_DRIVERS = ("nct6686", "nct6687", "nct6683")
# Where the SuperIO's channels are on the BC-250 (nct6687 driver numbering; mothenjoyer69's bc250-documentation:
# BIOS fan 1 is CPU_FAN1, fans 2-5 are on J4003, signals only). CPU_FAN1 as channel 2 confirmed on the owner's board
# (16-10-2026: pwm2 at 255 gave 2051 RPM, at 90 gave 861).
BC250_HEADERS = {2: "CPU_FAN1", 3: "J4003 fan 2", 4: "J4003 fan 3", 5: "J4003 fan 4", 1: "J4003 fan 5"}
GOVERNOR = ("com.cyanskillfish.Governor", "/com/cyanskillfish/Governor",
            "com.cyanskillfish.Governor.PerformanceMode")

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
    print(text, flush=True)                     # the journal, through the service's stdout


# --- The limits ----------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Limits:
    warn_c: int = 85
    cool_c: int = 90
    shutdown_c: int = 95
    hold_s: int = 10


def limits_problem(limits: Limits) -> str:
    if not 60 <= limits.warn_c < limits.cool_c < limits.shutdown_c <= 105:
        return "The limits must rise from the warning to the shutdown, between 60 and 105 °C."
    if not 3 <= limits.hold_s <= 60:
        return "The shutdown waits between 3 and 60 seconds."
    return ""


# --- The sensors ---------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Fan:
    channel: int
    header: str                                 # where it is on the board, or the driver's label
    rpm: int | None
    pwm: int | None                             # 0-255
    mode: int | None                            # pwmN_enable: 1 manual, 2 the firmware's curve
    folder: str                                 # the hwmon folder

    @property
    def mode_text(self) -> str:
        if self.mode == 1:
            return f"manual {round((self.pwm or 0) * 100 / 255)} %"
        if self.mode == 2:
            return "firmware curve"
        return "unknown mode"


@dataclass(frozen=True)
class Reading:
    gpu_c: float | None = None                  # amdgpu "edge"
    cpu_c: float | None = None                  # k10temp "Tctl"
    fans: tuple[Fan, ...] = ()
    fan_driver: str = ""

    @property
    def hottest(self) -> tuple[str, float] | None:
        found = [(name, c) for name, c in (("GPU", self.gpu_c), ("CPU", self.cpu_c)) if c is not None]
        return max(found, key=lambda pair: pair[1]) if found else None

    @property
    def turning(self) -> tuple[Fan, ...]:
        return tuple(f for f in self.fans if f.rpm)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def read_int(path: Path) -> int | None:
    try:
        return int(read_text(path))
    except ValueError:
        return None


def is_bc250(sys_root: Path) -> bool:
    return "BC-250" in read_text(sys_root / "class/dmi/id/board_name").upper().replace("BC250", "BC-250")


def temperature(folder: Path, label: str) -> float | None:
    """The temperature labeled *label* in a hwmon folder (temp1 when nothing has that label), in °C."""
    inputs = sorted(folder.glob("temp*_input"))
    chosen = next((p for p in inputs if read_text(p.with_name(p.name.replace("_input", "_label"))) == label),
                  folder / "temp1_input")
    milli = read_int(chosen)
    if milli is None:
        return None
    celsius = milli / 1000
    return celsius if VALID_C[0] <= celsius <= VALID_C[1] else None


def read_fans(folder: Path, bc250: bool) -> tuple[Fan, ...]:
    """The SuperIO's fan channels; on the BC-250 only the five it has headers for, CPU_FAN1 first."""
    fans = []
    for channel in range(1, 9):
        if not (folder / f"fan{channel}_input").exists() and not (folder / f"pwm{channel}").exists():
            continue
        if bc250 and channel not in BC250_HEADERS:
            continue
        header = BC250_HEADERS.get(channel) if bc250 else None
        fans.append(Fan(channel=channel,
                        header=header or read_text(folder / f"fan{channel}_label") or f"fan {channel}",
                        rpm=read_int(folder / f"fan{channel}_input"), pwm=read_int(folder / f"pwm{channel}"),
                        mode=read_int(folder / f"pwm{channel}_enable"), folder=str(folder)))
    return tuple(sorted(fans, key=lambda f: (f.channel != 2, f.channel)) if bc250 else fans)


def read_sensors(sys_root: Path = Path("/sys")) -> Reading:
    """Looks the hwmon folders up by name every time: their numbers change between boots."""
    gpu = cpu = None
    fans: tuple[Fan, ...] = ()
    driver = ""
    bc250 = is_bc250(sys_root)
    for folder in sorted((sys_root / "class/hwmon").glob("hwmon*")):
        name = read_text(folder / "name")
        if name == "amdgpu" and gpu is None:
            gpu = temperature(folder, "edge")
        elif name == "k10temp" and cpu is None:
            cpu = temperature(folder, "Tctl")
        elif name in FAN_DRIVERS and not driver:
            driver = name
            fans = read_fans(folder, bc250)
    return Reading(gpu_c=gpu, cpu_c=cpu, fans=fans, fan_driver=driver)


# --- The files -----------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Paths:
    etc: Path = Path("/etc")
    run: Path = Path("/run")

    @property
    def folder(self) -> Path:
        return self.etc / FOLDER

    @property
    def script(self) -> Path:
        return self.folder / "guard.py"

    @property
    def config(self) -> Path:
        return self.folder / "guard.json"

    @property
    def unit(self) -> Path:
        return self.etc / "systemd/system" / UNIT

    @property
    def state(self) -> Path:
        return self.run / FOLDER / "state.json"


def paths_from_env() -> Paths:
    root = Path(os.environ.get("BC250_SYSTEM_ROOT", "/"))       # another root only for testing
    return Paths(root / "etc", root / "run")


def read_limits(paths: Paths) -> Limits | None:
    try:
        data = json.loads(paths.config.read_text(encoding="utf-8"))
        limits = Limits(**{k: int(data[k]) for k in asdict(Limits())})
    except (OSError, ValueError, TypeError, KeyError):
        return None
    return None if limits_problem(limits) else limits


def installed(paths: Paths) -> Limits | None:
    """The guard's limits when all of it is there, else None."""
    if not (paths.script.is_file() and paths.unit.is_file()):
        return None
    return read_limits(paths) or Limits()


def outdated(paths: Paths, own: Path = Path(__file__)) -> bool:
    """Whether the installed copy differs from this file: another version of the app installed it."""
    try:
        return paths.script.read_bytes() != own.read_bytes()
    except OSError:
        return True


def read_state(paths: Paths, now: float | None = None) -> dict | None:
    """What the running guard wrote last; None when it is missing or older than STALE_S."""
    try:
        data = json.loads(paths.state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or (now if now is not None else time.time()) - data.get("time", 0) > STALE_S:
        return None
    return data


def unit_text() -> str:
    return "\n".join([
        "[Unit]",
        f"Description={APP_NAME}: the thermal guard (warns, cools, shuts down at a critical temperature)",
        f"Documentation={MANUAL_URL}",
        "",
        "[Service]",
        "Type=simple",
        f"ExecStart={SYSTEM_PYTHON} -I {Paths().script} run",
        "Restart=always",
        "RestartSec=5",
        f"RuntimeDirectory={FOLDER}",
        "RuntimeDirectoryMode=0755",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
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
    """The SELinux labels of the files (Fedora, Bazzite)."""
    if shutil.which("restorecon"):
        run(["restorecon", "-R", *map(str, paths)])


# --- What the app asks for, as root --------------------------------------------------------------------------------

def install(paths: Paths, limits: Limits, run: Runner = run, own: Path = Path(__file__)) -> None:
    problem = limits_problem(limits)
    if problem:
        raise ValueError(problem)
    write(paths.script, own.read_bytes())
    write(paths.config, (json.dumps(asdict(limits), indent=2) + "\n").encode())
    write(paths.unit, unit_text().encode())
    relabel(run, paths.folder, paths.unit)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", UNIT])
    result = run(["systemctl", "restart", UNIT])                # new limits and a new copy take effect now
    if not result.ok:
        raise ValueError(f"The guard is installed but did not start: {result.out.strip()}")


def uninstall(paths: Paths, run: Runner = run) -> None:
    run(["systemctl", "disable", "--now", UNIT])                # the guard puts the fans back as it stops
    for path in (paths.unit, paths.config, paths.script):
        path.unlink(missing_ok=True)
    try:
        paths.folder.rmdir()
    except OSError:
        pass
    run(["systemctl", "daemon-reload"])


# --- Asked for by the app ------------------------------------------------------------------------------------------

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


# --- The service ---------------------------------------------------------------------------------------------------

def notify_desktop(run: Runner, title: str, body: str, run_root: Path = Path("/run")) -> None:
    """A notification in every desktop session: as each user, on that user's session bus."""
    import pwd                                  # Linux only; the app imports this file on Windows too
    for bus in sorted((run_root / "user").glob("*/bus")):
        try:
            uid = int(bus.parent.name)
            user = pwd.getpwuid(uid).pw_name
        except (ValueError, KeyError):
            continue
        if uid < 1000:
            continue
        run(["runuser", "-u", user, "--", "env", f"DBUS_SESSION_BUS_ADDRESS=unix:path={bus}", "notify-send",
             "--urgency=critical", f"--app-name={APP_NAME}", "--icon=dialog-warning", title, body])


@dataclass
class Guard:
    limits: Limits
    paths: Paths = field(default_factory=Paths)
    sys_root: Path = Path("/sys")
    run: Runner = run
    notify: Callable[[str, str], None] | None = None
    clock: Callable[[], float] = time.monotonic
    wall: Callable[[], float] = time.time

    def __post_init__(self) -> None:
        if self.notify is None:
            self.notify = lambda title, body: notify_desktop(self.run, title, body, self.paths.run)
        self.warned = False
        self.cooling = False
        self.hot_since: float | None = None
        self.powering_off = False
        self.saved: dict[tuple[str, int], tuple[int | None, int | None]] = {}
        self.events: deque[dict] = deque(maxlen=EVENTS)
        self.no_sensor = False
        self.seen_turning: set[int] = set()
        self.stopped_since: dict[int, float] = {}
        self.fan_warned: set[int] = set()

    def event(self, text: str, kind: str = "info", alert: bool = False) -> None:
        log(text)
        self.events.append({"time": self.wall(), "kind": kind, "text": text})
        if alert:
            self.notify(APP_NAME, text)

    def step(self) -> Reading:
        reading = read_sensors(self.sys_root)
        hottest = reading.hottest
        if hottest is None:
            if not self.no_sensor:
                self.no_sensor = True
                self.event("No GPU or CPU temperature can be read; the guard waits for one and does nothing until "
                           "then.", "warn")
        else:
            self.no_sensor = False
            self.check_limits(*hottest)
        self.check_fans(reading)
        self.write_state(reading)
        return reading

    def check_limits(self, name: str, celsius: float) -> None:
        lim, now = self.limits, self.clock()
        rearm = lim.warn_c - REARM_C
        if celsius >= lim.warn_c and not self.warned:
            self.warned = True
            self.event(f"The {name} is at {celsius:.0f} °C (warning at {lim.warn_c} °C).", "warn", alert=True)
        elif self.warned and celsius < rearm:
            self.warned = False
            self.event(f"The {name} is back at {celsius:.0f} °C.")
        if celsius >= lim.cool_c and not self.cooling:
            self.cooling = True
            done = " and ".join(d for d in (self.fans_full(), self.performance_off()) if d) or "nothing to do"
            self.event(f"The {name} is at {celsius:.0f} °C (cooling at {lim.cool_c} °C): {done}.", "bad",
                       alert=True)
        elif self.cooling and celsius < rearm:
            self.cooling = False
            self.restore_fans()
            self.event(f"The {name} is back at {celsius:.0f} °C: the fans are back as they were. Performance mode "
                       "stays off until you turn it on.")
        if celsius >= lim.shutdown_c:
            if self.hot_since is None:
                self.hot_since = now
                self.event(f"The {name} is at {celsius:.0f} °C (shutdown at {lim.shutdown_c} °C): the board shuts "
                           f"down in {lim.hold_s} s unless it cools.", "bad", alert=True)
            elif now - self.hot_since >= lim.hold_s and not self.powering_off:
                self.powering_off = True
                self.event(f"The {name} stayed at or above {lim.shutdown_c} °C for {lim.hold_s} s "
                           f"({celsius:.0f} °C now): shutting down to protect the board.", "bad", alert=True)
                self.run(["systemctl", "poweroff"])
        elif self.hot_since is not None:
            self.hot_since = None
            self.event(f"The {name} is below {lim.shutdown_c} °C again ({celsius:.0f} °C): no shutdown.")

    def fans_full(self) -> str:
        """Every channel to full speed; the old mode and value are kept to put back."""
        count = 0
        for fan in read_sensors(self.sys_root).fans:
            key = (fan.folder, fan.channel)
            self.saved.setdefault(key, (fan.mode, fan.pwm))
            folder = Path(fan.folder)
            try:
                (folder / f"pwm{fan.channel}_enable").write_text("1")
                (folder / f"pwm{fan.channel}").write_text(str(FULL_PWM))
                count += 1
            except OSError as exc:
                log(f"pwm{fan.channel}: {exc}")
        return "the fans to full speed" if count else ""

    def restore_fans(self) -> None:
        for (folder, channel), (mode, pwm) in self.saved.items():
            try:
                if pwm is not None:
                    (Path(folder) / f"pwm{channel}").write_text(str(pwm))
                if mode is not None:
                    (Path(folder) / f"pwm{channel}_enable").write_text(str(mode))
            except OSError as exc:
                log(f"pwm{channel}: {exc}")
        self.saved.clear()

    def performance_off(self) -> str:
        bus, path, iface = GOVERNOR
        state = self.run(["busctl", "--system", "get-property", bus, path, iface, "Enabled"])
        if not state.ok or not state.out.strip().endswith("true"):
            return ""
        result = self.run(["busctl", "--system", "set-property", bus, path, iface, "Enabled", "b", "false"])
        return "performance mode off" if result.ok else ""

    def check_fans(self, reading: Reading) -> None:
        """A fan that turned and now reads 0 RPM while it should turn has stopped (or lost its connector)."""
        now = self.clock()
        for fan in reading.fans:
            if fan.rpm:
                self.seen_turning.add(fan.channel)
                self.stopped_since.pop(fan.channel, None)
                if fan.channel in self.fan_warned:
                    self.fan_warned.discard(fan.channel)
                    self.event(f"{fan.header} turns again ({fan.rpm} RPM).")
                continue
            should_turn = fan.mode != 1 or bool(fan.pwm)
            if fan.channel not in self.seen_turning or fan.rpm is None or not should_turn:
                continue
            since = self.stopped_since.setdefault(fan.channel, now)
            if now - since >= FAN_STOP_S and fan.channel not in self.fan_warned:
                self.fan_warned.add(fan.channel)
                self.event(f"{fan.header} has stopped: it reads 0 RPM. Check the fan and its connector.", "bad",
                           alert=True)

    def level(self) -> str:
        if self.hot_since is not None:
            return "shutdown"
        if self.cooling:
            return "cooling"
        if self.warned:
            return "warn"
        return "ok"

    def write_state(self, reading: Reading) -> None:
        data = {"time": self.wall(), "level": self.level(), "limits": asdict(self.limits),
                "gpu_c": reading.gpu_c, "cpu_c": reading.cpu_c,
                "fans": [asdict(f) for f in reading.fans], "events": list(self.events)}
        try:
            write(self.paths.state, (json.dumps(data) + "\n").encode())
        except OSError as exc:
            log(f"{self.paths.state}: {exc}")

    def stop(self) -> None:
        """When the service stops: the fans back as they were."""
        if self.saved:
            self.restore_fans()
            log("Stopped: the fans are back as they were.")

    def loop(self, sleep: Callable[[float], None] = time.sleep) -> int:
        def stop(_signum, _frame):
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, stop)
        lim = self.limits
        self.event(f"Guard on: warning at {lim.warn_c} °C, cooling at {lim.cool_c} °C, shutdown at "
                   f"{lim.shutdown_c} °C held for {lim.hold_s} s.")
        try:
            while True:
                self.step()
                sleep(STEP_S)
        finally:
            self.stop()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="guard.py", description=__doc__.split("\n\n")[0])
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("run", help="watch the temperatures (the service)")
    add = actions.add_parser("install", help="install or update the guard and (re)start it")
    defaults = Limits()
    add.add_argument("--warn", type=int, default=defaults.warn_c, help="°C")
    add.add_argument("--cool", type=int, default=defaults.cool_c, help="°C")
    add.add_argument("--shutdown", type=int, default=defaults.shutdown_c, help="°C")
    add.add_argument("--hold", type=int, default=defaults.hold_s, help="seconds")
    actions.add_parser("uninstall", help="stop and remove the guard")
    args = parser.parse_args(argv)
    paths = paths_from_env()

    if args.action == "run":
        limits = read_limits(paths)
        if limits is None:
            limits = Limits()
            log(f"{paths.config} is missing or broken; the guard uses its defaults")
        return Guard(limits, paths).loop()
    try:
        if args.action == "install":
            install(paths, Limits(args.warn, args.cool, args.shutdown, args.hold))
        else:
            uninstall(paths)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
