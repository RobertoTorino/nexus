# SPDX-License-Identifier: GPL-3.0-or-later
"""The system part: what runs as root, before anyone logs in. At boot no desktop runs yet, so a board with only a
Bluetooth keyboard and mouse has nothing to log in with until they are paired; this pairs them.

This file runs as root and needs only the standard library (the battery part also Bazzite's dbus-python and
PyGObject, python3-dbus and python3-gobject). The app runs it through pkexec with the system python3 in isolated mode
(-I) to install or remove the system part, and the installed copy runs at boot:
 * bc250-bluetooth-pairing.service searches for the listed devices for WINDOW_S seconds after every boot, and stops
   as soon as every one is connected. One that is in pairing mode is trusted, paired and connected; one that was
   paired before but refuses its old pairing twice is removed and paired again. Devices with other names are never
   paired.
 * bc250-bluetooth-pairing-battery.service, when chosen, shows the battery of PlayStation controllers in the
   Bluetooth icon: a DualSense reports its battery through the kernel's PlayStation driver
   (/sys/class/power_supply/ps-controller-battery-<address>), not through Bluetooth, so the icon, which shows what
   BlueZ reports, has none. It registers as a BlueZ battery provider and hands BlueZ each controller's level every
   PERIOD_S seconds. It restarts with bluetoothd, which forgets every provider when it stops.
 * /etc/bc250-bluetooth-pairing/boot.json holds the names and the two choices; boot.py next to it is the copy that
   runs."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

SYSTEM_PYTHON = "/usr/bin/python3"
FOLDER = "bc250-bluetooth-pairing"              # in /etc: boot.py and boot.json
PAIR_UNIT = "bc250-bluetooth-pairing.service"
BATTERY_UNIT = "bc250-bluetooth-pairing-battery.service"
MANUAL_URL = "https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/btpair/"
NAME_BYTES = 248                                # the longest name Bluetooth gives a device
WINDOW_S = 300                                  # how long the search runs after boot
ADAPTER_WAIT_S = 30                             # how long the adapter may take to appear at boot
PAIR_TIMEOUT_S = 25
CONNECT_TIMEOUT_S = 15
REFUSALS = 2                                    # connections refused before a paired device is paired again
PERIOD_S = 30                                   # how often the battery levels are handed to BlueZ
SUPPLIES = Path("/sys/class/power_supply")

Runner = Callable[[list[str]], "Result"]


@dataclass(frozen=True)
class Result:
    code: int
    out: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def run(argv: list[str], timeout: float = 30) -> Result:
    try:
        done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return Result(124, out)
    except OSError as exc:
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
    def pair_unit(self) -> Path:
        return self.etc / "systemd/system" / PAIR_UNIT

    @property
    def battery_unit(self) -> Path:
        return self.etc / "systemd/system" / BATTERY_UNIT


@dataclass(frozen=True)
class Config:
    names: tuple[str, ...] = ()
    pair: bool = False
    battery: bool = False


def name_problem(name: str) -> str:
    """Why *name* cannot be listed ("" when it can): it is matched exactly against the names devices give."""
    if not name.strip():
        return "The name is empty."
    if name != name.strip():
        return "The name starts or ends with a space."
    if not name.isprintable():
        return "The name holds a character that is not printable."
    if len(name.encode()) > NAME_BYTES:
        return f"At most {NAME_BYTES} bytes: no Bluetooth device has a longer name."
    return ""


def read_config(paths: Paths) -> Config | None:
    try:
        data = json.loads(paths.config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    names = data.get("names")
    if not isinstance(names, list) or not all(isinstance(n, str) and not name_problem(n) for n in names):
        return None
    return Config(tuple(names), data.get("pair") is True, data.get("battery") is True)


def installed(paths: Paths) -> Config | None:
    """The system part's settings when it is there, else None."""
    if not (paths.script.is_file() and paths.pair_unit.is_file()):
        return None
    return read_config(paths)


def outdated(paths: Paths, own: Path = Path(__file__)) -> bool:
    """Whether the installed copy differs from this file: another version of the app installed it."""
    try:
        return paths.script.read_bytes() != own.read_bytes()
    except OSError:
        return True


def pair_unit_text() -> str:
    return "\n".join([
        "[Unit]",
        "Description=BC-250 Bluetooth Pairing: pair the listed keyboard, mouse and controllers after boot",
        f"Documentation={MANUAL_URL}",
        "Wants=bluetooth.service",
        "After=bluetooth.service",
        "",
        "[Service]",
        "Type=simple",
        f"ExecStart={SYSTEM_PYTHON} -I {Paths().script} pair",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
    ])


def battery_unit_text() -> str:
    return "\n".join([
        "[Unit]",
        "Description=BC-250 Bluetooth Pairing: PlayStation controller batteries in the Bluetooth icon",
        f"Documentation={MANUAL_URL}",
        "Wants=bluetooth.service",
        "After=bluetooth.service",
        "# Restarted with bluetoothd, which forgets every battery provider when it stops.",
        "PartOf=bluetooth.service",
        "",
        "[Service]",
        f"ExecStart={SYSTEM_PYTHON} -I {Paths().script} battery",
        "Restart=on-failure",
        "RestartSec=10",
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
    """The SELinux labels of the folders the files are in (Fedora, Bazzite)."""
    if shutil.which("restorecon"):
        run(["restorecon", "-R", *map(str, paths)])


# --- What the app asks for, as root ------------------------------------------------------------------------------

def install(paths: Paths, config: Config, run: Runner = run, own: Path = Path(__file__)) -> None:
    """Writes the system part with *config*: the search at boot enabled when it pairs, the battery service enabled
    and started when chosen. Nothing is paired now: the search runs at the next boot, or with start."""
    for name in config.names:
        problem = name_problem(name)
        if problem:
            raise ValueError(f"{name!r}: {problem}")
    write(paths.script, own.read_bytes())
    write(paths.config, (json.dumps({"names": list(config.names), "pair": config.pair, "battery": config.battery},
                                    indent=2, ensure_ascii=False) + "\n").encode())
    write(paths.pair_unit, pair_unit_text().encode())
    write(paths.battery_unit, battery_unit_text().encode())
    relabel(run, paths.folder, paths.pair_unit, paths.battery_unit)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable" if config.pair else "disable", PAIR_UNIT])
    if config.battery:
        run(["systemctl", "enable", BATTERY_UNIT])
        run(["systemctl", "restart", BATTERY_UNIT])         # this copy of boot.py, after an update too
    else:
        run(["systemctl", "disable", "--now", BATTERY_UNIT])


def uninstall(paths: Paths, run: Runner = run) -> None:
    run(["systemctl", "disable", "--now", PAIR_UNIT, BATTERY_UNIT])
    for path in (paths.pair_unit, paths.battery_unit, paths.config, paths.script):
        path.unlink(missing_ok=True)
    try:
        paths.folder.rmdir()
    except OSError:
        pass
    run(["systemctl", "daemon-reload"])


def start(run: Runner = run) -> None:
    """Search again now, without a reboot: the service starts over (for WINDOW_S seconds)."""
    result = run(["systemctl", "restart", "--no-block", PAIR_UNIT])
    if not result.ok:
        raise OSError(result.out.strip() or f"systemctl could not start {PAIR_UNIT}")


# --- Asked for by the app ----------------------------------------------------------------------------------------

def command(args: list[str], own: Path = Path(__file__)) -> list[str]:
    """This file as root, through polkit's password dialog."""
    python = SYSTEM_PYTHON if Path(SYSTEM_PYTHON).is_file() else sys.executable
    return ["pkexec", python, "-I", str(own.resolve()), *args]


def install_args(config: Config) -> list[str]:
    """The command line of install for *config*."""
    args = ["install"]
    for name in config.names:
        args += ["--name", name]
    return args + (["--pair"] if config.pair else []) + (["--battery"] if config.battery else [])


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
    return out.strip() or f"It failed (exit code {code})."


# --- The search after boot (bluetoothctl) ------------------------------------------------------------------------

def devices(text: str) -> list[tuple[str, str]]:
    """(address, name) from the lines of `bluetoothctl devices`: "Device AA:BB:CC:DD:EE:FF Name with spaces"."""
    found = []
    for line in text.splitlines():
        parts = line.strip().split(" ", 2)
        if len(parts) == 3 and parts[0] == "Device" and len(parts[1]) == 17:
            found.append((parts[1], parts[2]))
    return found


def info_field(text: str, key: str) -> str:
    """One field of `bluetoothctl info`: "\\tPaired: yes" gives "yes" for Paired; "" when it is not there."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(f"{key}: "):
            return line[len(key) + 2:]
    return ""


@dataclass
class Search:
    """The search after boot: *run* runs bluetoothctl and busctl, *spawn* starts one that keeps running (the scan,
    a pairing), *sleep* and *clock* wait and tell the time. The tests give fakes of all four."""
    names: tuple[str, ...]
    run: Runner = run
    spawn: Callable[[list[str]], subprocess.Popen] = lambda argv: subprocess.Popen(
        argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    window: float = WINDOW_S
    dry: bool = False
    refusals: dict[str, int] = field(default_factory=dict)

    def ctl(self, *args: str, timeout: int = 0) -> Result:
        """bluetoothctl with *args*; with *timeout*, it waits that long for the device (connect)."""
        return self.run(["bluetoothctl", *(["--timeout", str(timeout)] if timeout else []), *args])

    def field(self, address: str, key: str) -> str:
        return info_field(self.ctl("info", address).out, key)

    def resolved(self, address: str) -> bool:
        """Whether the device's services are read; bluetoothctl info does not show it, D-Bus does. Stopped at
        Paired alone, the services are never read and a keyboard types nothing."""
        tree = self.run(["busctl", "tree", "--list", "org.bluez"]).out
        path = next((p.strip() for p in tree.splitlines() if p.strip().endswith(f"/dev_{address.replace(':', '_')}")),
                    "")
        if not path:
            return False
        got = self.run(["busctl", "get-property", "org.bluez", path, "org.bluez.Device1", "ServicesResolved"])
        return got.out.strip() == "b true"

    def adapter(self) -> bool:
        """Waits for the adapter (it can take a few seconds at boot) and switches it on."""
        for _ in range(ADAPTER_WAIT_S):
            shown = self.ctl("show").out
            if shown.startswith("Controller") or "\nController" in shown:
                if "Powered: yes" not in shown:
                    self.ctl("power", "on")
                return True
            self.sleep(1)
        return False

    def connected_names(self) -> set[str]:
        return {name for _address, name in devices(self.ctl("devices", "Connected").out)}

    def pair(self, address: str, name: str) -> bool:
        """Trust, pair and connect one device; False when pairing failed."""
        log(f"pairing {name} ({address})")
        # Trusted before pairing: a controller connects back the moment pairing ends, and an untrusted one is refused.
        self.ctl("trust", address)
        # bluetoothctl waits out its whole timeout even after pairing succeeded: stopped once the device is paired
        # and its services are read.
        process = self.spawn(["bluetoothctl", "--timeout", str(PAIR_TIMEOUT_S), "--agent", "NoInputNoOutput",
                              "pair", address])
        try:
            for _ in range(PAIR_TIMEOUT_S * 2):
                if self.field(address, "Paired") == "yes" and self.resolved(address):
                    break
                if process.poll() is not None:
                    break
                self.sleep(0.5)
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        if self.field(address, "Paired") != "yes":
            log(f"pairing {name} failed; trying again.")
            return False
        self.ctl("trust", address)
        # Pairing usually leaves it connected; connect also waits out its whole timeout, so only when needed.
        if self.field(address, "Connected") != "yes":
            self.ctl("connect", address, timeout=CONNECT_TIMEOUT_S)
        log(f"{name}: paired, trusted, connected: {self.field(address, 'Connected') or 'no'}")
        return True

    def handle(self, address: str, name: str) -> None:
        """A listed device that is advertising and not connected."""
        if self.dry:
            log(f"would pair {name} ({address}), paired now: {self.field(address, 'Paired') or 'no'}")
            return
        if self.field(address, "Paired") == "yes":
            self.ctl("connect", address, timeout=CONNECT_TIMEOUT_S)
            if self.field(address, "Connected") == "yes":
                log(f"{name} reconnected.")
                return
            # Advertising, yet refusing a connection twice: the device has dropped its pairing. Pair it again.
            self.refusals[address] = self.refusals.get(address, 0) + 1
            if self.refusals[address] < REFUSALS:
                return
            log(f"{name} ({address}) no longer accepts its old pairing; pairing it again.")
            self.ctl("remove", address)
            self.refusals.pop(address, None)
            self.sleep(2)
            return
        self.pair(address, name)

    def loop(self) -> int:
        if not self.names:
            log("no device names listed; nothing to do.")
            return 0
        if not self.adapter():
            log("no Bluetooth adapter found.")
            return 0
        scan = self.spawn(["bluetoothctl", "--timeout", str(int(self.window)), "scan", "on"])
        log(f"searching for {', '.join(self.names)} for {int(self.window)} s.")
        missing: list[str] = []
        try:
            end = self.clock() + self.window
            while self.clock() < end:
                connected = self.connected_names()
                missing = [n for n in self.names if n not in connected]
                if not missing:
                    log("every listed device is connected.")
                    return 0
                for address, name in devices(self.ctl("devices").out):
                    if name not in self.names or name in self.connected_names():
                        continue                    # not listed, or one of that name is connected already
                    info = self.ctl("info", address).out
                    if info_field(info, "Connected") == "yes":
                        continue
                    if not info_field(info, "RSSI"):
                        continue                    # not heard in this search: not in pairing mode or out of range
                    self.handle(address, name)
                self.sleep(1)
        finally:
            if scan.poll() is None:
                scan.terminate()
        log(f"search ended; not connected: {', '.join(missing)}")
        return 0


# --- The battery of PlayStation controllers (BlueZ battery provider) ---------------------------------------------

def levels(supplies: Path = SUPPLIES) -> dict[str, int]:
    """Each controller's address (upper case) and its battery percentage, from the PlayStation driver."""
    found = {}
    for supply in supplies.glob("ps-controller-battery-*"):
        try:
            found[supply.name.rsplit("-", 1)[1].upper()] = max(0, min(100, int((supply / "capacity").read_text())))
        except (OSError, ValueError):
            pass
    return found


def battery() -> int:                                   # pragma: no cover (the system bus and BlueZ)
    """Registers with BlueZ as a battery provider and keeps the levels current. dbus-python and PyGObject are
    Bazzite's own (python3-dbus, python3-gobject); they are imported here so the rest runs without them."""
    import dbus
    import dbus.mainloop.glib
    import dbus.service
    from gi.repository import GLib

    provider_iface, root_path, source = "org.bluez.BatteryProvider1", "/org/bc250/bluetooth_pairing", \
        "PlayStation controller driver"
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    def props(device: str, percentage: int) -> dict:
        return {"Device": dbus.ObjectPath(device), "Percentage": dbus.Byte(percentage), "Source": source}

    class Battery(dbus.service.Object):
        def __init__(self, path: str, device: str, percentage: int):
            super().__init__(bus, path)
            self.device, self.percentage = device, percentage

        @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ss", out_signature="v")
        def Get(self, interface, name):  # noqa: N802 (D-Bus)
            return props(self.device, self.percentage)[name]

        @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface):  # noqa: N802
            return props(self.device, self.percentage)

        @dbus.service.signal("org.freedesktop.DBus.Properties", signature="sa{sv}as")
        def PropertiesChanged(self, interface, changed, invalidated):  # noqa: N802
            pass

        def update(self, percentage: int) -> None:
            if percentage != self.percentage:
                self.percentage = percentage
                self.PropertiesChanged(provider_iface, {"Percentage": dbus.Byte(percentage)}, [])

    shown: dict[str, Battery] = {}

    class Root(dbus.service.Object):
        """The object manager BlueZ reads the providers from."""

        @dbus.service.method("org.freedesktop.DBus.ObjectManager", out_signature="a{oa{sa{sv}}}")
        def GetManagedObjects(self):  # noqa: N802
            return {b.__dbus_object_path__: {provider_iface: props(b.device, b.percentage)} for b in shown.values()}

        @dbus.service.signal("org.freedesktop.DBus.ObjectManager", signature="oa{sa{sv}}")
        def InterfacesAdded(self, path, interfaces):  # noqa: N802
            pass

        @dbus.service.signal("org.freedesktop.DBus.ObjectManager", signature="oas")
        def InterfacesRemoved(self, path, interfaces):  # noqa: N802
            pass

    root = Root(bus, root_path)
    manager = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
    adapter = next(path for path, ifaces in manager.GetManagedObjects().items()
                   if "org.bluez.BatteryProviderManager1" in ifaces)
    loop = GLib.MainLoop()
    failed: list[str] = []

    def registered() -> None:
        log(f"registered with {adapter} as a battery provider")

    def refused(error) -> None:
        failed.append(str(error))
        loop.quit()

    # Asynchronous, from the running loop: BlueZ reads the providers back (GetManagedObjects) before it answers, and
    # a blocking call would leave no one to answer it.
    GLib.idle_add(lambda: dbus.Interface(bus.get_object("org.bluez", adapter), "org.bluez.BatteryProviderManager1")
                  .RegisterBatteryProvider(dbus.ObjectPath(root_path), reply_handler=registered,
                                           error_handler=refused) and False)

    def tick() -> bool:
        now = levels()
        known = {str(ifaces["org.bluez.Device1"]["Address"]).upper(): str(path)
                 for path, ifaces in manager.GetManagedObjects().items() if "org.bluez.Device1" in ifaces}
        for address, percentage in now.items():
            if address in shown:
                shown[address].update(percentage)
            elif address in known:
                path = f"{root_path}/dev_{address.replace(':', '_')}"
                shown[address] = Battery(path, known[address], percentage)
                root.InterfacesAdded(dbus.ObjectPath(path), {provider_iface: props(known[address], percentage)})
                log(f"{address}: {percentage}%")
        for address in [a for a in shown if a not in now]:
            gone = shown.pop(address)
            path = gone.__dbus_object_path__
            gone.remove_from_connection()
            root.InterfacesRemoved(dbus.ObjectPath(path), [provider_iface])
        return True

    tick()
    GLib.timeout_add_seconds(PERIOD_S, tick)
    loop.run()
    if failed:
        log(f"BlueZ refused the battery provider: {failed[0]}")
        return 1                                    # the service starts it again (Restart=on-failure)
    return 0


# --- Main --------------------------------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="boot.py", description=__doc__.split("\n\n")[0])
    actions = parser.add_subparsers(dest="action", required=True)
    pair = actions.add_parser("pair", help="after boot, from the service: search and pair the listed devices")
    pair.add_argument("--dry-run", action="store_true", help="search and say what it would do, pair nothing")
    actions.add_parser("battery", help="from the service: controller batteries in the Bluetooth icon")
    add = actions.add_parser("install", help="install or update the system part")
    add.add_argument("--name", action="append", default=[], help="a device name to pair (once per name)")
    add.add_argument("--pair", action="store_true", help="search and pair them after every boot")
    add.add_argument("--battery", action="store_true", help="show controller batteries in the Bluetooth icon")
    actions.add_parser("uninstall", help="remove the system part")
    actions.add_parser("start", help="search again now, without a reboot")
    args = parser.parse_args(argv)
    paths = Paths(Path(os.environ.get("BC250_SYSTEM_ROOT", "/")) / "etc")      # another root only for testing
    if args.action == "pair":
        config = read_config(paths)
        if config is None:
            log(f"{paths.config} is missing or broken; nothing to do.")
            return 0
        return Search(config.names, dry=args.dry_run).loop()
    if args.action == "battery":
        return battery()
    try:
        if args.action == "install":
            install(paths, Config(tuple(args.name), args.pair, args.battery), run)
        elif args.action == "uninstall":
            uninstall(paths, run)
        else:
            start(run)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
