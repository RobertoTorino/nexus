# SPDX-License-Identifier: GPL-3.0-or-later
"""Bazzite's update state from rpm-ostree's and systemd's answers (recorded on the owner's board, 15-10-2026, and
the other states a board can be in), what the card says, and when the weekly reminder speaks."""

from __future__ import annotations

import datetime
import json
import subprocess

from package_checker import bazzite
from package_checker.bazzite import BazziteState, Deployment

IMAGE = "ostree-image-signed:docker://ghcr.io/ublue-os/bazzite:stable"
RUNNING = {"booted": True, "staged": False, "pinned": False, "version": "44.20261012.1", "timestamp": 1791962757,
           "container-image-reference": IMAGE, "checksum": "550d380b9f27"}
PREVIOUS = {"booted": False, "staged": False, "pinned": False, "version": "44.20261006.1", "timestamp": 1791338629,
            "container-image-reference": IMAGE, "checksum": "b07a3ac5e105"}
NEWER = {"booted": False, "staged": True, "pinned": False, "version": "44.20261019.0", "timestamp": 1792567557,
         "container-image-reference": IMAGE, "checksum": "0123456789ab"}
NOW = datetime.datetime(2026, 10, 19, 10, 0, tzinfo=datetime.timezone.utc)
LAST_RUN = "Thu 2026-10-15 04:06:15 CEST"


def status(*deployments: dict) -> str:
    return json.dumps({"cached-update": None, "deployments": list(deployments), "transaction": None})


def fake_run(rpm: str, timer: str = LAST_RUN, result: str = "success", rpm_code: int = 0):
    """subprocess.run for rpm-ostree and systemctl, answering what a board would; records the commands."""
    calls: list[list[str]] = []

    def run(argv, **kwargs):
        calls.append(argv)
        if argv[0] == "rpm-ostree":
            return subprocess.CompletedProcess(argv, rpm_code, rpm, "error: no daemon" if rpm_code else "")
        if argv[0] == "systemctl" and argv[2] == "uupd.timer":
            return subprocess.CompletedProcess(argv, 0, timer + "\n", "")
        if argv[0] == "systemctl" and argv[2] == "uupd.service":
            return subprocess.CompletedProcess(argv, 0, result + "\n", "")
        if argv[0].endswith("notify-send"):
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise AssertionError(argv)
    run.calls = calls
    return run


def which(name: str) -> str:
    return f"/usr/bin/{name}"


def test_the_owners_board_up_to_date():
    """The running image first, the previous one kept for a rollback: nothing waits."""
    state = bazzite.read_state(fake_run(status(RUNNING, PREVIOUS)), which)
    assert state.running.version == "44.20261012.1" and state.next_boot is None
    assert state.image == "ghcr.io/ublue-os/bazzite:stable"
    assert state.updater_last.strftime("%Y-%m-%d %H:%M") == "2026-10-15 04:06" and not state.updater_failed
    kind, text = bazzite.describe(state)
    assert "Bazzite 44.20261012.1 (built " in text and "No update waits for a reboot." in text
    assert "last ran 15-10-2026 04:06." in text
    assert bazzite.reminder(state, NOW) == ""


def test_an_update_waits_for_a_reboot():
    state = bazzite.read_state(fake_run(status(NEWER, RUNNING, PREVIOUS)), which)
    assert state.update_waiting and not state.rollback_waiting and state.next_boot.staged
    kind, text = bazzite.describe(state)
    assert kind == "warn" and "Bazzite 44.20261019.0" in text and "waits for a reboot" in text
    assert bazzite.reminder(state, NOW) == "Bazzite 44.20261019.0 waits for a reboot: restart the board to use it."


def test_a_rollback_is_not_an_update():
    state = bazzite.read_state(fake_run(status(PREVIOUS, RUNNING)), which)
    assert state.rollback_waiting and not state.update_waiting
    assert "a rollback" in bazzite.describe(state)[1]
    assert bazzite.reminder(state, NOW) == ""


def test_the_updater_failed_or_stopped_running():
    failed = bazzite.read_state(fake_run(status(RUNNING), result="exit-code"), which)
    assert failed.updater_failed and bazzite.describe(failed)[0] == "warn"
    assert bazzite.reminder(failed, NOW) == "Bazzite's updater (uupd) failed on its last run."
    stale = bazzite.read_state(fake_run(status(RUNNING), timer="Mon 2026-10-05 04:06:15 CEST"), which)
    assert bazzite.reminder(stale, NOW) == "Bazzite's updater (uupd) has not run for over a week."
    never = bazzite.read_state(fake_run(status(RUNNING), timer="n/a"), which)
    assert never.updater_last is None and "has not run yet" in bazzite.describe(never)[1]


def test_not_bazzite_or_rpm_ostree_failing():
    none = bazzite.read_state(fake_run(""), lambda name: None)
    assert "no rpm-ostree" in none.error and bazzite.describe(none)[0] == "neutral"
    assert bazzite.reminder(none, NOW) == ""
    broken = bazzite.read_state(fake_run("", rpm_code=1), which)
    assert broken.error == "rpm-ostree status failed: error: no daemon"
    garbled = bazzite.read_state(fake_run("not json"), which)
    assert garbled.error.startswith("rpm-ostree status could not be read")


def test_only_reads():
    """rpm-ostree status and systemctl show: nothing that changes the system."""
    run = fake_run(status(NEWER, RUNNING))
    bazzite.read_state(run, which)
    assert [argv[:2] for argv in run.calls] == [["rpm-ostree", "status"], ["systemctl", "show"],
                                                ["systemctl", "show"]]


def test_the_notification():
    run = fake_run("")
    assert bazzite.notify("Bazzite 44.2 waits for a reboot.", "/icon.png", run, which)
    assert run.calls == [["/usr/bin/notify-send", "--app-name", "Dependency Checker", "--icon", "/icon.png",
                          "Bazzite update", "Bazzite 44.2 waits for a reboot."]]
    assert not bazzite.notify("", "/icon.png", run, which)                   # nothing to say: no notification
    assert not bazzite.notify("text", "/icon.png", run, lambda name: None)   # no notify-send


def test_the_reminder_entry_point(monkeypatch, capsys):
    import package_checker.__main__ as entry
    shown: list[str] = []
    waiting = BazziteState(Deployment("44.1", 1, True, False), Deployment("44.2", 2, False, True), "",
                           datetime.datetime.now().astimezone())
    monkeypatch.setattr(entry, "read_state", lambda: waiting)
    monkeypatch.setattr(entry, "notify", lambda text, icon: shown.append(text))
    monkeypatch.setattr("sys.argv", ["package_checker", "--bazzite-reminder"])
    assert entry.main() == 0
    assert shown == ["Bazzite 44.2 waits for a reboot: restart the board to use it."]
    monkeypatch.setattr(entry, "read_state", lambda: BazziteState(waiting.running, None, "", waiting.updater_last))
    shown.clear()
    assert entry.main() == 0 and shown == []
