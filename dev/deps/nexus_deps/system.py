# SPDX-License-Identifier: GPL-3.0-or-later
"""What has a newer version on this machine besides the suite's apps (owner, 09-11-2026: Nexus Deps picks up every
update system wide; it took over from tools/dev-updates.sh and its hourly timer): Bazzite's image, the Flatpaks,
Homebrew's formulae and casks, the Rust toolchain and the checkout's development venv (.venv-linux).

Each source is asked with its own tool, without root; a source whose tool is not on the machine is left out.
`brew update` fetches Homebrew's formulae first, else `brew outdated` only knows what the last fetch knew. A source
with updates has a Step, which Fix and the source's card run after asking: rpm-ostree upgrade (the new image is
used after a restart), flatpak update, brew upgrade, rustup update, and pip for the venv within what
requirements-dev.txt allows (it keeps MkDocs below 2 on purpose): what the requirements hold back is shown, not
updated. Bazzite's own updater (uupd) installs the image, the Flatpaks and Homebrew's packages every night; Fix only
does it sooner.

Every source says what its Update does and how to handle what goes wrong (about, behind the card's "i"); an update
that needs care says so on the card (note): a new major version, an image used after a restart. One that should not
be installed by a click has no step and says how instead (owner, 09-11-2026): a Bazzite image of a new Fedora
release changes the whole system (the kernel, Mesa, the system's Python), so it goes through `ujust update` after
reading its release notes."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from . import CHECKOUT
from .bazzite import parse_status
from .fixes import RESTART, Step

Run = Callable[..., subprocess.CompletedProcess]
Which = Callable[[str], "str | None"]

TIMEOUT = 300                           # brew update and pip ask the network; rpm-ostree fetches the repo metadata
BREW_HOME = "/home/linuxbrew/.linuxbrew/bin/brew"    # Bazzite's Homebrew: not on the PATH of a timer's service
VENV = ".venv-linux"
REQUIREMENTS = "requirements-dev.txt"
RELEASES = "https://github.com/ublue-os/bazzite/releases"
ROLLBACK = ("If the new image misbehaves, choose the previous one in the boot menu, or run <code>rpm-ostree rollback"
            f"</code> and restart (<code>{RESTART}</code>).")


def _major(version: str) -> str | None:
    """The first number of a version with a dot after it ("26" of "26.13.0_1"); None for a date or a hash."""
    found = re.match(r"\s*v?(\d+)\.", version)
    return found.group(1) if found else None


@dataclass(frozen=True)
class Update:
    name: str
    current: str = ""                   # "" when the source does not say (Flatpak) or the package is new (pip)
    latest: str = ""

    @property
    def major(self) -> bool:
        """A new major version ("26.13.0_1" → "27.0.0"): it may change how the thing behaves."""
        old, new = _major(self.current), _major(self.latest)
        return old is not None and new is not None and old != new


@dataclass(frozen=True)
class Source:
    key: str                            # "image", "flatpak", "brew", "rust" or "venv"
    name: str                           # the card's title
    updates: tuple[Update, ...] = ()
    held: tuple[Update, ...] = ()       # newer than the requirements allow (the venv): shown, not updated
    error: str = ""                     # why it could not be checked (offline, ...)
    step: Step | None = None            # what installs the updates; None when there are none
    note: str = ""                      # what needs care, on the card (a new major version, a restart, ...)
    about: str = ""                     # what Update does and how to handle it: rich text behind the card's "i"
    group: str = "system"               # "system": this machine's; "apps": what the suites' apps use (upstreams.py)
    detail: str = ""                    # a line beside the updates (the latest versions known)
    checked: bool = True                # False: nothing a program can ask; the card says how (about)
    known: tuple[tuple[str, str], ...] = ()  # the versions just read, remembered for the next look (Sony's)

    @property
    def outdated(self) -> bool:
        return bool(self.updates) and not self.error

    @property
    def manual(self) -> bool:
        """Updates no click installs: the card says how (about)."""
        return self.outdated and self.step is None


def majors(updates: tuple[Update, ...]) -> str:
    """The note for new major versions among *updates*, "" when there are none."""
    names = [f"{update.name} {_major(update.latest)}" for update in updates if update.major]
    if not names:
        return ""
    return (f"New major version{'s' if len(names) > 1 else ''}: {', '.join(names)}. A major version can change how "
            "it behaves or drop what was deprecated; try what uses it afterwards.")


def _notes(*notes: str) -> str:
    return " ".join(note for note in notes if note)


def _tail(done: subprocess.CompletedProcess) -> str:
    text = (done.stderr or done.stdout or "").strip().splitlines()
    return text[-1][-200:] if text else f"exit code {done.returncode}"


def find_brew(which: Which = shutil.which) -> str | None:
    return which("brew") or (BREW_HOME if Path(BREW_HOME).is_file() else None)


# --- Bazzite's image ------------------------------------------------------------------------------------------

def parse_image_check(text: str) -> str:
    """The version `rpm-ostree upgrade --check` offers ("AvailableUpdate:" ... "Version: 44.20261019.0 (...)"), or
    "" when it offers none."""
    if "AvailableUpdate" not in text:
        return ""
    found = re.search(r"^\s*Version:\s*(\S+)", text, re.MULTILINE)
    return found.group(1) if found else "(a new deployment)"


IMAGE_ABOUT = ("<p>Bazzite's image: the operating system, its kernel, Mesa and the system's Python, as one "
               "image. Bazzite's updater (uupd) installs a new one every night; <code>ujust update</code> in a terminal "
               "does it now, with the Flatpaks, Homebrew and distroboxes.</p>")


def running_version(run: Run) -> str:
    """The version of the image the machine runs, from `rpm-ostree status --json`; "" when it cannot be read."""
    try:
        done = run(["rpm-ostree", "status", "--json"], capture_output=True, text=True, timeout=TIMEOUT)
        running = parse_status(done.stdout)[0] if done.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return ""
    return running.version if running else ""


def check_image(run: Run) -> Source:
    name = "Bazzite image"
    about = IMAGE_ABOUT + f"<p>{ROLLBACK}</p>"
    done = run(["rpm-ostree", "upgrade", "--check"], capture_output=True, text=True, timeout=TIMEOUT)
    if done.returncode == 77:                                       # rpm-ostree's "no updates"
        return Source("image", name, about=about)
    if done.returncode != 0:
        return Source("image", name, error=f"rpm-ostree upgrade --check failed: {_tail(done)}", about=about)
    version = parse_image_check(done.stdout)
    if not version:
        return Source("image", name, about=about)
    current = running_version(run)
    update = Update("Bazzite", current, version)
    if update.major:
        # A new Fedora release: the whole system changes. Not by a click: the steps, in order.
        old, new = _major(current), _major(version)
        return Source("image", name, (update,), note=(
            f"Bazzite {version} moves from Fedora {old} to Fedora {new}: a system-wide change (the kernel, Mesa, the "
            "system's Python and libraries). Not installed from here: see the steps under the i."), about=(
            IMAGE_ABOUT + f"<p><b>Fedora {old} → {new}</b> changes the whole system. Install it by hand:</p><ol>"
            f"<li>Read its release notes: <a href='{RELEASES}'>Bazzite's releases</a> (what breaks, what to do "
            "first).</li>"
            "<li>In a terminal: <code>ujust update</code> (the image, the Flatpaks, Homebrew and distroboxes).</li>"
            f"<li>Restart: <code>{RESTART}</code>.</li>"
            "<li>Open Nexus Deps again: a venv made with the old Python has lost its packages (its card says so and "
            "installs them), and the suite's apps say what they miss.</li></ol>"
            f"<p>{ROLLBACK}</p>"))
    return Source("image", name, (update,), note=(
        f"Used after a restart ({RESTART}), which Nexus Deps never does by itself."), about=(
        IMAGE_ABOUT + "<p><b>Update</b> stages it with <code>rpm-ostree upgrade</code> (it may ask for your "
        f"password); the machine starts it at the next boot. {ROLLBACK}</p>"),
        step=Step("rpm-ostree", f"Bazzite {version} into the Bazzite image", ("rpm-ostree", "upgrade"),
                  restart=True))


# --- Flatpak --------------------------------------------------------------------------------------------------

def parse_flatpak(text: str) -> tuple[Update, ...]:
    """`flatpak remote-ls --updates --columns=application,branch,version`: a tab between the columns. A runtime
    often has no version; its branch says which one it is."""
    updates = []
    for line in text.splitlines():
        parts = line.split("\t")
        if not parts[0].strip():
            continue
        branch = parts[1].strip() if len(parts) > 1 else ""
        version = parts[2].strip() if len(parts) > 2 else ""
        updates.append(Update(parts[0].strip(), latest=version or branch))
    return tuple(updates)


FLATPAK_ABOUT = ("<p>The Flatpak apps and their runtimes, the user's and the system's. <b>Update</b> runs "
                 "<code>flatpak update</code>; the system's Flatpaks may ask for your password. An app that is open "
                 "uses its new version once it is started again. <code>flatpak update --commit=&lt;old&gt; "
                 "&lt;app&gt;</code> goes back to a version from <code>flatpak remote-info --log flathub "
                 "&lt;app&gt;</code>.</p>")


def check_flatpak(run: Run) -> Source:
    name = "Flatpak"
    done = run(["flatpak", "remote-ls", "--updates", "--columns=application,branch,version"], capture_output=True,
               text=True, timeout=TIMEOUT)
    if done.returncode != 0:
        return Source("flatpak", name, error=f"flatpak remote-ls failed: {_tail(done)}", about=FLATPAK_ABOUT)
    updates = parse_flatpak(done.stdout)
    step = Step("flatpak", f"{len(updates)} Flatpak update(s)", ("flatpak", "update", "-y", "--noninteractive"))
    return Source("flatpak", name, updates, step=step if updates else None, about=FLATPAK_ABOUT)


# --- Homebrew -------------------------------------------------------------------------------------------------

def parse_brew(text: str) -> tuple[Update, ...]:
    """`brew outdated --json=v2`: the formulae and the casks, each with its installed and its current version."""
    data = json.loads(text or "{}")
    updates = []
    for item in [*data.get("formulae", []), *data.get("casks", [])]:
        installed = item.get("installed_versions") or []
        current = ", ".join(installed) if isinstance(installed, list) else str(installed)
        updates.append(Update(str(item.get("name", "?")), current, str(item.get("current_version", ""))))
    return tuple(updates)


BREW_ABOUT = ("<p>Homebrew's formulae and casks (gh, shellcheck, node, the suite's tools from Homebrew such as "
              "stress-ng). <b>Update</b> runs <code>brew upgrade</code> for all of them; nothing needs a restart. "
              "A formula marked <i>major</i> may behave differently: <code>brew pin &lt;formula&gt;</code> before "
              "Update keeps it where it is, <code>brew unpin</code> lets it go again.</p>")


def check_brew(run: Run, brew: str) -> Source:
    name = "Homebrew"
    done = run([brew, "update", "--quiet"], capture_output=True, text=True, timeout=TIMEOUT)
    if done.returncode != 0:
        return Source("brew", name, error=f"brew update failed: {_tail(done)}", about=BREW_ABOUT)
    done = run([brew, "outdated", "--json=v2"], capture_output=True, text=True, timeout=TIMEOUT)
    if done.returncode != 0:
        return Source("brew", name, error=f"brew outdated failed: {_tail(done)}", about=BREW_ABOUT)
    try:
        updates = parse_brew(done.stdout)
    except (ValueError, AttributeError) as exc:
        return Source("brew", name, error=f"brew outdated could not be read: {exc}", about=BREW_ABOUT)
    step = Step("brew", f"{len(updates)} Homebrew update(s)", (brew, "upgrade"))
    return Source("brew", name, updates, step=step if updates else None, note=majors(updates), about=BREW_ABOUT)


# --- Rust -----------------------------------------------------------------------------------------------------

RUSTUP_LINE = re.compile(r"^(\S+) - update available : (\S+).*?-> (\S+)")


def parse_rustup(text: str) -> tuple[Update, ...]:
    """`rustup check`: "stable-x86_64-unknown-linux-gnu - update available : 1.99.1 (...) -> 1.100.0 (...)" and
    "rustup - update available : 1.29.2 -> 1.29.3"; "- up to date" lines are left out."""
    return tuple(Update(*found.groups()) for line in text.splitlines() if (found := RUSTUP_LINE.match(line.strip())))


RUST_ABOUT = ("<p>The Rust toolchains and rustup itself, for Console Link's native core (<code>cargo test</code>, "
              "<code>maturin build</code>). <b>Update</b> runs <code>rustup update</code>; nothing needs a restart. "
              "A new Rust can warn where the old did not: run clippy afterwards. <code>rustup default "
              "&lt;version&gt;</code> goes back to an older toolchain.</p>")


def check_rust(run: Run, rustup: str) -> Source:
    name = "Rust"
    done = run([rustup, "check"], capture_output=True, text=True, timeout=TIMEOUT)
    if done.returncode not in (0, 100):                             # 100: updates available
        return Source("rust", name, error=f"rustup check failed: {_tail(done)}", about=RUST_ABOUT)
    updates = parse_rustup(done.stdout)
    step = Step("rustup", "the Rust toolchain and rustup", (rustup, "update"))
    return Source("rust", name, updates, step=step if updates else None, about=RUST_ABOUT)


# --- The development venv -------------------------------------------------------------------------------------

def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


VENV_ABOUT = ("<p>The checkout's development venv, where <code>./test.sh</code>, the docs and the Nexus apps run. "
              "<b>Update</b> runs pip within what <code>requirements-dev.txt</code> allows, so a limit set on purpose "
              "(MkDocs below 2, Pillow below 13) stays: those packages are listed as held back. Raising a limit is a "
              "change to the requirements, tested with <code>./test.sh</code> and <code>tools/ci-local.sh</code>. "
              "After a major version, run <code>./test.sh</code>. To start over: <code>rm -rf .venv-linux && python3 "
              "-m venv .venv-linux && .venv-linux/bin/python -m pip install -r requirements-dev.txt</code>.</p>")


def made_with(venv: Path) -> str:
    """The Python version the venv was made with (pyvenv.cfg's version, "3.14"), "" when it does not say."""
    try:
        text = (venv / "pyvenv.cfg").read_text(encoding="utf-8")
    except OSError:
        return ""
    found = re.search(r"^version(?:_info)?\s*=\s*(\d+\.\d+)", text, re.MULTILINE)
    return found.group(1) if found else ""


def check_venv(run: Run, checkout: Path) -> Source:
    """A dry run of the upgrade within requirements-dev.txt, with pip's outdated packages: what it would install is
    the update (a missing package too), what stays below PyPI's latest is held back by the requirements. A venv
    whose python links to the system's /usr/bin/python3 runs a newer Python once Bazzite's image has one, without
    the packages it had for the older: while packages are missing, the note says so (pyvenv.cfg keeps the older
    version once they are installed again, so the version alone says nothing)."""
    venv = checkout / VENV
    python = str(venv / "bin" / "python")
    requirements = str(checkout / REQUIREMENTS)
    name = f"Python venv ({VENV})"
    pip = [python, "-m", "pip", "--disable-pip-version-check"]
    done = run([python, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"], capture_output=True, text=True,
               timeout=TIMEOUT)
    running, made = done.stdout.strip() if done.returncode == 0 else "", made_with(venv)
    done = run([*pip, "list", "--outdated", "--format", "json"], capture_output=True, text=True, timeout=TIMEOUT)
    if done.returncode != 0:
        return Source("venv", name, error=f"pip list --outdated failed: {_tail(done)}", about=VENV_ABOUT)
    try:
        outdated = {_canonical(item["name"]): (item["name"], item["version"], item["latest_version"])
                    for item in json.loads(done.stdout or "[]")}
    except (ValueError, KeyError, TypeError) as exc:
        return Source("venv", name, error=f"pip list could not be read: {exc}", about=VENV_ABOUT)
    names = sorted(original for original, _current, _latest in outdated.values())
    upgrade = ("install", "--upgrade", *names, "-r", requirements)
    done = run([*pip, *upgrade[:1], "--dry-run", "--quiet", "--report", "-", *upgrade[1:]], capture_output=True,
               text=True, timeout=TIMEOUT)
    if done.returncode != 0:
        return Source("venv", name, error=f"pip could not resolve requirements-dev.txt: {_tail(done)}", about=VENV_ABOUT)
    listed = run([*pip, "list", "--format", "json"], capture_output=True, text=True, timeout=TIMEOUT)
    try:
        installed = {_canonical(item["name"]): item["version"] for item in json.loads(listed.stdout or "[]")}
        report = json.loads(done.stdout)
        resolved = {_canonical(item["metadata"]["name"]): (item["metadata"]["name"], item["metadata"]["version"])
                    for item in report.get("install", [])}
    except (ValueError, KeyError, TypeError) as exc:
        return Source("venv", name, error=f"pip's report could not be read: {exc}", about=VENV_ABOUT)
    updates = tuple(Update(original, installed.get(key, ""), version) for key, (original, version)
                    in sorted(resolved.items()) if installed.get(key) != version)
    updated = {_canonical(update.name): update.latest for update in updates}
    held = tuple(Update(original, current, latest) for key, (original, current, latest) in sorted(outdated.items())
                 if updated.get(key) != latest)
    missing = sum(not update.current for update in updates)
    note = ""
    if missing and made and running and made != running:
        note = (f"The venv was made with Python {made} and runs Python {running} now (a new Bazzite image): the "
                f"packages it had for {made} are not used. Update installs requirements-dev.txt for {running}.")
    title = f"{len(updates)} package(s) into {VENV}" + (f", {missing} of them missing" if missing else "")
    return Source("venv", name, updates, held, step=Step("pip", title, (*pip, *upgrade)) if updates else None,
                  note=_notes(note, majors(updates)), about=VENV_ABOUT)


# --- Every source ---------------------------------------------------------------------------------------------

def _guarded(key: str, name: str, job: Callable[[], Source]) -> Source:
    try:
        return job()
    except subprocess.TimeoutExpired:
        return Source(key, name, error="it took too long (offline?)")
    except (OSError, subprocess.SubprocessError) as exc:
        return Source(key, name, error=str(exc))


def read_sources(run: Run = subprocess.run, which: Which = shutil.which,
                 checkout: Path = CHECKOUT) -> tuple[Source, ...]:
    """Every source this machine has, asked at the same time; in a fixed order."""
    jobs: list[tuple[str, str, Callable[[], Source]]] = []
    if which("rpm-ostree"):
        jobs.append(("image", "Bazzite image", lambda: check_image(run)))
    if which("flatpak"):
        jobs.append(("flatpak", "Flatpak", lambda: check_flatpak(run)))
    if brew := find_brew(which):
        jobs.append(("brew", "Homebrew", lambda: check_brew(run, brew)))
    if rustup := which("rustup"):
        jobs.append(("rust", "Rust", lambda: check_rust(run, rustup)))
    if (checkout / VENV / "bin" / "python").is_file():
        jobs.append(("venv", f"Python venv ({VENV})", lambda: check_venv(run, checkout)))
    if not jobs:
        return ()
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return tuple(pool.map(lambda job: _guarded(*job), jobs))


def steps(sources: tuple[Source, ...]) -> tuple[Step, ...]:
    return tuple(source.step for source in sources if source.step is not None and not source.error)


def summary(sources: tuple[Source, ...]) -> str:
    """"Homebrew (10), Rust (1)": the sources with updates, for the header's box."""
    return ", ".join(f"{source.name} ({len(source.updates)})" for source in sources if source.outdated)
