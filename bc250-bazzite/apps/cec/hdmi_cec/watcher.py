# SPDX-License-Identifier: GPL-3.0-or-later
"""The background part of the app: python -m hdmi_cec.watcher [--restart-picture] [--pause-media], started
by the user service bc250-hdmi-cec-watch.service with the desktop session.

Every POLL_S seconds it asks the TV for its power status (Give Device Power Status: a question, it wakes nothing).
 * --restart-picture: when the TV comes back on, it switches the CEC adapter's output to another refresh rate for a
   moment and back: a new signal, so the DP-to-HDMI converter handshakes with the TV again (see display.py).
 * --pause-media: when the TV goes to standby, it pauses the media players that play (media.py), and continues
   them when the TV is on again.
One missed answer is not "off": only SILENT_POLLS of them in a row are (the TV unplugged), so a glitch on the bus
neither flickers the picture nor pauses anything. It writes one line to the journal for each thing it does."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from bc250_core.platform import config_home

from . import bazzite, cec, display, media
from .runner import Result

POLL_S = 5
SETTLE_S = 3                            # after the TV reports on, before the switch
HOLD_S = 4                              # on the other refresh rate
SILENT_POLLS = 3                        # this many unanswered questions in a row: the TV counts as off


def run(argv: list[str]) -> Result:
    try:
        done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Result(127, str(exc))
    return Result(done.returncode, done.stdout)


def log(text: str) -> None:
    print(text, flush=True)


class Watcher:
    def __init__(self, run: Callable[[list[str]], Result] = run, sleep: Callable[[float], None] = time.sleep,
                 restart_picture: bool = True, pause_media: bool = False, config_dir: Path | None = None):
        self.run, self.sleep = run, sleep
        self.config_dir = config_dir or config_home()
        self.restart, self.pause = restart_picture, pause_media
        self.adapter: cec.Adapter | None = None
        self.last: str | None = None            # "on" or "off" at the last look; None before the first answer
        self.silent = 0                         # unanswered questions in a row
        self.paused: list[str] = []             # the players paused while the TV is off

    def find_adapter(self, dev_root: Path = Path("/dev")) -> cec.Adapter | None:
        found = []
        for device in cec.devices(dev_root):
            result = self.run([cec.CEC_CTL, *cec.info(device)])
            if result.ok:
                found.append(cec.parse_info(device, result.out))
        adapter = cec.pick(found)
        if adapter is None:
            return None
        name = bazzite.read_fragment(self.config_dir).get("osd_name") or cec.OSD_NAME
        cecd = self.run(["systemctl", "--user", "is-active", bazzite.CECD_UNIT]).ok    # it names the adapter itself
        if not adapter.configured or (cec.needs_name(adapter, name) and not cecd):   # as the app does
            configured = self.run([cec.CEC_CTL, *cec.configure(adapter.device, name)])
            adapter = cec.parse_info(adapter.device, configured.out) if "Driver Info" in configured.out else adapter
        return adapter

    def tv_power(self) -> str:
        return cec.power_status(self.run([cec.CEC_CTL, *cec.give_power_status(self.adapter.device)]).out)

    def change(self, power: str) -> str:
        """ "came on", "went off" or "" for the TV's power now: "on", "standby" or a transition, "" for no answer."""
        if power:
            self.silent = 0
            now = "on" if power == "on" else "off"
        else:
            self.silent += 1
            if self.silent < SILENT_POLLS:
                return ""
            now = "off"
        before, self.last = self.last, now
        if before is None or before == now:
            return ""
        return "came on" if now == "on" else "went off"

    def restart_picture(self) -> str:
        output = display.read(self.run).get(self.adapter.name)
        if output is None or not output.enabled:
            return f"no enabled output {self.adapter.name} in kscreen-doctor"
        other = display.other_rate(output)
        if other is None:
            return f"{self.adapter.name} has no other refresh rate at this size"
        self.run(display.set_mode(output.name, other.id))
        self.sleep(HOLD_S)
        self.run(display.set_mode(output.name, output.current))
        return f"restarted the picture on {output.name}: {other.rate:g} Hz for {HOLD_S} s, then mode {output.current}"

    def step(self) -> None:
        change = self.change(self.tv_power())
        if change == "went off" and self.pause:
            self.paused = media.pause_all(self.run)
            log(f"the TV is off; paused {', '.join(self.paused) or 'nothing (nothing played)'}")
        elif change == "came on":
            if self.restart:
                self.sleep(SETTLE_S)
                log(f"the TV is on again; {self.restart_picture()}")
            if self.pause and self.paused:
                media.resume(self.run, self.paused)
                log(f"the TV is on again; continued {', '.join(self.paused)}")
                self.paused = []

    def loop(self) -> int:
        self.adapter = self.find_adapter()
        if self.adapter is None:
            log("no CEC adapter (/dev/cec*); nothing to watch")
            return 1
        jobs = [job for job, on in (("restart the picture", self.restart), ("pause media", self.pause)) if on]
        log(f"watching the TV on {self.adapter.device} ({self.adapter.name}): {' and '.join(jobs) or 'nothing to do'}")
        while True:
            self.step()
            self.sleep(POLL_S)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="hdmi_cec.watcher")
    parser.add_argument("--restart-picture", action="store_true", help="restart the picture when the TV comes on")
    parser.add_argument("--pause-media", action="store_true", help="pause media players while the TV is off")
    args = parser.parse_args(argv)
    return Watcher(restart_picture=args.restart_picture, pause_media=args.pause_media).loop()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
