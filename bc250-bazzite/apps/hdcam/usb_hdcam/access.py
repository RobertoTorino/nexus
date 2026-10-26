# SPDX-License-Identifier: GPL-3.0-or-later
"""Access to the camera's boot loader for the user at the board. Its usbfs node is root's; a udev rule gives the
logged-in user access instead (uaccess, as for a game controller), for the boot loader's USB ID only. The same rule
starts the user's load service when the camera is plugged in (systemd's SYSTEMD_USER_WANTS), so the firmware is sent
as a PlayStation would, with nothing running as root. The camera itself, once loaded, is a video device that Bazzite
already gives the user; the rule keeps it out of USB autosuspend, as the camera forgets its picture settings when it
is suspended (found on the owner's board, 23-10-2026: 2 s after the last program let go, the kernel suspended it,
and the exposure fell back to the camera's dark default while the driver still reported Auto Mode).

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
RULE = "70-bc250-usb-hdcam.rules"               # before 73-seat-late.rules, which turns uaccess into the user's ACL
VENDOR, PRODUCT = "05a9", "0580"                # as camera.py, which this file cannot import (it runs on its own)
CAMERAS = ("058c", "058a")                      # the PS5 HD Camera and the PS4 Camera with their firmware
SERVICE = "bc250-usb-hdcam-load.service"        # written by install.sh in the user's systemd folder


def rule_text() -> str:
    return ("# BC250 Bazzite Suite, USB HD Cam: the logged-in user may load the PlayStation HD Camera's firmware,\n"
            "# and the user's load service does so when the camera is plugged in.\n"
            f'SUBSYSTEM=="usb", ENV{{DEVTYPE}}=="usb_device", ATTR{{idVendor}}=="{VENDOR}", '
            f'ATTR{{idProduct}}=="{PRODUCT}", TAG+="uaccess", TAG+="systemd", '
            f'ENV{{SYSTEMD_USER_WANTS}}+="{SERVICE}"\n'
            "# The camera with its firmware stays powered: suspended, it forgets its picture settings.\n"
            f'SUBSYSTEM=="usb", ENV{{DEVTYPE}}=="usb_device", ATTR{{idVendor}}=="{VENDOR}", '
            f'ATTR{{idProduct}}=="{"|".join(CAMERAS)}", TEST=="power/control", ATTR{{power/control}}="on"\n')


def rule_path(root: Path | str = "/") -> Path:
    return Path(root, "etc/udev/rules.d", RULE)


def installed(root: Path | str = "/") -> bool:
    """The rule as this version writes it: an older one is offered again (Allow access)."""
    try:
        return rule_path(root).read_text() == rule_text()
    except (OSError, UnicodeDecodeError):
        return False


def outdated(root: Path | str = "/") -> bool:
    return rule_path(root).is_file() and not installed(root)


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
    """The access takes effect at once on a camera that is already plugged in."""
    run(["udevadm", "control", "--reload"])
    run(["udevadm", "trigger", "--subsystem-match=usb", f"--attr-match=idVendor={VENDOR}"])


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
