# SPDX-License-Identifier: GPL-3.0-or-later
"""The driver on the system: installed, loaded at boot and rebuilt after a kernel update, as root.

Bazzite's /usr is read-only, so the modules cannot go where modprobe looks and the firmware cannot go under
/lib/firmware. They live under /var instead and are loaded with insmod, with the firmware folder given to the
loader as a module parameter (aic_fw_path). What this file puts on the system:
 * /etc/bc250-usb-wifi/driver.py, a copy of this file, which the service runs; driver.json beside it says which
   driver branch is installed;
 * /etc/systemd/system/bc250-usb-wifi.service: at boot, `load`: builds the modules when there are none for the
   running kernel (the sources are kept, gcc and the kernel's build tree are in Bazzite's image, no network is
   needed), loads them, and ejects a stick that sits in storage mode;
 * /etc/udev/rules.d/90-bc250-usb-wifi.rules: a stick plugged in later is switched out of storage mode by
   ejecting its virtual disk, the same as every driver package does;
 * /var/lib/bc250-usb-wifi/src/<branch>: the driver sources, from the app's checkout;
 * /var/lib/bc250-usb-wifi/modules/<kernel>: the two modules, the firmware folder and the build log, per kernel;
 * /run/bc250-usb-wifi/state.json: what the service did last, for the app to show.

The app runs this file through pkexec with the system python3 in isolated mode (-I) to install or remove the
driver; the installed copy is what the service runs. Only the standard library is used.

Nothing here reboots the board: a kernel update's reboot is Bazzite's, and the service does its work at the boot
that follows (the owner's rule: advice, not reboots)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

SYSTEM_PYTHON = "/usr/bin/python3"
FOLDER = "bc250-usb-wifi"                       # in /etc, /var/lib and /run
UNIT = "bc250-usb-wifi.service"
RULES = "90-bc250-usb-wifi.rules"
MANUAL_URL = "https://robertotorino.github.io/nexus/apps/wdriver/"
APP_NAME = "BC-250 USB Wi-Fi"
LOADER = "aic_load_fw"
DRIVER = "aic8800_fdrv"
MODULES = (LOADER, DRIVER)                      # load order; unloaded in reverse
FW_FOLDER = "aic8800D80"
STORAGE_PRODUCTS = ("5721", "5722", "5723", "5724", "572c")
BRANCHES = ("main", "legacy-mcu1")
BUILD_TIMEOUT_S = 1800

Runner = Callable[..., "Result"]


@dataclass(frozen=True)
class Result:
    code: int
    out: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def run(argv: list[str], timeout: float = 30, cwd: Path | None = None) -> Result:
    try:
        done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout,
                              cwd=cwd)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Result(127, str(exc))
    return Result(done.returncode, done.stdout)


def log(text: str) -> None:
    print(text, flush=True)                     # the journal, through the service's stdout


# --- The files -----------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Paths:
    etc: Path = Path("/etc")
    var: Path = Path("/var/lib")
    run: Path = Path("/run")
    usr: Path = Path("/usr")
    sys: Path = Path("/sys")
    proc: Path = Path("/proc")
    dev: Path = Path("/dev")

    @property
    def folder(self) -> Path:
        return self.etc / FOLDER

    @property
    def script(self) -> Path:
        return self.folder / "driver.py"

    @property
    def config(self) -> Path:
        return self.folder / "driver.json"

    @property
    def unit(self) -> Path:
        return self.etc / "systemd/system" / UNIT

    @property
    def rules(self) -> Path:
        return self.etc / "udev/rules.d" / RULES

    @property
    def data(self) -> Path:
        return self.var / FOLDER

    def source(self, branch: str) -> Path:
        return self.data / "src" / branch

    def modules(self, kernel: str) -> Path:
        return self.data / "modules" / kernel

    @property
    def state(self) -> Path:
        return self.run / FOLDER / "state.json"

    def build_tree(self, kernel: str) -> Path:
        return self.usr / "lib/modules" / kernel / "build"


def paths_from_env() -> Paths:
    root = Path(os.environ.get("BC250_SYSTEM_ROOT", "/"))       # another root only for testing
    return Paths(root / "etc", root / "var/lib", root / "run", root / "usr", root / "sys", root / "proc",
                 root / "dev")


@dataclass(frozen=True)
class Config:
    branch: str
    commit: str = ""
    app_version: str = ""


def read_config(paths: Paths) -> Config | None:
    try:
        data = json.loads(paths.config.read_text(encoding="utf-8"))
        config = Config(str(data["branch"]), str(data.get("commit", "")), str(data.get("app_version", "")))
    except (OSError, ValueError, TypeError, KeyError):
        return None
    return config if config.branch in BRANCHES else None


def installed(paths: Paths) -> Config | None:
    """The installed driver's configuration when all of it is there, else None."""
    if not (paths.script.is_file() and paths.unit.is_file()):
        return None
    return read_config(paths)


def outdated(paths: Paths, own: Path = Path(__file__)) -> bool:
    """Whether the installed copy differs from this file: another version of the app installed it."""
    try:
        return paths.script.read_bytes() != own.read_bytes()
    except OSError:
        return True


def built_kernels(paths: Paths) -> tuple[str, ...]:
    folder = paths.data / "modules"
    if not folder.is_dir():
        return ()
    return tuple(sorted(k.name for k in folder.iterdir() if complete(k)))


def complete(folder: Path) -> bool:
    return all((folder / f"{m}.ko").is_file() for m in MODULES) and (folder / "fw" / FW_FOLDER).exists()


def read_state(paths: Paths) -> dict | None:
    """What the service wrote last, None when it never ran this boot."""
    try:
        data = json.loads(paths.state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_state(paths: Paths, state: dict) -> None:
    try:
        paths.state.parent.mkdir(parents=True, exist_ok=True)
        write(paths.state, (json.dumps(state, indent=2) + "\n").encode())
    except OSError as exc:
        log(f"could not write {paths.state}: {exc}")


def unit_text() -> str:
    # Type=simple with RemainAfterExit: a rebuild at boot takes minutes and must not hold the boot up, which a
    # oneshot in multi-user.target would; the unit stays active afterwards so `stop` unloads the modules.
    return "\n".join([
        "[Unit]",
        f"Description={APP_NAME}: the AIC8800 driver, built for the running kernel and loaded",
        f"Documentation={MANUAL_URL}",
        "After=systemd-modules-load.service",
        "",
        "[Service]",
        "Type=simple",
        "RemainAfterExit=yes",
        f"ExecStart={SYSTEM_PYTHON} -I {Paths().script} load",
        f"ExecStop={SYSTEM_PYTHON} -I {Paths().script} unload",
        f"RuntimeDirectory={FOLDER}",
        "RuntimeDirectoryMode=0755",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
    ])


def rules_text() -> str:
    """The stick's virtual disk ejected as soon as it appears, which switches the stick to loader mode; the loader
    then takes it. The product IDs are the storage modes the driver packages know."""
    lines = [f"# {APP_NAME}: switch an AIC8800 stick out of storage mode by ejecting its virtual disk."]
    for product in STORAGE_PRODUCTS:
        lines.append(f'ACTION=="add", KERNEL=="sd*", SUBSYSTEM=="block", ATTRS{{idVendor}}=="a69c", '
                     f'ATTRS{{idProduct}}=="{product}", RUN+="/usr/bin/eject /dev/%k"')
    return "\n".join(lines) + "\n"


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


def place_firmware(source: Path, target: Path) -> None:
    """The firmware files flat, with the aic8800D80 link to the folder itself: the loader reads <folder>/<file>,
    the Wi-Fi module appends /aic8800D80 to the same path (see builder.py)."""
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for f in sorted(source.iterdir()):
        if f.is_file():
            shutil.copy2(f, target / f.name)
    (target / FW_FOLDER).symlink_to(".")


def place_modules(build: Path, target: Path) -> None:
    """A build output (the app's, or the service's own) into the modules folder of a kernel."""
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for module in MODULES:
        shutil.copy2(build / f"{module}.ko", target / f"{module}.ko")
    place_firmware(build / "fw", target / "fw")
    if (build / "build.log").is_file():
        shutil.copy2(build / "build.log", target / "build.log")


# --- What the app asks for, as root --------------------------------------------------------------------------------

def install(paths: Paths, branch: str, build: Path, source: Path, kernel: str, commit: str = "",
            app_version: str = "", run: Runner = run, own: Path = Path(__file__)) -> None:
    """The driver built by the app for the running kernel, its sources for the next kernel, the rule and the
    service, which loads it now."""
    if branch not in BRANCHES:
        raise ValueError(f"Unknown driver branch {branch!r}.")
    if not complete(build):
        raise ValueError(f"{build} holds no complete build (the two modules and the firmware folder).")
    if not (source / "drivers/aic8800/Makefile").is_file() or not (source / "fw" / FW_FOLDER).is_dir():
        raise ValueError(f"{source} holds no driver sources (drivers/aic8800 and fw/{FW_FOLDER}).")
    shutil.rmtree(paths.data, ignore_errors=True)                # one branch at a time; old kernels go with it
    target = paths.source(branch)
    shutil.copytree(source / "drivers/aic8800", target / "drivers/aic8800",
                    ignore=shutil.ignore_patterns("*.o", "*.ko", "*.cmd", ".*.cmd", "*.mod", "*.mod.c",
                                                  "modules.order", "Module.symvers", ".tmp_versions"))
    shutil.copytree(source / "fw" / FW_FOLDER, target / "fw" / FW_FOLDER)
    place_modules(build, paths.modules(kernel))
    write(paths.script, own.read_bytes())
    write(paths.config, (json.dumps(asdict(Config(branch, commit, app_version)), indent=2) + "\n").encode())
    write(paths.unit, unit_text().encode())
    write(paths.rules, rules_text().encode())
    relabel(run, paths.folder, paths.unit, paths.rules, paths.data)
    run(["systemctl", "daemon-reload"])
    run(["udevadm", "control", "--reload"])
    run(["systemctl", "enable", UNIT])
    result = run(["systemctl", "restart", UNIT], timeout=120)   # loads the driver now
    if not result.ok:
        raise ValueError(f"The driver is installed but the service did not start: {result.out.strip()}")


def uninstall(paths: Paths, run: Runner = run) -> None:
    run(["systemctl", "disable", "--now", UNIT], timeout=60)    # unloads the modules
    for path in (paths.unit, paths.rules, paths.config, paths.script):
        path.unlink(missing_ok=True)
    try:
        paths.folder.rmdir()
    except OSError:
        pass
    shutil.rmtree(paths.data, ignore_errors=True)
    run(["systemctl", "daemon-reload"])
    run(["udevadm", "control", "--reload"])


# --- The service ---------------------------------------------------------------------------------------------------

def loaded(paths: Paths) -> set[str]:
    try:
        text = (paths.proc / "modules").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return {line.split(" ", 1)[0] for line in text.splitlines()} & set(MODULES)


def build(paths: Paths, branch: str, kernel: str, run: Runner = run) -> str:
    """The modules for a kernel, built from the kept sources with the kernel's own build tree. Returns what went
    wrong, "" when the modules folder is complete."""
    module_dir = paths.source(branch) / "drivers/aic8800"
    tree = paths.build_tree(kernel)
    if not (tree / ".config").is_file():
        return f"No build tree for kernel {kernel} at {tree} (kernel-devel is missing)."
    if not (module_dir / "Makefile").is_file():
        return f"No driver sources at {module_dir}."
    for tool in ("gcc", "make"):
        if shutil.which(tool) is None:
            return f"{tool} is not installed."
    target = paths.modules(kernel)
    jobs = os.cpu_count() or 2
    run(["make", "-C", str(tree), f"M={module_dir}", "clean"], timeout=120)
    result = run(["make", "-C", str(tree), f"M={module_dir}", f"-j{jobs}", "modules"], timeout=BUILD_TIMEOUT_S)
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    write(target / "build.log", result.out.encode())
    if not result.ok:
        return f"The build for kernel {kernel} failed (exit {result.code}); the log is {target / 'build.log'}."
    for module in MODULES:
        built = module_dir / module / f"{module}.ko"
        if not built.is_file():
            return f"The build left no {module}.ko; the log is {target / 'build.log'}."
        shutil.copy2(built, target / f"{module}.ko")
    place_firmware(paths.source(branch) / "fw" / FW_FOLDER, target / "fw")
    return ""


def storage_disks(paths: Paths) -> list[str]:
    """The virtual disks of sticks in storage mode: the SCSI vendor is "AIC" (seen 17-10-2026)."""
    disks = []
    block = paths.sys / "block"
    if not block.is_dir():
        return disks
    for disk in sorted(block.iterdir()):
        try:
            vendor = (disk / "device/vendor").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if disk.name.startswith("sd") and vendor == "AIC":
            disks.append(disk.name)
    return disks


def load(paths: Paths, kernel: str, run: Runner = run, now: Callable[[], float] = time.time,
         notify: Callable[[Runner, str, str], None] | None = None) -> int:
    """What the service does: build when needed, load, eject. Everything it did goes to the journal and the state
    file; a rebuild is also announced on the desktop."""
    notify = notify or notify_desktop
    state: dict = {"time": now(), "kernel": kernel, "built": False, "loaded": [], "ejected": [], "error": ""}
    config = read_config(paths)
    if config is None:
        state["error"] = f"{paths.config} is missing or broken."
        log(state["error"])
        write_state(paths, state)
        return 1
    state["branch"] = config.branch
    folder = paths.modules(kernel)
    if not complete(folder):
        log(f"no driver for kernel {kernel} yet: building it from the {config.branch} sources")
        error = build(paths, config.branch, kernel, run)
        if error:
            state["error"] = error
            log(error)
            write_state(paths, state)
            notify(run, f"{APP_NAME}: the Wi-Fi driver could not be built for kernel {kernel}",
                   f"{error} Open {APP_NAME} for the details.")
            return 1
        state["built"] = True
        log(f"built the driver for kernel {kernel}")
    already = loaded(paths)
    run(["modprobe", "cfg80211"])
    for module in MODULES:
        if module in already:
            state["loaded"].append(module)
            continue
        argv = ["insmod", str(folder / f"{module}.ko")]
        if module == LOADER:
            argv.append(f"aic_fw_path={folder / 'fw'}")
        result = run(argv)
        if not result.ok:
            state["error"] = f"insmod {module} failed: {result.out.strip()}"
            log(state["error"])
            write_state(paths, state)
            return 1
        state["loaded"].append(module)
    for disk in storage_disks(paths):
        result = run(["eject", str(paths.dev / disk)])
        log(f"ejected /dev/{disk} (a stick in storage mode): {'switched' if result.ok else result.out.strip()}")
        state["ejected"].append(disk)
    write_state(paths, state)
    log(f"loaded {', '.join(state['loaded'])} for kernel {kernel} ({config.branch})")
    if state["built"]:
        notify(run, f"{APP_NAME}: the Wi-Fi driver was rebuilt for kernel {kernel}",
               "The stick works as before. Plug it in again if it does not show up.")
    return 0


def unload(paths: Paths, run: Runner = run) -> int:
    for module in reversed(MODULES):
        if module in loaded(paths):
            run(["rmmod", module])
    return 0


def notify_desktop(run: Runner, title: str, body: str, run_root: Path = Path("/run")) -> None:
    """A notification in every desktop session: as each user, on that user's session bus."""
    import pwd                                  # Linux only; the app imports this file on Windows too
    if shutil.which("notify-send") is None:
        return
    for bus in sorted((run_root / "user").glob("*/bus")):
        try:
            uid = int(bus.parent.name)
            user = pwd.getpwuid(uid).pw_name
        except (ValueError, KeyError):
            continue
        if uid < 1000:
            continue
        run(["runuser", "-u", user, "--", "env", f"DBUS_SESSION_BUS_ADDRESS=unix:path={bus}", "notify-send",
             f"--app-name={APP_NAME}", "--icon=network-wireless", title, body])


# --- Asked for by the app ------------------------------------------------------------------------------------------

def command(args: list[str], own: Path = Path(__file__)) -> list[str]:
    """This file as root, through polkit's password dialog."""
    python = SYSTEM_PYTHON if Path(SYSTEM_PYTHON).is_file() else sys.executable
    return ["pkexec", python, "-I", str(own.resolve()), *args]


def answer(code: int, out: str) -> str:
    """What went wrong ("" when nothing did): main() prints one JSON line; pkexec exits with 126 or 127 when the
    password dialog is cancelled."""
    if code in (126, 127):
        return "Not authorised: the password dialog was cancelled or refused."
    for line in reversed(out.strip().splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            return "" if data.get("ok") else str(data.get("error") or "It failed without saying why.")
    return f"The helper stopped with exit code {code} without an answer:\n{out.strip()}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="driver.py", description=__doc__.split("\n\n")[0])
    actions = parser.add_subparsers(dest="action", required=True)
    add = actions.add_parser("install", help="install or update the driver and its service, and load it")
    add.add_argument("--branch", choices=BRANCHES, required=True)
    add.add_argument("--build", required=True, help="the app's build output for the running kernel")
    add.add_argument("--source", required=True, help="the app's checkout of the driver sources")
    add.add_argument("--commit", default="")
    add.add_argument("--app-version", default="")
    add.add_argument("--kernel", default=os.uname().release)
    actions.add_parser("uninstall", help="unload and remove the driver, its service and its rule")
    actions.add_parser("load", help="build when needed, load the modules, eject a stick in storage mode (the service)")
    actions.add_parser("unload", help="unload the modules (the service, on stop)")
    args = parser.parse_args(argv)
    paths = paths_from_env()

    # run is passed by name on purpose: the module's run as it is now, so a test can stand in for it.
    if args.action == "load":
        return load(paths, os.uname().release, run=run)
    if args.action == "unload":
        return unload(paths, run=run)
    try:
        if args.action == "install":
            install(paths, args.branch, Path(args.build), Path(args.source), args.kernel, args.commit,
                    args.app_version, run=run)
        else:
            uninstall(paths, run=run)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
