# SPDX-License-Identifier: GPL-3.0-or-later
"""Switching an idle controller off (owner, 23-10-2026): nothing on Linux does it, as a PS5 does, and a controller
left on over Bluetooth drains its battery in a few hours. A user service (python -m usb_hdcontrol --idle-watch,
installed by install.sh) reads the input reports of every controller on Bluetooth, each with its own wait, and,
after the minutes chosen in
the window without a button, a stick moved off its middle or a trigger pulled, ends its Bluetooth connection as Turn
off does, and says so in a desktop notification (owner, 23-10-2026) and the journal. On the USB cable a controller is
left alone: the cable powers it. The motion sensors do not count, so a controller lying on a table is idle.

While a game Steam started runs, every controller is left on (owner, 24-10-2026): a controller switched off during
a game is not picked up again by every game when it comes back (RPCS3's build of the time lost it for the rest of
the session), and the wait starts over when the game ends. Steam gives a game's process SteamGameId in its
environment (the suite's run wrappers read it too), which /proc shows for the user's own processes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from . import controller, inputs

CHOICES = (0, 10, 30, 60)           # minutes, as a PS5 offers them; 0 is Off
DEFAULT_MINUTES = 10
STICK = 0.25                        # off the middle by more than this is a stick in use, not its drift
TRIGGER = 0.1
NOTIFY_TIMEOUT = 10
PERIOD = 0.2                        # the kernel keeps 64 reports, about 0.25 s over Bluetooth: none is missed
SAVE = 5.0                          # the last-used times go to STATE at most this often
LOOK = 2.0                          # how often /sys is searched for controllers, and the pause while none is watched
GAME_MARK = b"SteamGameId="         # in the environment of a process Steam started as a game


def active(reading: inputs.Reading) -> bool:
    return (bool(reading.pressed) or any(abs(value) > STICK for value in reading.sticks)
            or any(value > TRIGGER for value in reading.triggers))


def state_path() -> Path:
    """Where the service keeps when each controller was last used, for the window's countdown: in the session's
    runtime folder, in memory and gone at logout."""
    return Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}") / "bc250-usb-hdcontrol-idle.json"


def read_state(path: Path) -> dict[str, float]:
    """Node -> when it was last used (time.monotonic(), the same clock in every process); {} without the
    service."""
    try:
        data = json.loads(path.read_text())
        return {str(node): float(last) for node, last in data.get("last_used", {}).items()}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}


def game_running(proc: Path = controller.PROC) -> bool:
    """Whether a game Steam started runs: a process (the user's own, which /proc lets it read) with SteamGameId in
    its environment. Steam's own processes do not have it."""
    for process in proc.glob("[0-9]*"):
        try:
            if GAME_MARK in (process / "environ").read_bytes():
                return True
        except OSError:
            continue
    return False


def notify(summary: str, body: str, run=subprocess.run, which=shutil.which) -> bool:
    """A desktop notification through notify-send, as the Dependency Checker sends its reminder."""
    from . import APP_ID, APP_NAME, ROOT
    exe = which("notify-send")
    if not exe:
        return False
    try:
        run([exe, "--app-name", APP_NAME, "--icon", str(ROOT / "images" / f"{APP_ID}-128.png"), summary, body],
            timeout=NOTIFY_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


class Reports:
    """A hidraw node read without blocking: whether any report waiting shows the controller in use."""

    def __init__(self, path: Path):
        self.fd = os.open(str(path), os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)

    def in_use(self) -> bool:
        used = False
        while True:
            try:
                data = os.read(self.fd, 128)
            except BlockingIOError:
                return used
            if not data:
                return used
            reading = inputs.parse(data)
            used = used or (reading is not None and active(reading))

    def close(self) -> None:
        if self.fd >= 0:
            fd, self.fd = self.fd, -1
            os.close(fd)


def label(found: controller.Controller) -> str:
    """The controller's name with the player number its lights show, so that with several connected the
    notification says which one: "DualSense Edge (player 2)"."""
    number = controller.player_number(found)
    return f"{found.name} (player {number})" if number else found.name


class Watcher:
    """The controllers on Bluetooth and when each was last used. step() is one look: call it every PERIOD."""

    def __init__(self, minutes: Callable[[], int], find=controller.find, open_reports=Reports,
                 disconnect=controller.disconnect_bluetooth, clock=time.monotonic, log=print, notify=notify,
                 dev: Path = controller.DEV, state: Path | None = None, game=game_running):
        self.minutes, self.find, self.open_reports = minutes, find, open_reports
        self.disconnect, self.clock, self.log, self.notify, self.dev = disconnect, clock, log, notify, dev
        self.game = game
        self.in_game = False                                    # a game Steam started runs: nothing goes off
        self.watched: dict[str, tuple[object, float]] = {}      # node -> (its reports, last used)
        self.present: dict[str, controller.Controller] = {}
        self.looked = float("-inf")
        self.state, self.saved, self.saved_at = state, None, float("-inf")

    def step(self) -> None:
        now = self.clock()
        limit = self.minutes() * 60
        if not limit:                       # Off: nothing is read
            self.close()
            self._save(now)
            return
        if now - self.looked >= LOOK:
            self.looked = now
            self.present = {found.node: found for found in self.find() if found.bus == "bluetooth"}
            for node in list(self.watched):
                if node not in self.present:
                    self.watched.pop(node)[0].close()
            in_game = bool(self.present) and self.game()        # looked for only while a controller is there
            if in_game != self.in_game:
                self.log("A game started from Steam runs: the controllers stay on." if in_game else
                         "The game ended: a controller unused from now on is switched off after the wait.")
            self.in_game = in_game
        for node, found in self.present.items():
            if node not in self.watched:
                try:
                    self.watched[node] = (self.open_reports(found.path(self.dev)), now)
                except OSError:
                    continue
            reports, last = self.watched[node]
            try:
                if reports.in_use() or self.in_game:                # a game runs: as good as in use
                    last = now
            except OSError:                 # it left between the look in /sys and the read
                self.watched.pop(node)[0].close()
                self.looked = float("-inf")
                continue
            if limit and now - last >= limit:
                name = label(found)             # before it goes: its player lights go with it
                address = controller.bluetooth_address(found)
                problem = self.disconnect(address) if address else "its address is not known."
                minutes = self.minutes()
                self.log(f"{name} on Bluetooth unused for {minutes} minutes: "
                         + (f"not switched off, {problem}" if problem else "switched off."))
                if problem:
                    self.notify(f"{name} not switched off", f"It was not used for {minutes} minutes, but "
                                f"switching it off failed: {problem} Hold the PS button for 10 seconds to switch it "
                                "off.")
                else:
                    self.notify(f"{name} switched off", f"Not used for {minutes} minutes. Press the PS button "
                                "to switch it on again.")
                last = now                  # if it stayed, the next try comes after another full wait
            self.watched[node] = (reports, last)
        self._save(now)

    def _save(self, now: float) -> None:
        """The last-used times for the window: when a controller came or went at once, else at most every SAVE."""
        if self.state is None:
            return
        last_used = {node: last for node, (_reports, last) in self.watched.items()}
        if last_used == self.saved or (self.saved is not None and set(last_used) == set(self.saved)
                                       and now - self.saved_at < SAVE):
            return
        try:
            temporary = self.state.with_suffix(".tmp")
            temporary.write_text(json.dumps({"last_used": last_used}))
            temporary.replace(self.state)
        except OSError:
            return
        self.saved, self.saved_at = last_used, now

    def close(self) -> None:
        for reports, _last in self.watched.values():
            reports.close()
        self.watched.clear()


def minutes_setting() -> Callable[[], int]:
    """The minutes chosen in the window, read again each time: the window may change them while the service runs."""
    from . import INFO
    from .settings import ControlSettings
    settings = ControlSettings(INFO)

    def minutes() -> int:
        settings.sync()
        value = settings.get("idle_minutes")
        return value if value in CHOICES else DEFAULT_MINUTES
    return minutes


def run() -> int:
    watcher = Watcher(minutes_setting(), log=lambda text: print(text, file=sys.stderr, flush=True),
                      state=state_path())
    try:
        while True:
            watcher.step()
            time.sleep(PERIOD if watcher.watched else LOOK)
    except KeyboardInterrupt:
        return 0
    finally:
        watcher.close()
        state_path().unlink(missing_ok=True)
