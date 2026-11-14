# SPDX-License-Identifier: GPL-3.0-or-later
"""Fix's plan (pip into the app's venv, Homebrew, rpm-ostree, else the manual) and the weekly notification."""

from __future__ import annotations

import datetime
import subprocess

from nexus_deps import CATALOG
from nexus_deps.bazzite import BazziteState, Deployment
from nexus_deps.dependencies import (
    CheckResult, DependencyStatus, EnvironmentVersion, ToolStatus, Vulnerability, load_catalog, load_tools,
)
from nexus_deps.fixes import Plan, Step, notify, plan, problems, reminder_text, requirement
from nexus_deps.system import Source, Update

VENV = "/home/u/.local/share/bc250-bazzite-suite/venv"
OWN = "/home/u/.local/share/bc250-sftp-tools/venv"


def dependencies():
    return {d.name: d for d in load_catalog(CATALOG)}


def tools():
    return {t.name: t for t in load_tools(CATALOG)}


def which_all(name):
    return f"/usr/bin/{name}" if name in ("brew", "rpm-ostree", "notify-send") else None


def no_brew(name):
    return None if name == "brew" else which_all(name)


def result(packages=(), tool_results=(), installed=("check", "cores", "sftp", "portal")):
    return CheckResult(list(packages), list(tool_results), frozenset(installed))


def test_nothing_broken_needs_no_fix():
    pyqt = dependencies()["PyQt6"]
    fine = DependencyStatus(pyqt, (EnvironmentVersion(VENV, ("portal", "check"), "6.11.0"),))
    found = ToolStatus(tools()["stress-ng"], "/usr/bin/stress-ng")
    assert not plan(result([fine], [found]), which_all)
    assert problems(result([fine], [found])) == []


def test_missing_and_outdated_packages_go_into_their_own_venv():
    deps = dependencies()
    paramiko = deps["paramiko"]
    pyqt = deps["PyQt6"]
    vuln = Vulnerability("CVE-1", fixed="5.0.1")
    statuses = [
        DependencyStatus(pyqt, (EnvironmentVersion(VENV, ("portal", "check"), ""),)),           # missing
        DependencyStatus(paramiko, (EnvironmentVersion(OWN, ("sftp",), "5.0.0", vulnerabilities=(vuln,)),)),
    ]
    steps = plan(result(statuses), which_all).steps
    assert [step.kind for step in steps] == ["pip", "pip"]
    assert steps[0].command[:6] == (f"{VENV}/bin/python", "-m", "pip", "install", "--disable-pip-version-check",
                                    "--upgrade")
    assert steps[0].command[6:] == ("PyQt6>=6.11,<7",)                  # the apps' one specifier, once
    assert steps[1].command[6:] == (requirement(statuses[1], statuses[1].environments[0]),)
    assert steps[1].command[6].startswith("paramiko") and steps[1].command[6].endswith(",>=5.0.1")
    assert not any(step.restart for step in steps)


def test_a_missing_required_tool_comes_from_homebrew_first_then_rpm_ostree():
    t = tools()
    missing = [ToolStatus(t["stress-ng"]), ToolStatus(t["setpci"])]             # both required by Cores Bisect
    steps = plan(result(tool_results=missing), which_all).steps
    assert [(s.kind, s.command) for s in steps] == [
        ("brew", ("/usr/bin/brew", "install", "stress-ng")),
        ("rpm-ostree", ("rpm-ostree", "install", "--idempotent", "--allow-inactive", "pciutils"))]
    assert steps[1].restart and not steps[0].restart
    without_brew = plan(result(tool_results=missing), no_brew)
    assert [s.command[-2:] for s in without_brew.steps] == [("stress-ng", "pciutils")] and without_brew.restart


def test_optional_and_unfixable_tools_stay_out():
    t = tools()
    optional = ToolStatus(t["stress-ng"])                                         # optional for check alone
    assert not plan(result(tool_results=[optional], installed=("check",)), which_all)
    governor = ToolStatus(t["cyan-skillfish-governor-smu"])          # required by GPU Manager; no brew, no rpm
    fixed = plan(result(tool_results=[governor], installed=("gpu",)), which_all)
    assert fixed.manual == ("cyan-skillfish-governor-smu",) and not fixed


def test_every_tool_names_at_most_one_formula_and_package():
    for tool in load_tools(CATALOG):
        assert " " not in tool.brew and " " not in tool.rpm, tool.name
    named = {name for name, tool in tools().items() if tool.rpm}
    assert {"stress-ng", "setpci", "smartctl", "vkmark", "SDL3"} <= named
    assert not {"Steam", "ujust", "cecd", "FFmpeg", "cyan-skillfish-governor-smu"} & named


def test_the_reminder_says_what_needs_the_user():
    t = tools()
    waiting = BazziteState(Deployment("44.1", 1, True, False), Deployment("44.2", 2, False, True), "",
                           datetime.datetime.now().astimezone())
    quiet = BazziteState(waiting.running, None, "", waiting.updater_last)
    assert reminder_text(quiet, result()).text == ""
    note = reminder_text(quiet, result(tool_results=[ToolStatus(t["setpci"])]), which_all)
    assert note.text == "Tools an installed app needs: setpci." and list(note.actions) == ["fix", "open"]
    note = reminder_text(waiting, None)                                          # the check failed: Bazzite alone
    assert note.text.startswith("Bazzite 44.2 waits for a reboot") and list(note.actions) == ["open"]


class Run:
    def __init__(self, stdout="", code=0):
        self.calls, self.stdout, self.code = [], stdout, code

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        return subprocess.CompletedProcess(argv, self.code, self.stdout, "")


def test_the_notification_waits_for_a_button():
    run = Run("fix\n")
    assert notify("Nexus Deps", "text", "/icon.webp", {"fix": "Fix…", "open": "Open"}, run, which_all) == "fix"
    assert run.calls == [["/usr/bin/notify-send", "--app-name", "Nexus Deps", "--icon", "/icon.webp", "--wait",
                          "--action=fix=Fix…", "--action=open=Open", "Nexus Deps", "text"]]
    assert notify("Nexus Deps", "text", "/i", {"open": "Open"}, Run(""), which_all) == ""        # closed
    old = Run(code=1)                                     # a notify-send without --action: the text alone
    assert notify("Nexus Deps", "text", "/i", {"open": "Open"}, old, which_all) == ""
    assert old.calls[1] == ["/usr/bin/notify-send", "--app-name", "Nexus Deps", "--icon", "/i", "Nexus Deps", "text"]
    assert notify("Nexus Deps", "", "/i", None, Run(), which_all) is None                       # nothing to say
    assert notify("Nexus Deps", "text", "/i", None, Run(), lambda name: None) is None           # no notify-send


def test_remind_opens_the_app_on_a_click(monkeypatch):
    import nexus_deps.__main__ as entry
    started = []
    waiting = BazziteState(Deployment("44.1", 1, True, False), Deployment("44.2", 2, False, True), "",
                           datetime.datetime.now().astimezone())
    monkeypatch.setattr(entry, "check_all", lambda *args: result())
    monkeypatch.setattr(entry, "read_state", lambda: waiting)
    monkeypatch.setattr(entry, "read_sources", lambda: ())
    monkeypatch.setattr(entry, "read_upstreams", lambda section: ())         # GitHub is not asked from a test
    monkeypatch.setattr(entry, "notify", lambda title, text, icon, actions: "open")
    monkeypatch.setattr(entry.subprocess, "Popen", lambda argv, **kw: started.append(argv))
    monkeypatch.setattr("sys.argv", ["nexus_deps", "--remind"])
    assert entry.main() == 0
    assert len(started) == 1 and started[0][0].endswith("dev/deps/run.sh")
    assert started[0][1:] == ["--suite", "bc250-bazzite"]
    monkeypatch.setattr(entry, "notify", lambda *args: "fix")
    started.clear()
    assert entry.main() == 0 and started[0][-1] == "--fix"


def test_an_empty_plan_is_false():
    assert not Plan() and not Plan(manual=("Steam",))


def test_the_machines_updates_alone_make_a_notification_with_fix():
    """The hourly timer's sources are Nexus Deps' since 09-11-2026: Homebrew's updates alone are worth a word."""
    quiet = BazziteState(Deployment("44.1", 1, True, False), None, "", datetime.datetime.now().astimezone())
    brew = Source("brew", "Homebrew", (Update("node", "26.13.0_1", "26.13.0_2"), Update("lz4", "1.10.0", "1.11.0")),
                  step=Step("brew", "2 Homebrew update(s)", ("brew", "upgrade")))
    current = Source("flatpak", "Flatpak")
    note = reminder_text(quiet, result(), which_all, (brew, current))
    assert note.text == "Updates: Homebrew (2)." and list(note.actions) == ["fix", "open"]
    failed = Source("rust", "Rust", error="offline")
    assert reminder_text(quiet, result(), which_all, (current, failed)).text == ""
    venv = Source("venv", "Python venv (.venv-linux)", note="The venv was made with Python 3.14 and runs 3.15 now.")
    assert reminder_text(quiet, result(), which_all, (venv,)).text == venv.note
