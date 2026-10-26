# SPDX-License-Identifier: GPL-3.0-or-later
"""Bazzite's update state, read only: the image the board runs, an update that waits for a reboot, and the last run
of Bazzite's updater (uupd, a nightly systemd timer that updates the image, Flatpaks, Homebrew and distroboxes).

Updating is Bazzite's: the suite answers for its own apps, and shows this so a waiting update is not missed (owner's
decision, 15-10-2026). Nothing here needs root or the network: `rpm-ostree status --json` lists the deployments, the
first one being what the next boot starts, and `systemctl show` tells when the timer last fired and how the service
ended. reminder() is the weekly desktop notification (`--bazzite-reminder`, from a systemd user timer the installer
writes): it says something only when something needs the user."""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

TIMEOUT = 20
STALE_DAYS = 8                          # uupd runs nightly: a week without a run means it is not running
UPDATER = "uupd"
Run = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class Deployment:
    version: str
    timestamp: int                      # the image's build time, seconds since the epoch
    booted: bool
    staged: bool


@dataclass(frozen=True)
class BazziteState:
    running: Deployment | None = None
    next_boot: Deployment | None = None     # what the next boot starts, when it is not the running one
    image: str = ""                         # ghcr.io/ublue-os/bazzite:stable, without the transport prefix
    updater_last: datetime.datetime | None = None
    updater_failed: bool = False
    error: str = ""                         # why nothing could be read (not an rpm-ostree system, ...)

    @property
    def update_waiting(self) -> bool:
        return (self.running is not None and self.next_boot is not None
                and self.next_boot.timestamp > self.running.timestamp)

    @property
    def rollback_waiting(self) -> bool:
        return (self.running is not None and self.next_boot is not None
                and self.next_boot.timestamp <= self.running.timestamp)

    def updater_stale(self, now: datetime.datetime | None = None) -> bool:
        now = now or datetime.datetime.now().astimezone()
        return self.updater_last is None or now - self.updater_last > datetime.timedelta(days=STALE_DAYS)


def _deployment(entry: dict) -> Deployment:
    return Deployment(str(entry.get("version") or entry.get("checksum", "")[:12]), int(entry.get("timestamp") or 0),
                      bool(entry.get("booted")), bool(entry.get("staged")))


def parse_status(text: str) -> tuple[Deployment | None, Deployment | None, str]:
    """(the running deployment, the next boot's when it differs, the image) from `rpm-ostree status --json`."""
    deployments = json.loads(text).get("deployments") or []
    running = next((_deployment(d) for d in deployments if d.get("booted")), None)
    first = deployments[0] if deployments else None
    next_boot = _deployment(first) if first is not None and not first.get("booted") else None
    reference = next((d.get("container-image-reference") or "" for d in deployments if d.get("booted")), "")
    return running, next_boot, reference.split("docker://", 1)[-1]


def parse_systemd_time(value: str) -> datetime.datetime | None:
    """systemctl's "Thu 2026-10-15 04:06:15 CEST" as an aware datetime; None for an empty or unknown value."""
    parts = value.split()
    if len(parts) < 3:
        return None
    try:
        moment = datetime.datetime.strptime(f"{parts[1]} {parts[2]}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return moment.astimezone()          # systemctl prints the local time


def _show(run: Run, unit: str, prop: str) -> str:
    done = run(["systemctl", "show", unit, "-p", prop, "--value"], capture_output=True, text=True, timeout=TIMEOUT)
    return done.stdout.strip() if done.returncode == 0 else ""


def read_state(run: Run = subprocess.run, which: Callable[[str], str | None] = shutil.which) -> BazziteState:
    if which("rpm-ostree") is None:
        return BazziteState(error="This system has no rpm-ostree: it is not Bazzite, or not an image-based one.")
    try:
        done = run(["rpm-ostree", "status", "--json"], capture_output=True, text=True, timeout=TIMEOUT)
        if done.returncode != 0:
            return BazziteState(error=f"rpm-ostree status failed: {(done.stderr or done.stdout).strip()[-200:]}")
        running, next_boot, image = parse_status(done.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return BazziteState(error=f"rpm-ostree status could not be read: {exc}")
    last, failed = None, False
    if which("systemctl") is not None:
        try:
            last = parse_systemd_time(_show(run, f"{UPDATER}.timer", "LastTriggerUSec"))
            failed = _show(run, f"{UPDATER}.service", "Result") not in ("", "success")
        except (OSError, subprocess.SubprocessError):
            pass
    return BazziteState(running, next_boot, image, last, failed)


def build_date(deployment: Deployment) -> str:
    return datetime.datetime.fromtimestamp(deployment.timestamp).strftime("%d-%m-%Y") if deployment.timestamp else "?"


def describe(state: BazziteState) -> tuple[str, str]:
    """(a status word for the card: "ok", "warn" or "neutral", the text in plain sentences)."""
    if state.error or state.running is None:
        return "neutral", state.error or "The running image could not be found."
    text = f"Bazzite {state.running.version} (built {build_date(state.running)}) is running"
    text += f", from {state.image}." if state.image else "."
    kind = "ok"
    if state.update_waiting:
        text += (f" Bazzite {state.next_boot.version} (built {build_date(state.next_boot)}) is installed and waits for "
                 "a reboot: restart the board to use it.")
        kind = "warn"
    elif state.rollback_waiting:
        text += (f" The next boot starts the older {state.next_boot.version} (a rollback); restart to go back to it, "
                 "or keep running this one.")
        kind = "warn"
    else:
        text += " No update waits for a reboot."
    if state.updater_last is None:
        text += f" Bazzite's updater ({UPDATER}) has not run yet."
        kind = "warn"
    else:
        text += f" Bazzite's updater ({UPDATER}) last ran {state.updater_last.strftime('%d-%m-%Y %H:%M')}"
        text += ", and failed." if state.updater_failed else "."
        if state.updater_failed or state.updater_stale():
            kind = "warn"
        if state.updater_stale():
            text += f" That is more than {STALE_DAYS - 1} days ago: it normally runs every night."
    text += " It updates the image, Flatpaks, Homebrew and distroboxes by itself; this app only reads its state."
    return kind, text


def reminder(state: BazziteState, now: datetime.datetime | None = None) -> str:
    """The weekly notification's text, or "" when nothing needs the user."""
    if state.error or state.running is None:
        return ""
    lines = []
    if state.update_waiting:
        lines.append(f"Bazzite {state.next_boot.version} waits for a reboot: restart the board to use it.")
    if state.updater_failed:
        lines.append(f"Bazzite's updater ({UPDATER}) failed on its last run.")
    elif state.updater_stale(now):
        lines.append(f"Bazzite's updater ({UPDATER}) has not run for over a week.")
    return " ".join(lines)


def notify(text: str, icon: str, run: Run = subprocess.run, which: Callable[[str], str | None] = shutil.which) -> bool:
    exe = which("notify-send")
    if not exe or not text:
        return False
    try:
        run([exe, "--app-name", "Dependency Checker", "--icon", icon, "Bazzite update", text], timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return False
    return True
