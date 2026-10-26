# SPDX-License-Identifier: GPL-3.0-or-later
"""Launch options in Steam whose game monitor can no longer start: read from localconfig.vdf, the reason, the
fixed line and the game's name; and the warning on the In-Game page."""

from __future__ import annotations

import os
from pathlib import Path

from bazzite_check import steamlines

PREFIX = "PYTHONPATH=/opt/bc250-bazzite-test /venv/bin/python -m bazzite_check.gamemon"
# From the owner's board (19-10-2026), the user folder masked: lines copied from the checkout before the move.
OLD = ("PYTHONPATH=/home/user/bc250-bazzite-test /home/user/bc250-bazzite-test/_python/bin/python "
       "-m bc250_gui.gamemon")


def localconfig(apps: dict[str, str]) -> str:
    def esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"')
    entries = "".join(f'\t\t\t\t\t"{appid}"\n\t\t\t\t\t{{\n\t\t\t\t\t\t"LastPlayed"\t\t"1760000000"\n'
                      f'\t\t\t\t\t\t"LaunchOptions"\t\t"{esc(line)}"\n\t\t\t\t\t}}\n' for appid, line in apps.items())
    return ('"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n'
            '\t\t\t\t"LaunchOptions"\t\t"not an app"\n'
            f'\t\t\t\t"apps"\n\t\t\t\t{{\n{entries}\t\t\t\t}}\n\t\t\t}}\n\t\t}}\n\t}}\n}}\n')


def python(folder: Path) -> Path:
    exe = folder / "bin" / "python"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    return exe


def app_folder(folder: Path) -> Path:
    (folder / "bazzite_check").mkdir(parents=True)
    (folder / "bazzite_check" / "gamemon.py").write_text("")
    return folder


def steam_with(tmp_path: Path, users: dict[str, dict[str, str]]) -> Path:
    steam = tmp_path / "Steam"
    for user, apps in users.items():
        config = steam / "userdata" / user / "config"
        config.mkdir(parents=True)
        (config / "localconfig.vdf").write_text(localconfig(apps))
    return steam


def test_launch_options_reads_apps_only_and_unescapes():
    text = localconfig({"389730": 'FOO="a b" %command%', "10": "", "297860": OLD + " %command%"})
    assert steamlines.launch_options(text) == {"389730": 'FOO="a b" %command%', "297860": OLD + " %command%"}


def test_old_package_line_is_stale_for_its_missing_python():
    assert steamlines.gamemon_problem(OLD + " mangohud %command%").startswith("its python is gone")


def test_lines_without_gamemon_are_left_alone():
    for line in ("%command%", "mangohud %command%", "gamemoderun %command% -dx11", "PROTON_LOG=1 %command%"):
        assert steamlines.gamemon_problem(line) is None


def test_current_line_is_fine(tmp_path):
    exe, root = python(tmp_path / "venv"), app_folder(tmp_path / "app")
    assert steamlines.gamemon_problem(f"PYTHONPATH={root} {exe} -m bazzite_check.gamemon %command%") is None


def test_quoted_paths_with_spaces(tmp_path):
    exe, root = python(tmp_path / "my venv"), app_folder(tmp_path / "my app")
    line = f"PYTHONPATH='{root}' '{exe}' -m bazzite_check.gamemon mangohud %command%"
    assert steamlines.gamemon_problem(line) is None
    assert steamlines.fixed_line(line, PREFIX) == PREFIX + " mangohud %command%"


def test_each_missing_part_has_its_reason(tmp_path):
    exe, root = python(tmp_path / "venv"), app_folder(tmp_path / "app")
    assert "app folder is gone" in steamlines.gamemon_problem(
        f"PYTHONPATH={tmp_path / 'moved'} {exe} -m bazzite_check.gamemon %command%")
    assert "names the package bc250_gui" in steamlines.gamemon_problem(
        f"PYTHONPATH={root} {exe} -m bc250_gui.gamemon %command%")
    assert "has no bazzite_check" in steamlines.gamemon_problem(
        f"PYTHONPATH={tmp_path} {exe} -m bazzite_check.gamemon %command%")
    assert steamlines.gamemon_problem(f"{exe} -m bazzite_check.gamemon %command%") is None   # no PYTHONPATH


def test_fixed_line_keeps_what_surrounds_the_gamemon_part():
    assert steamlines.fixed_line(f"DXVK_HUD=1 {OLD} mangohud %command% -novid", PREFIX) == \
        f"DXVK_HUD=1 {PREFIX} mangohud %command% -novid"


def test_stale_lines_over_every_user_with_names_from_any_library(tmp_path):
    exe, root = python(tmp_path / "venv"), app_folder(tmp_path / "app")
    good = f"PYTHONPATH={root} {exe} -m bazzite_check.gamemon %command%"
    steam = steam_with(tmp_path, {
        "111": {"389730": OLD + " mangohud %command%", "297860": OLD + " %command%", "570": good},
        "222": {"389730": OLD + " mangohud %command%", "851670": "%command%"},
    })
    (steam / "steamapps").mkdir()
    (steam / "steamapps" / "appmanifest_389730.acf").write_text('"AppState"\n{\n\t"appid"\t\t"389730"\n'
                                                               '\t"name"\t\t"TEKKEN 7"\n}\n')
    library = tmp_path / "games"
    (library / "steamapps").mkdir(parents=True)
    (library / "steamapps" / "appmanifest_297860.acf").write_text('"AppState"\n{\n\t"name"\t\t"Split/Second"\n}\n')
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n\t"0"\n\t{{\n\t\t"path"\t\t"{steam}"\n\t}}\n'
        f'\t"1"\n\t{{\n\t\t"path"\t\t"{library}"\n\t}}\n}}\n')
    stale = steamlines.stale_lines(steam, PREFIX)
    assert [(s.appid, s.name, s.fixed) for s in stale] == [
        ("297860", "Split/Second", PREFIX + " %command%"),
        ("389730", "TEKKEN 7", PREFIX + " mangohud %command%"),
    ]


def test_no_steam_or_no_name(tmp_path):
    assert steamlines.stale_lines(None, PREFIX) == []
    steam = steam_with(tmp_path, {"1": {"42": OLD + " %command%"}})
    assert [s.name for s in steamlines.stale_lines(steam, PREFIX)] == ["AppID 42"]


def test_from_checkout(tmp_path):
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    (tmp_path / "repo" / "apps" / "check").mkdir(parents=True)
    (tmp_path / "opt" / "bc250-bazzite-test").mkdir(parents=True)
    assert steamlines.from_checkout(tmp_path / "repo" / "apps" / "check")
    assert not steamlines.from_checkout(tmp_path / "opt" / "bc250-bazzite-test")


def test_ingame_page_lists_the_stale_games(sandbox, monkeypatch):
    from PyQt6.QtWidgets import QLabel, QLineEdit

    from bazzite_check import ingame
    steam = steam_with(sandbox.parent, {"1": {"297860": OLD + " %command%"}})
    monkeypatch.setattr(ingame, "find_steam", lambda: steam)
    page = ingame.InGamePage()
    texts = [w.text() for w in page.findChildren(QLabel)]
    assert any("1 game in Steam will not start" in t for t in texts)
    assert ingame.gamemon_prefix() + " %command%" in [w.text() for w in page.findChildren(QLineEdit)]

    (steam / "userdata" / "1" / "config" / "localconfig.vdf").write_text(localconfig({"297860": "%command%"}))
    page.reload()
    from PyQt6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not any("will not start" in w.text() for w in page.findChildren(QLabel))


def test_scan_reads_only(tmp_path):
    steam = steam_with(tmp_path, {"1": {"297860": OLD + " %command%"}})
    config = steam / "userdata" / "1" / "config" / "localconfig.vdf"
    before = (config.read_bytes(), os.stat(config).st_mtime_ns)
    steamlines.stale_lines(steam, PREFIX)
    assert (config.read_bytes(), os.stat(config).st_mtime_ns) == before
