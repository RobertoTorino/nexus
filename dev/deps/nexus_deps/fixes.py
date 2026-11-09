# SPDX-License-Identifier: GPL-3.0-or-later
"""What Fix does about a check (owner, 07-11-2026: a tool to fix missing dependencies), and the hourly reminder.

plan() turns a CheckResult into steps, each one command the window shows before it runs anything:
  * pip: a Python package that is missing, at a version an app does not accept, or that must be updated (an app
    wants a newer one, or a newer release fixes a known vulnerability), installed into the app's own venv with the
    specifiers of the apps that run in it. One step per venv.
  * brew: a missing tool an installed app needs, when Homebrew has it (the catalog's brew). No restart.
  * rpm-ostree: a missing tool Homebrew lacks, layered as the Fedora package (the catalog's rpm). It changes the
    Bazzite image and is active after a restart; the app says so and gives the command, it never restarts.
A tool with neither (ujust, Steam, a suite app's own) is left to the app's manual. Optional tools are not part of
Fix: the apps work without them. The machine's own updates (system.py: Bazzite's image, the Flatpaks, Homebrew,
Rust, the development venv) bring a step each; the window adds them to this plan.

reminder_text() is the hourly notification (--remind, from the systemd user timer install.sh writes): Bazzite's
update state, the machine's updates and what is missing or outdated. notify() shows it with buttons and says which
one was clicked."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .bazzite import BazziteState, reminder
from .dependencies import CheckResult, DependencyStatus, EnvironmentVersion, release, tool_need

if TYPE_CHECKING:
    from .system import Source

Run = Callable[..., subprocess.CompletedProcess]
Which = Callable[[str], "str | None"]

RESTART = "systemctl reboot"
NOTIFY_WAIT = 3000                       # a notification nobody answers lets the service end before the next hour


@dataclass(frozen=True)
class Step:
    kind: str                            # "pip", "brew", "rpm-ostree", "flatpak" or "rustup"
    title: str                           # what it does, for the confirmation and the log
    command: tuple[str, ...]
    restart: bool = False                # active only after a restart (rpm-ostree)


@dataclass(frozen=True)
class Plan:
    steps: tuple[Step, ...] = ()
    manual: tuple[str, ...] = ()         # missing tools Fix cannot install: the app's manual says how

    @property
    def restart(self) -> bool:
        return any(step.restart for step in self.steps)

    def __bool__(self) -> bool:
        return bool(self.steps)


def _broken(env: EnvironmentVersion) -> bool:
    return not env.version or bool(env.unmet) or env.needs_update


def requirement(status: DependencyStatus, env: EnvironmentVersion) -> str:
    """The pip requirement for one venv: the specifiers of the apps that run in it, and the release that fixes a
    known vulnerability of the installed version."""
    wanted = {source.owner: source.specifier for source in status.dependency.sources}
    specifiers = list(dict.fromkeys(wanted[owner] for owner in env.owners if wanted.get(owner)))
    if env.fixes:
        specifiers.append(">=" + max((vuln.fixed for vuln in env.fixes), key=release))
    return status.dependency.name + ",".join(specifiers)


def _venv_python(environment: str) -> str:
    return str(Path(environment) / "bin" / "python")


def plan(result: CheckResult, which: Which = shutil.which) -> Plan:
    per_venv: dict[str, list[str]] = {}
    names: dict[str, list[str]] = {}
    for status in result.packages:
        for env in status.environments:
            if _broken(env):
                per_venv.setdefault(env.environment, []).append(requirement(status, env))
                names.setdefault(env.environment, []).append(status.dependency.name)
    steps = [Step("pip", f"{', '.join(names[venv])} into {venv}",
                  (_venv_python(venv), "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", *reqs))
             for venv, reqs in per_venv.items()]

    brew, rpm, manual = [], [], []
    for item in result.tools:
        if item.path or item.note or tool_need(item.tool, result.installed) != "required":
            continue
        if item.tool.brew and which("brew"):
            brew.append(item.tool)
        elif item.tool.rpm and which("rpm-ostree"):
            rpm.append(item.tool)
        else:
            manual.append(item.tool.name)
    if brew:
        steps.append(Step("brew", ", ".join(tool.name for tool in brew) + " with Homebrew",
                          (which("brew") or "brew", "install", *dict.fromkeys(tool.brew for tool in brew))))
    if rpm:
        steps.append(Step("rpm-ostree", ", ".join(tool.name for tool in rpm) + " into the Bazzite image",
                          ("rpm-ostree", "install", "--idempotent", "--allow-inactive",
                           *dict.fromkeys(tool.rpm for tool in rpm)), restart=True))
    return Plan(tuple(steps), tuple(manual))


def problems(result: CheckResult) -> list[str]:
    """What the window counts as missing or to update, in a line each: the reminder's text."""
    lines = []
    missing = sorted({status.dependency.name for status in result.packages
                      if any(not env.version or env.unmet for env in status.environments)})
    update = sorted({status.dependency.name for status in result.packages if status.needs_update} - set(missing))
    tools = [item.tool.name for item in result.tools
             if not item.path and not item.note and tool_need(item.tool, result.installed) == "required"]
    if missing:
        lines.append(f"Python packages missing or at a wrong version: {', '.join(missing)}.")
    if update:
        lines.append(f"Python packages to update: {', '.join(update)}.")
    if tools:
        lines.append(f"Tools an installed app needs: {', '.join(tools)}.")
    return lines


@dataclass(frozen=True)
class Reminder:
    text: str = ""
    actions: dict[str, str] = field(default_factory=dict)    # the notification's buttons: key -> label


def system_lines(sources: tuple[Source, ...]) -> list[str]:
    """The machine's updates in the notification: which sources have them, how many, and what to know beside."""
    outdated = ", ".join(f"{source.name} ({len(source.updates)})" for source in sources if source.outdated)
    lines = [f"Updates: {outdated}."] if outdated else []
    lines.extend(source.note for source in sources if source.note)
    return lines


def reminder_text(state: BazziteState, result: CheckResult | None, which: Which = shutil.which,
                  sources: tuple[Source, ...] = ()) -> Reminder:
    """The hourly notification: Bazzite's update state, the machine's updates (*sources*) and the dependencies; ""
    when nothing needs the user."""
    lines = [line for line in (reminder(state),) if line]
    lines.extend(system_lines(sources))
    fixable = any(source.outdated and source.step for source in sources)
    if result is not None:
        lines.extend(problems(result))
        fixable = fixable or bool(plan(result, which))
    if not lines:
        return Reminder()
    actions = {"fix": "Fix…"} if fixable else {}
    actions["open"] = "Open Nexus Deps"
    return Reminder(" ".join(lines), actions)


def notify(title: str, text: str, icon: str, actions: dict[str, str] | None = None, run: Run = subprocess.run,
           which: Which = shutil.which) -> str | None:
    """A desktop notification. With *actions* it waits for a click and returns that button's key ("" when it was
    closed without one); None when no notification could be shown."""
    exe = which("notify-send")
    if not exe or not text:
        return None
    argv = [exe, "--app-name", "Nexus Deps", "--icon", icon]
    if actions:
        argv.append("--wait")
        argv.extend(f"--action={key}={label}" for key, label in actions.items())
    argv += [title, text]
    try:
        done = run(argv, capture_output=True, text=True, timeout=NOTIFY_WAIT if actions else 20)
    except subprocess.TimeoutExpired:
        return ""
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0 and actions:              # a notify-send without actions: show the text alone
        try:
            run([exe, "--app-name", "Nexus Deps", "--icon", icon, title, text], timeout=20)
        except (OSError, subprocess.SubprocessError):
            return None
        return ""
    answer = (done.stdout or "").strip()
    return answer if answer in (actions or {}) else ""
