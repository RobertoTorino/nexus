# SPDX-License-Identifier: GPL-3.0-or-later
"""Access to the screen's port for the user at the board. The kernel makes it /dev/ttyACM<n>, owned by root and the
dialout group, which Bazzite's users are not in. A udev rule gives the logged-in user access instead (uaccess, as
for a game controller), for this USB ID only.

This file runs as root and needs only the standard library: the app runs it through pkexec with the system python3 in
isolated mode (-I) to add or remove the rule. It prints one JSON line with what went wrong, if anything."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SYSTEM_PYTHON = "/usr/bin/python3"
RULE = "70-bc250-usb-ips35.rules"               # before 73-seat-late.rules, which turns uaccess into the user's ACL
VENDOR, PRODUCT = "1a86", "5722"                # as screen.py, which this file cannot import (it runs on its own)


def rule_text() -> str:
    return ("# BC250 Bazzite Suite, USB IPS3.5: the logged-in user may use the USB IPS screen's serial port.\n"
            f'SUBSYSTEM=="tty", ATTRS{{idVendor}}=="{VENDOR}", ATTRS{{idProduct}}=="{PRODUCT}", TAG+="uaccess"\n')


def rule_path(root: Path | str = "/") -> Path:
    return Path(root, "etc/udev/rules.d", RULE)


def installed(root: Path | str = "/") -> bool:
    return rule_path(root).is_file()


def run(argv: list[str]) -> None:
    """A missing or failing command does not stop the change: the rule is written, and udev reads it at the next
    plug-in anyway."""
    try:
        subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def install(root: Path | str = "/", run=run) -> None:
    path = rule_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(rule_text())
    temp.chmod(0o644)
    temp.replace(path)
    if shutil.which("restorecon"):              # the SELinux label of rules.d (Fedora, Bazzite)
        run(["restorecon", str(path)])
    reload(run)


def uninstall(root: Path | str = "/", run=run) -> None:
    rule_path(root).unlink(missing_ok=True)
    reload(run)


def reload(run=run) -> None:
    """The rule takes effect at once on a screen that is already plugged in."""
    run(["udevadm", "control", "--reload"])
    run(["udevadm", "trigger", "--subsystem-match=tty"])


def command(args: list[str], own: Path = Path(__file__)) -> list[str]:
    """This file as root, through polkit's password dialog."""
    python = SYSTEM_PYTHON if Path(SYSTEM_PYTHON).is_file() else sys.executable
    return ["pkexec", python, "-I", str(own.resolve()), *args]


def answer(code: int, out: str) -> str:
    """What went wrong ("" when nothing did); pkexec exits with 126 or 127 when the password dialog is canceled."""
    if code in (126, 127):
        return "Not authorized: the password dialog was canceled or refused."
    for line in reversed(out.strip().splitlines()):
        try:
            return json.loads(line).get("error", "")
        except (ValueError, AttributeError):
            continue
    return "" if code == 0 else f"The change failed (exit code {code}): {out.strip() or 'no output'}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="access.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=("install", "uninstall"))
    args = parser.parse_args(argv)
    root = os.environ.get("BC250_SYSTEM_ROOT", "/")         # another root only for testing
    try:
        install(root, run) if args.action == "install" else uninstall(root, run)
    except OSError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    print(json.dumps({"error": ""}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
