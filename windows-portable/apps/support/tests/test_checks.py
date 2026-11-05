# SPDX-License-Identifier: GPL-3.0-or-later
"""The checks (checks.py), each on its own source faked: the portal's apps and records, each app's state against the
portal's version, the tools' statuses for the installed apps (the most urgent that applies), Windows' tar with and
without liblzma, the Visual C++ runtime's files, and Windows' version, its restart and its newest update."""

from __future__ import annotations

import datetime
import json

from support_checker import checks
from support_checker.checks import App, Found


def write_portal(folder, manifest: str, recorded: dict[str, str]):
    internal = folder / "app" / "_internal"
    internal.mkdir(parents=True)
    (internal / "apps.toml").write_text(manifest, encoding="utf-8")
    (folder / "installed.json").write_text(json.dumps(recorded), encoding="utf-8")


MANIFEST = """
[apps.test]
name = "Windows Portable Test"
tag = "wp-test-v0.2.0"
detect = ["%TEMP%\\\\none\\\\test.exe"]

[apps.xenia]
name = "Xenia Manager"
tag = "wp-xenia-v0.4.0"
detect = ["%TEMP%\\\\none\\\\xenia.exe"]
"""


def test_the_portals_apps_and_records(tmp_path):
    folder = tmp_path / "portal"
    write_portal(folder, MANIFEST, {"xenia": "wp-xenia-v0.3.1"})
    assert checks.manifest_path(folder) == folder / "app" / "_internal" / "apps.toml"
    apps = checks.load_apps(checks.manifest_path(folder))
    assert [(a.key, a.name, a.version) for a in apps] == [("test", "Windows Portable Test", "0.2.0"),
                                                          ("xenia", "Xenia Manager", "0.4.0")]
    assert checks.records(folder) == {"xenia": "wp-xenia-v0.3.1"}
    assert checks.records(tmp_path / "none") == {} and checks.load_apps(None) == []


def test_each_apps_state():
    apps = [App("a", "A", "wp-a-v1.2.0", ()), App("b", "B", "wp-b-v1.0.0", ()), App("c", "C", "wp-c-v2.0.0", ()),
            App("d", "D", "wp-d-v0.1.0", ())]
    states = checks.app_states(apps, {"a": "wp-a-v1.1.9", "b": "wp-b-v1.0.0"}, lambda app: app.key != "d")
    assert [(s.app.key, s.status, s.installed) for s in states] == [
        ("a", "Update in the portal", "1.1.9"), ("b", "Up to date", "1.0.0"), ("c", "Version unknown", ""),
        ("d", "Not installed", "")]


def test_the_tools_for_the_installed_apps():
    """Missing when an installed app needs it, Not installed when they only use it, Not needed when none uses it,
    Unsupported build before Available."""
    found = {"powershell": Found(True, "ps"), "vcruntime": Found(False, "missing in System32: msvcp140.dll"),
             "tar": Found(True, "tar", "built without liblzma"), "steam": Found(False, "none"),
             "xbox": Found(True, "installed")}
    finders = {key: (lambda value=value: value) for key, value in found.items()}
    states = {s.tool.key: s for s in checks.tool_states({"portal", "xenia"}, {"xenia": "Xenia Manager",
                                                                              "portal": "the portal"}, finders)}
    assert {k: s.status for k, s in states.items()} == {
        "powershell": "Available", "vcruntime": "Missing", "tar": "Unsupported build", "steam": "Not installed",
        "xbox": "Available"}
    assert states["vcruntime"].needed_by == ("Xenia Manager",) and states["vcruntime"].required
    assert not states["steam"].required and set(states["steam"].needed_by) == {"Xenia Manager", "the portal"}
    alone = {s.tool.key: s.status for s in checks.tool_states({"portal"}, {}, finders)}
    assert alone["vcruntime"] == "Not needed" and alone["tar"] == "Not needed"


def test_tar_with_and_without_liblzma(tmp_path):
    assert not checks.find_tar(tmp_path, lambda argv: "").ok                       # no tar.exe
    (tmp_path / "tar.exe").write_bytes(b"")
    good = checks.find_tar(tmp_path, lambda argv: "bsdtar 3.7.2 - libarchive 3.7.2 zlib/1.2.13 liblzma/5.4.3\n")
    assert good.ok and not good.unsupported and "bsdtar 3.7.2" in good.where
    old = checks.find_tar(tmp_path, lambda argv: "bsdtar 3.5.2 - libarchive 3.5.2 zlib/1.2.5.f-ipp\n")
    assert old.ok and "cannot unpack a .7z" in old.unsupported


def test_the_visual_cpp_runtime(tmp_path):
    assert checks.find_vcruntime(tmp_path).where.startswith("missing in System32: vcruntime140.dll")
    for name in checks.RUNTIME_DLLS:
        (tmp_path / name).write_bytes(b"")
    assert checks.find_vcruntime(tmp_path).ok


def test_windows_its_restart_and_its_newest_update():
    values = {"ProductName": "Windows 10 Home", "CurrentBuild": "26100", "UBR": 4351, "DisplayVersion": "24H2"}

    def registry(path, name=None, restart=False):
        if name is None:
            return restart and path.endswith("RebootRequired")
        return values.get(name)
    state = checks.read_windows(registry, lambda argv: "2026-10-14 KB5066835\r\n")
    assert (state.name, state.version, state.build) == ("Windows 11 Home", "24H2", "26100.4351")
    assert state.last_update == "2026-10-14 (KB5066835)" and not state.restart
    assert state.status(datetime.date(2026, 11, 5)) == "Up to date"
    assert state.status(datetime.date(2026, 12, 1)) == "Update late"
    waiting = checks.read_windows(lambda path, name=None: registry(path, name, restart=True), lambda argv: "")
    assert waiting.restart and waiting.status() == "Restart to update" and waiting.last_update == ""
    unknown = checks.read_windows(registry, lambda argv: "")
    assert unknown.status() == "Unknown"
