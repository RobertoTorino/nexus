# SPDX-License-Identifier: GPL-3.0-or-later
"""What the app reads as the user (state.py): the installed version, the service, Steam's switch and the plugins."""

from __future__ import annotations

import json

from conftest import make_plugin

from decky_manager import loader, state


def _paths(tmp_path) -> loader.Paths:
    return loader.Paths(tmp_path / "home", etc=tmp_path / "etc")


def test_installed_version(tmp_path):
    paths = _paths(tmp_path)
    assert state.installed_version(paths) == ""
    paths.services.mkdir(parents=True)
    paths.binary.write_bytes(b"")
    assert state.installed_version(paths) == "unknown"
    paths.version_file.write_text("v3.3.0\n")              # the app's and Decky's updater's
    assert state.installed_version(paths) == "3.3.0"
    paths.version_file.write_text("v3.3.0-pre1")
    assert state.installed_version(paths) == "3.3.0-pre1"
    paths.binary.unlink()
    assert state.installed_version(paths) == ""             # a version file alone is not Decky


def test_service(tmp_path):
    paths = _paths(tmp_path)
    answers = {"is-enabled": (0, "enabled\n"), "is-active": (3, "failed\n")}
    calls = []

    def run(argv):
        calls.append(argv)
        return answers[argv[1]]
    s = state.service(paths, run)
    assert s == state.Service(False, "enabled", "failed") and not s.running and s.at_boot
    assert calls == [["systemctl", "is-enabled", "plugin_loader"], ["systemctl", "is-active", "plugin_loader"]]
    assert state.service(paths, lambda argv: (127, "")).active == "unknown"


def test_journal():
    assert state.journal(lambda argv: (0, "line 1\nline 2\n")) == "line 1\nline 2"
    assert "could not read" in state.journal(lambda argv: (1, ""))


def test_steam_folders_and_the_switch(tmp_path):
    home = tmp_path / "home"
    assert state.steam_folders(home) == [] and not state.cef_enabled([])
    native = home / ".local/share/Steam"
    native.mkdir(parents=True)
    (home / ".steam").mkdir()
    (home / ".steam/steam").symlink_to(native)              # Bazzite's: one folder, found once
    flatpak = home / ".var/app/com.valvesoftware.Steam/data/Steam"
    flatpak.mkdir(parents=True)
    folders = state.steam_folders(home)
    assert folders == [home / ".steam/steam", flatpak]
    assert not state.cef_enabled(folders)
    state.enable_cef(folders)
    assert (native / ".cef-enable-remote-debugging").is_file() and state.cef_enabled(folders)
    state.disable_cef(folders)
    assert not (native / ".cef-enable-remote-debugging").exists() and not (flatpak / state.CEF_FILE).exists()


def test_plugins(tmp_path):
    paths = _paths(tmp_path)
    assert state.plugins(paths) == []
    make_plugin(paths.plugins, "SDH-CssLoader", "CSS Loader", "2.1.2", "DeckThemes")
    make_plugin(paths.plugins, "decky-recorder", "Decky Recorder", None)
    broken = paths.plugins / "broken"
    broken.mkdir()
    (broken / "plugin.json").write_text("{not json")
    (paths.plugins / "no-plugin-json").mkdir()               # not a plugin to Decky either
    paths.loader_settings.parent.mkdir(parents=True)
    paths.loader_settings.write_text(json.dumps({"disabled_plugins": ["Decky Recorder"]}))
    found = state.plugins(paths)
    assert [(p.name, p.version, p.author, p.disabled) for p in found] == [
        ("broken", "", "", False), ("CSS Loader", "2.1.2", "DeckThemes", False), ("Decky Recorder", "", "someone", True)]
