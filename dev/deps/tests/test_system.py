# SPDX-License-Identifier: GPL-3.0-or-later
"""The machine's updates (system.py) from each tool's answers, as the development machine gave them on 09-11-2026
(Homebrew's formulae and a cask, rustup, the venv after Bazzite moved to Python 3.15), and the steps that install
them."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from nexus_deps import system
from nexus_deps.system import Update

IMAGE_UPDATE = """\
Note: --check and --preview may be unreliable.  See https://github.com/coreos/rpm-ostree/issues/1579
AvailableUpdate:
        Version: 44.20261109.0 (2026-11-09T04:12:33Z)
         Digest: sha256:0123456789abcdef
"""
BREW = {"formulae": [{"name": "node", "installed_versions": ["26.13.0_1"], "current_version": "26.13.0_2"},
                     {"name": "simdjson", "installed_versions": ["5.0.6", "5.0.7"], "current_version": "5.1.1"}],
        "casks": [{"name": "visual-studio-code-linux", "installed_versions": ["1.144.0,2c33b50"],
                   "current_version": "1.145.2,c4453f8"}]}
RUSTUP = """\
stable-x86_64-unknown-linux-gnu - update available : 1.99.1 (58cf8f9c3 2026-10-13) -> 1.100.0 (1a2b3c4d5 2026-11-06)
rustup - update available : 1.29.2 -> 1.29.3
"""
FLATPAK = "org.mozilla.firefox\tstable\t145.0\norg.freedesktop.Platform.GL.default\t25.08\t\n"
OUTDATED = [{"name": "pytest", "version": "8.4.2", "latest_version": "9.2.0"},
            {"name": "mkdocs", "version": "1.6.1", "latest_version": "2.0.1"}]          # kept below 2
INSTALLED = [{"name": "pytest", "version": "8.4.2"}, {"name": "mkdocs", "version": "1.6.1"},
             {"name": "PyYAML", "version": "6.0.3"}]
REPORT = {"install": [{"metadata": {"name": "pytest", "version": "9.2.0"}},
                      {"metadata": {"name": "mkdocs", "version": "1.6.1"}},
                      {"metadata": {"name": "PyYAML", "version": "6.0.3"}},
                      {"metadata": {"name": "paramiko", "version": "5.1.0"}}]}               # missing


@pytest.fixture(autouse=True)
def no_homebrew_of_this_machine(monkeypatch, tmp_path):
    """Homebrew where Bazzite puts it is this machine's: the tests have only the one *which* gives."""
    monkeypatch.setattr(system, "BREW_HOME", str(tmp_path / "no-brew"))


def done(argv, code=0, out="", err=""):
    return subprocess.CompletedProcess(argv, code, out, err)


class Machine:
    """subprocess.run for the tools, answering as the development machine did; records every command."""

    def __init__(self, image=(77, ""), python="3.14", running="44.20261102.0", **answers):
        self.image = image
        self.running = running
        self.python = python
        self.answers = answers
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        tool, args = Path(argv[0]).name, argv[1:]
        if tool == "rpm-ostree" and args[0] == "status":
            return done(argv, 0, json.dumps({"deployments": [{"booted": True, "version": self.running,
                                                               "timestamp": 1}]}))
        if tool == "rpm-ostree":
            return done(argv, *self.image)
        if tool == "flatpak":
            return done(argv, 0, self.answers.get("flatpak", ""))
        if tool == "brew":
            return done(argv, 0, json.dumps(self.answers.get("brew", {})) if args[0] == "outdated" else "")
        if tool == "rustup":
            return done(argv, 100 if self.answers.get("rustup") else 0, self.answers.get("rustup", ""))
        if tool == "python" and args[0] == "-c":
            return done(argv, 0, self.python + "\n")
        if tool == "python" and "list" in args:
            data = self.answers.get("outdated", []) if "--outdated" in args else self.answers.get("installed", [])
            return done(argv, 0, json.dumps(data))
        if tool == "python" and "--dry-run" in args:
            return done(argv, 0, json.dumps(self.answers.get("report", {"install": []})))
        raise AssertionError(argv)


def checkout(tmp_path: Path, made="3.14") -> Path:
    (tmp_path / ".venv-linux" / "bin").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".venv-linux" / "bin" / "python").write_text("")
    (tmp_path / ".venv-linux" / "pyvenv.cfg").write_text(f"home = /usr/bin\nversion = {made}.8\n")
    return tmp_path


def which(name):
    return f"/usr/bin/{name}"


def test_every_source_with_its_updates_and_its_step(tmp_path):
    run = Machine(image=(0, IMAGE_UPDATE), flatpak=FLATPAK, brew=BREW, rustup=RUSTUP, outdated=OUTDATED,
                  installed=INSTALLED, report=REPORT)
    sources = {source.key: source for source in system.read_sources(run, which, checkout(tmp_path))}
    assert list(sources) == ["image", "flatpak", "brew", "rust", "venv"]

    image = sources["image"]
    assert image.updates == (Update("Bazzite", "44.20261102.0", "44.20261109.0"),)
    assert image.step.command == ("rpm-ostree", "upgrade") and image.step.restart
    assert "Used after a restart (systemctl reboot)" in image.note and "rpm-ostree rollback" in image.about

    assert sources["flatpak"].updates == (Update("org.mozilla.firefox", "", "145.0"),
                                          Update("org.freedesktop.Platform.GL.default", "", "25.08"))
    assert sources["flatpak"].step.command == ("flatpak", "update", "-y", "--noninteractive")

    brew = sources["brew"]
    assert [update.name for update in brew.updates] == ["node", "simdjson", "visual-studio-code-linux"]
    assert brew.updates[1].current == "5.0.6, 5.0.7"
    assert brew.step.command == ("/usr/bin/brew", "upgrade")
    assert brew.note == ""                                                  # no new major version among them
    assert "brew pin" in brew.about

    assert sources["rust"].updates == (Update("stable-x86_64-unknown-linux-gnu", "1.99.1", "1.100.0"),
                                       Update("rustup", "1.29.2", "1.29.3"))
    assert sources["rust"].step.command == ("/usr/bin/rustup", "update")

    venv = sources["venv"]
    assert venv.updates == (Update("paramiko", "", "5.1.0"), Update("pytest", "8.4.2", "9.2.0"))
    assert venv.held == (Update("mkdocs", "1.6.1", "2.0.1"),)                 # requirements-dev.txt keeps it
    command = venv.step.command
    assert command[-5:] == ("--upgrade", "mkdocs", "pytest", "-r", str(tmp_path / "requirements-dev.txt"))
    assert "--dry-run" not in command and venv.step.title == "2 package(s) into .venv-linux, 1 of them missing"
    assert venv.note.startswith("New major version: pytest 9.") and venv.held[0].major

    assert [step.kind for step in system.steps(tuple(sources.values()))] == [
        "rpm-ostree", "flatpak", "brew", "rustup", "pip"]
    assert system.summary(tuple(sources.values())) == (
        "Bazzite image (1), Flatpak (2), Homebrew (3), Rust (2), Python venv (.venv-linux) (2)")


def test_everything_current(tmp_path):
    run = Machine(installed=INSTALLED, report={"install": [{"metadata": {"name": "pytest", "version": "8.4.2"}}]})
    sources = system.read_sources(run, which, checkout(tmp_path))
    assert all(not source.updates and source.step is None and not source.error for source in sources)
    assert system.steps(sources) == () and system.summary(sources) == ""
    # Homebrew fetches its formulae before it is asked; nothing is installed or upgraded
    assert ["/usr/bin/brew", "update", "--quiet"] in run.calls
    for argv in run.calls:
        assert "upgrade" not in argv or argv[1:3] == ["upgrade", "--check"]          # rpm-ostree only asks
        assert "install" not in argv or "--dry-run" in argv                          # pip only resolves


def test_a_venv_left_on_an_older_python_says_so(tmp_path):
    """Bazzite's image moved python3 to 3.15: the venv's python follows it, without the packages it had for 3.14."""
    run = Machine(python="3.15", installed=[{"name": "pip", "version": "26.1.2"}], report=REPORT)
    venv = system.check_venv(run, checkout(tmp_path, made="3.14"))
    assert "made with Python 3.14 and runs Python 3.15" in venv.note
    assert venv.step.title == "4 package(s) into .venv-linux, 4 of them missing"
    # Once they are installed again, pyvenv.cfg still names 3.14: no note then
    again = Machine(python="3.15", installed=INSTALLED, report={"install": []})
    assert system.check_venv(again, checkout(tmp_path, made="3.14")).note == ""


def test_sources_this_machine_lacks_are_left_out(tmp_path):
    sources = system.read_sources(Machine(), lambda name: None, tmp_path)
    assert sources == ()


def test_a_source_that_fails_says_why_and_offers_nothing(tmp_path):
    def run(argv, **kwargs):
        if Path(argv[0]).name == "flatpak":
            return done(argv, 1, "", "error: Unable to load summary from remote flathub: Could not resolve host")
        if Path(argv[0]).name == "rustup":
            raise subprocess.TimeoutExpired(argv, 1)
        return Machine(image=(1, "", "error: no daemon"))(argv, **kwargs)
    sources = {source.key: source for source in system.read_sources(run, lambda name: f"/usr/bin/{name}"
                                                                     if name in ("flatpak", "rustup", "rpm-ostree")
                                                                     else None, tmp_path)}
    assert sources["flatpak"].error.endswith("Could not resolve host") and sources["flatpak"].step is None
    assert sources["rust"].error == "it took too long (offline?)"
    assert sources["image"].error == "rpm-ostree upgrade --check failed: error: no daemon"
    assert system.steps(tuple(sources.values())) == ()


def test_homebrew_off_the_path_is_still_found(monkeypatch):
    """A timer's service has no Homebrew on its PATH: Bazzite's own place is looked at."""
    monkeypatch.setattr(system, "BREW_HOME", __file__)
    assert system.find_brew(lambda name: None) == __file__
    assert system.find_brew(lambda name: "/opt/brew") == "/opt/brew"


def test_the_parsers_keep_to_what_the_tools_print():
    assert system.parse_image_check("No updates available.\n") == ""
    assert system.parse_image_check("AvailableUpdate:\n  Digest: sha256:00\n") == "(a new deployment)"
    assert system.parse_rustup("stable-x86_64-unknown-linux-gnu - up to date: 1.99.1 (58cf8f9c3 2026-10-13)\n") == ()
    assert system.parse_flatpak("\n") == ()
    assert system.parse_brew("{}") == ()


def test_a_new_fedora_release_is_not_installed_by_a_click():
    """44 → 45 changed the system's Python under the venv on 09-11-2026: such an image has the steps, not a step."""
    run = Machine(image=(0, IMAGE_UPDATE.replace("44.20261109.0", "45.20261109.0")), running="44.20261102.0")
    image = system.check_image(run)
    assert image.manual and image.step is None and system.steps((image,)) == ()
    assert "moves from Fedora 44 to Fedora 45" in image.note
    for words in ("ujust update", "systemctl reboot", "releases", "rpm-ostree rollback", "lost its packages"):
        assert words in image.about


def test_major_versions_are_named():
    updates = (Update("node", "26.13.0_1", "27.0.0"), Update("lz4", "1.10.0", "1.11.0"),
               Update("ca-certificates", "2026-10-20", "2026-11-05"), Update("paramiko", "", "5.1.0"))
    assert [update.major for update in updates] == [True, False, False, False]
    assert system.majors(updates).startswith("New major version: node 27.")
    assert system.majors(updates[1:]) == ""


def test_every_source_says_what_update_does(tmp_path):
    run = Machine(image=(0, IMAGE_UPDATE), flatpak=FLATPAK, brew=BREW, rustup=RUSTUP, outdated=OUTDATED,
                  installed=INSTALLED, report=REPORT)
    assert all(source.about for source in system.read_sources(run, which, checkout(tmp_path)))
