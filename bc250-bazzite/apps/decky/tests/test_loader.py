# SPDX-License-Identifier: GPL-3.0-or-later
"""The root part (loader.py) on a home and /etc made in a temp folder, with a fake runner and chown: what installing
writes and runs, the refusals, removing with and without the plugins, and the /home/deck link."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import make_plugin

from decky_manager import loader

BINARY = b"\x7fELF decky"


class Recorder:
    def __init__(self, fail: str = ""):
        self.commands: list[list[str]] = []
        self.owners: dict[str, tuple[int, int]] = {}
        self.fail = fail

    def run(self, argv: list[str]) -> loader.Result:
        self.commands.append(argv)
        return loader.Result(1, "Job failed.") if self.fail and self.fail in argv else loader.Result(0, "")

    def chown(self, path: Path, uid: int, gid: int) -> None:
        self.owners[path.name] = (uid, gid)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "SHA256", hashlib.sha256(BINARY).hexdigest())
    home = tmp_path / "home" / "player"
    home.mkdir(parents=True)
    paths = loader.Paths(home, etc=tmp_path / "etc", deck=tmp_path / "home" / "deck", selinux=tmp_path / "selinux")
    user = loader.User("player", 1000, 1000, home)
    source = tmp_path / "download" / "PluginLoader"
    source.parent.mkdir()
    source.write_bytes(BINARY)
    return user, paths, source


def test_the_pin_points_at_the_release():
    assert loader.URL == "https://github.com/SteamDeckHomebrew/decky-loader/releases/download/v3.3.0/PluginLoader"
    assert len(loader.SHA256) == 64 and loader.TAG == f"v{loader.VERSION}"


def test_the_unit_is_deckys_release_unit():
    """dist/plugin_loader-release.service of Decky, ${HOMEBREW_FOLDER} filled in as its installer does."""
    upstream = ("[Unit]\nDescription=SteamDeck Plugin Loader\nAfter=network.target\n[Service]\nType=simple\n"
                "User=root\nRestart=always\nKillMode=process\nTimeoutStopSec=15\n"
                "ExecStart=${HOMEBREW_FOLDER}/services/PluginLoader\nWorkingDirectory=${HOMEBREW_FOLDER}/services\n"
                "Environment=UNPRIVILEGED_PATH=${HOMEBREW_FOLDER}\nEnvironment=PRIVILEGED_PATH=${HOMEBREW_FOLDER}\n"
                "Environment=LOG_LEVEL=INFO\n[Install]\nWantedBy=multi-user.target\n")
    homebrew = Path("/var/home/player/homebrew")
    assert loader.unit_text(homebrew) == upstream.replace("${HOMEBREW_FOLDER}", str(homebrew))


def test_install(setup, monkeypatch):
    user, paths, source = setup
    monkeypatch.setattr(loader.shutil, "which", lambda name: f"/usr/bin/{name}")
    (paths.selinux).mkdir()
    (paths.selinux / "enforce").write_text("1")
    fake = Recorder()
    assert loader.install(user, paths, source, fake.run, fake.chown) == "Decky Loader 3.3.0 is installed and running."
    assert paths.binary.read_bytes() == BINARY and paths.binary.stat().st_mode & 0o777 == 0o755
    assert paths.version_file.read_text() == "v3.3.0\n"
    assert paths.unit.read_text() == loader.unit_text(paths.homebrew)
    assert paths.plugins.is_dir()
    assert fake.owners["homebrew"] == fake.owners["plugins"] == (1000, 1000)          # the user's, as Decky's
    assert fake.owners["services"] == (0, 0)                                          # root's: see loader.py
    assert fake.owners[".PluginLoader.new"] == (0, 0)
    assert fake.commands == [["chcon", "-t", "bin_t", str(paths.binary)], ["restorecon", str(paths.unit)],
                             ["systemctl", "daemon-reload"], ["systemctl", "enable", "plugin_loader"],
                             ["systemctl", "restart", "plugin_loader"]]
    assert sorted(p.name for p in paths.services.iterdir()) == [".loader.version", "PluginLoader"]


def test_update_keeps_the_plugins_and_without_selinux_no_chcon(setup, monkeypatch):
    user, paths, source = setup
    monkeypatch.setattr(loader.shutil, "which", lambda name: None)
    make_plugin(paths.plugins, "Tool", "Tool")
    paths.services.mkdir()
    paths.binary.write_bytes(b"old")
    paths.user_unit.parent.mkdir(parents=True)
    paths.user_unit.write_text("old user unit")
    fake = Recorder()
    loader.install(user, paths, source, fake.run, fake.chown)
    assert paths.binary.read_bytes() == BINARY and (paths.plugins / "Tool" / "plugin.json").is_file()
    assert "homebrew" not in fake.owners and "plugins" not in fake.owners             # there already: left as they are
    assert not paths.user_unit.exists()
    assert fake.commands[0] == ["systemctl", "daemon-reload"]


def test_a_different_file_or_a_link_changes_nothing(setup, tmp_path):
    user, paths, source = setup
    source.write_bytes(b"something else")
    with pytest.raises(loader.LoaderError, match="SHA-256 differs"):
        loader.install(user, paths, source, Recorder().run, Recorder().chown)
    assert not paths.homebrew.exists() and not paths.unit.exists()
    source.write_bytes(BINARY)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    paths.homebrew.symlink_to(elsewhere)
    with pytest.raises(loader.LoaderError, match="is a link"):
        loader.install(user, paths, source, Recorder().run, Recorder().chown)
    assert not list(elsewhere.iterdir())


def test_a_service_that_does_not_start_is_an_error(setup, monkeypatch):
    user, paths, source = setup
    monkeypatch.setattr(loader.shutil, "which", lambda name: None)
    with pytest.raises(loader.LoaderError, match="systemctl restart plugin_loader failed .*Job failed"):
        loader.install(user, paths, source, Recorder("restart").run, Recorder().chown)


def test_remove_keeps_the_plugins_unless_wiped(setup, monkeypatch):
    user, paths, source = setup
    monkeypatch.setattr(loader.shutil, "which", lambda name: None)
    fake = Recorder()
    loader.install(user, paths, source, fake.run, fake.chown)
    make_plugin(paths.plugins, "Tool", "Tool")
    fake.commands.clear()
    text = loader.remove(user, paths, run=fake.run)
    assert text == "Decky Loader is removed; its plugins and their settings stay in ~/homebrew."
    assert fake.commands == [["systemctl", "disable", "--now", "plugin_loader"], ["systemctl", "daemon-reload"]]
    assert not paths.unit.exists() and not paths.services.exists() and (paths.plugins / "Tool").is_dir()
    loader.install(user, paths, source, fake.run, fake.chown)
    assert loader.remove(user, paths, wipe=True, run=fake.run).endswith("with its plugins and their settings.")
    assert not paths.homebrew.exists()


def test_deck_link(setup, tmp_path):
    user, paths, _source = setup
    assert loader.deck_state(user.home, paths.deck) == "missing"
    assert loader.link_deck(user, paths, Recorder().run).endswith("points to your home now.")
    assert paths.deck.is_symlink() and loader.deck_state(user.home, paths.deck) == "linked"
    assert "already" in loader.link_deck(user, paths, Recorder().run)
    assert loader.remove(user, paths, unlink=True, run=Recorder().run).endswith("is no longer linked.")
    assert not paths.deck.exists() and not paths.deck.is_symlink()
    with pytest.raises(loader.LoaderError, match="not a link to your home"):
        loader.unlink_deck(user, paths)

    paths.deck.mkdir()                                  # another user's home
    assert loader.deck_state(user.home, paths.deck) == "taken"
    with pytest.raises(loader.LoaderError, match="folder of its own"):
        loader.link_deck(user, paths)
    paths.deck.rmdir()
    paths.deck.symlink_to(tmp_path)
    assert loader.deck_state(user.home, paths.deck) == "elsewhere"
    with pytest.raises(loader.LoaderError, match="link to"):
        loader.link_deck(user, paths)
    with pytest.raises(loader.LoaderError):
        loader.unlink_deck(user, paths)
    assert paths.deck.is_symlink()                      # left as it was
    own = tmp_path / "deck-home"
    own.mkdir()
    assert loader.deck_state(own, own) == "own"


def test_the_command_line_runs_on_its_own_and_needs_pkexec():
    """It runs with the system python in isolated mode, beside nothing of the app: the standard library only."""
    script = Path(loader.__file__)
    env = {k: v for k, v in os.environ.items() if k != "PKEXEC_UID"}
    done = subprocess.run([sys.executable, "-I", str(script), "restart"], capture_output=True, text=True, env=env)
    answer = json.loads(done.stdout.strip().splitlines()[-1])
    assert done.returncode == 1 and not answer["ok"]
    expected = "PKEXEC_UID is not set" if os.geteuid() == 0 else "This needs root"
    assert expected in answer["error"]
    help_text = subprocess.run([sys.executable, "-I", str(script), "--help"], capture_output=True, text=True)
    assert help_text.returncode == 0 and "install" in help_text.stdout
