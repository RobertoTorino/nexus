# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal window with the terminal, downloads and dialogs replaced by fakes."""

from __future__ import annotations

import json

from dataclasses import replace
from html import escape
from pathlib import Path, PurePosixPath

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QMessageBox

from bc250_portal import MANIFEST
from bc250_portal import main_window as mw
from bc250_portal.manifest import load
from bc250_portal.sources import Records, Sources
from bc250_core.updates import ReleaseInfo

YES, CANCEL = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Cancel


class FakeSources(Sources):
    def __init__(self, work: Path):
        super().__init__(work)
        self.prepared: list[str] = []

    def prepare(self, entry):
        self.prepared.append(entry.key)
        folder = self.folder(entry)
        folder.mkdir(parents=True, exist_ok=True)
        return folder


@pytest.fixture
def launched(monkeypatch):
    calls = []
    monkeypatch.setattr(mw, "launch_in_terminal", lambda line, **kw: calls.append((line, kw["exit_file"])))
    return calls


@pytest.fixture
def window(qapp, home, settings_dir, tmp_path, launched):
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    yield w
    w.close()


def wait_for(predicate, ms=5000):
    loop = QEventLoop()
    timer = QTimer()
    timer.timeout.connect(lambda: predicate() and loop.quit())
    timer.start(20)
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    timer.stop()
    return predicate()


def entry_of(window, key):
    return next(e for e in window.entries if e.key == key)


def menu_texts(window, key) -> list[str]:
    return [a.text() for a in window.tile_menu(entry_of(window, key)).actions() if not a.isSeparator()]


def test_bazzite_test_first_without_uninstall(window):
    keys = list(window.states)
    assert keys[0] == "check"
    assert "Uninstall" not in menu_texts(window, "check")
    assert "Uninstall" in menu_texts(window, "gpu")
    assert "Open" in menu_texts(window, "acpi")
    assert menu_texts(window, "compute")[:2] == ["Bisect", "Unlock"]                  # two windows


def test_every_app_has_its_icon(qapp, home, settings_dir, tmp_path, launched):
    entries = load(MANIFEST)
    w = mw.MainWindow(entries, FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    for key, state in w.states.items():
        assert (mw.APP_ICONS / f"{key}.webp").is_file(), key
        assert state.has_icon, key
        assert not w.big.tiles[key].pixmap.isNull(), key
    w.close()


def test_open_menu_shows_each_window_icon(window):
    for key in ("compute", "cores"):
        actions = window.tile_menu(entry_of(window, key)).actions()[:2]
        assert [a.text() for a in actions] == ["Bisect", "Unlock"]
        assert all(not a.icon().isNull() for a in actions), key
        assert (mw.APP_ICONS / f"{mw.LAUNCH_ICON_FILES[(key, 'Unlock')]}.webp").is_file()


def test_an_app_without_an_icon_file_still_has_a_tile(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    monkeypatch.setattr(mw, "APP_ICONS", tmp_path / "no-icons")
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    assert all(not state.has_icon for state in w.states.values())
    assert all(not tile.pixmap.isNull() for tile in w.big.tiles.values())      # the category's icon
    w.close()


def test_short_names_drop_the_suite_prefix(window):
    assert mw.short_name("BC-250 Bazzite Test") == "Bazzite Test"
    assert mw.short_name("BC250 Suite Releases") == "Suite Releases"
    assert mw.short_name("Media Tool") == "Media Tool"
    assert window.states["gpu"].title == "GPU Manager"
    assert "BC-250 GPU Manager" in window.states["gpu"].tooltip     # the full name on hover
    assert window.big.tiles["gpu"].toolTip() == window.states["gpu"].tooltip
    assert window.states["cec"].title == "CEC Manager"
    assert window.states["datstation"].title == "DatStation"                 # apps.toml's short


def test_a_tile_opens_only_an_installed_program(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    entries = [replace(e, launch=()) if e.key == "gpu" else e for e in load(MANIFEST)]
    w = mw.MainWindow(entries, FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    acpi = w.states["acpi"]
    assert not acpi.opens and "Not installed" in acpi.tooltip
    for name in ("bc250-governor-manager", "bc250-persistent-acpi-gui"):
        (home / ".local" / "bin" / name).write_text("#!/bin/sh\n")
    w.refresh()
    assert acpi.opens and "Press it to open it." in acpi.tooltip
    assert not w.states["gpu"].opens                                   # not a program
    assert "Open" not in menu_texts(w, "gpu")
    opened = []
    monkeypatch.setattr(w, "open_app", lambda entry, command: opened.append(command))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: YES)
    w.big.tiles["acpi"].click()
    assert opened == ["~/.local/bin/bc250-persistent-acpi-gui"]
    w.close()


def test_icon_is_greyed_until_installed(window, home):
    tile = window.big.tiles["overlay"]
    grey = tile.pixmap.cacheKey()
    assert grey == window.big.art("utilities", "overlay", False).cacheKey()
    (home / ".local" / "bin" / "bc250-system-overlay").write_text("#!/bin/sh\n")
    window.refresh()
    assert tile.pixmap.cacheKey() == window.big.art("utilities", "overlay", True).cacheKey() != grey


def test_board_warning_under_the_icon(window, home):
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    window.records.set("gpu", entry_of(window, "gpu").tag)
    window.refresh()
    assert window.big.tiles["gpu"].status == "changes the board"
    assert window.big.tiles["gpu"].status_colour == mw.ORANGE
    assert window.big.tiles["overlay"].status == "Not installed"
    # On hover, what the app changes and how that is undone (apps.toml's board_change), in orange
    assert f"<p style='color:{mw.ORANGE};'><b>Changes the board.</b> " + \
        escape(entry_of(window, "gpu").board_change) in window.states["gpu"].tooltip
    assert "Changes the board." not in window.states["overlay"].tooltip


def test_states_follow_detection_and_records(window, home):
    state = window.states["gpu"]
    assert state.status == "Not installed" and state.action == "Install"
    assert "Uninstall" in menu_texts(window, "gpu")
    assert not [a for a in window.tile_menu(state.entry).actions() if a.text() == "Uninstall"][0].isEnabled()
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    window.refresh()
    assert state.status == "Reinstall needed" and state.action == "Reinstall"
    assert [a for a in window.tile_menu(state.entry).actions() if a.text() == "Uninstall"][0].isEnabled()
    window.records.set("gpu", entry_of(window, "gpu").tag)
    window.refresh()
    assert state.status == "Installed" and state.action == "Reinstall"
    window.records.set("gpu", "gpu-v0.0.9")
    window.refresh()
    assert state.status == "Update" and state.action == "Update"


def test_bazzite_test_has_only_reinstall(window, home):
    """With the arrow into a tray, as every app (owner, 14-10-2026), and the version it reinstalls."""
    state = window.states["check"]
    (home / ".local" / "bin" / "bc250-bazzite-test").write_text("#!/bin/sh\n")
    window.records.set("check", state.entry.tag)
    window.refresh()
    assert state.action_tip == f"Reinstall BC-250 Bazzite Test v{state.entry.version}"
    assert menu_texts(window, "check") == ["Open", "Reinstall"]
    assert not state.reinstall
    window.records.set("check", "")                                      # not installed by the portal
    window.refresh()
    assert state.reinstall and window.big.tiles["check"].marker == "reinstall"


def test_board_change_needs_confirmation(window, launched, monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: (asked.append(a[2]), CANCEL)[1])
    window.install(entry_of(window, "acpi"))
    assert asked and "changes how your BC-250 runs" in asked[0]
    assert window.sources.prepared == [] and launched == []                 # canceled: nothing happens


def test_no_warning_for_bazzite_test(window, launched, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail("no board warning expected"))
    window.install(window.entries[0])
    assert wait_for(lambda: launched)
    line, exit_file = launched[0]
    assert line.endswith("&& bash install.sh") and "local-check" not in line
    assert window.pending is not None and window.states["check"].status == "Installing…"
    assert window.big.tiles["check"].status == "Installing…"
    install = [a for a in window.tile_menu(entry_of(window, "gpu")).actions() if a.text() == "Install"][0]
    assert not install.isEnabled()                                      # one action at a time


def test_install_success_records_tag(window, launched, monkeypatch, home):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: YES)
    entry = entry_of(window, "gpu")
    window.install(entry)
    assert wait_for(lambda: launched)
    _, exit_file = launched[0]
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    exit_file.write_text("0\n")
    old = window.sources.work / "gpu-v0.0.9"                          # the release it updates from
    old.mkdir(parents=True)
    window._check_pending()
    assert window.pending is None
    assert window.records.get("gpu") == entry.tag
    assert not old.exists() and window.sources.folder(entry).is_dir()      # only the installed release stays
    assert window.states["gpu"].status == "Installed"


def test_failed_install_warns_and_records_nothing(window, launched, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: YES)
    entry = entry_of(window, "upscaler")
    window.install(entry)
    assert wait_for(lambda: launched)
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    launched[0][1].write_text("1\n")
    window._check_pending()
    assert window.records.get("upscaler") == "" and shown and "exit status 1" in shown[0]


def test_uninstall_forgets_release(window, launched, monkeypatch, home):
    entry = entry_of(window, "upscaler")
    (home / ".local" / "bin" / "bc250-upscaler").write_text("#!/bin/sh\n")
    window.records.set("upscaler", entry.tag)
    window.refresh()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: YES)
    [a for a in window.tile_menu(entry).actions() if a.text() == "Uninstall"][0].trigger()
    assert wait_for(lambda: launched)
    line, exit_file = launched[0]
    assert line.endswith("&& bash install.sh --uninstall")
    exit_file.write_text("0\n")
    window._check_pending()
    assert window.records.get("upscaler") == ""
    assert not window.sources.folder(entry).exists()


def test_closed_terminal_can_be_abandoned(window, launched, monkeypatch):
    window.install(window.entries[0])
    assert wait_for(lambda: launched)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: YES)
    window._on_refresh()
    assert window.pending is None
    assert [a for a in window.tile_menu(entry_of(window, "gpu")).actions() if a.text() == "Install"][0].isEnabled()


def test_shell_line_quotes_folder():
    line = mw.shell_line(PurePosixPath("/tmp/a b"), ("bash x.sh", "bash y.sh"))
    assert line == "cd '/tmp/a b' && bash x.sh && bash y.sh"


def tab_text(window, category: str) -> str:
    return window.big.bar.tabText(window.big.categories.index(category))


def test_red_dot_and_count_for_updates(window, home):
    for name in ("bc250-governor-manager", "bc250-upscaler"):
        (home / ".local" / "bin" / name).write_text("#!/bin/sh\n")
    window.records.set("gpu", "gpu-v0.0.9")              # older than the pin: an update
    window.records.set("upscaler", entry_of(window, "upscaler").tag)   # the pinned one
    window.refresh()
    assert window.states["gpu"].update and window.big.tiles["gpu"].marker == "update"
    assert not window.states["upscaler"].update
    assert "gpu-v0.0.9" in window.states["gpu"].tooltip
    assert window.big.notice.text() == "● 1 update" and window.big.notice.isVisibleTo(window.big)
    assert window.notice_lines == [("gpu", "GPU Manager (Sustainable): update to v"
                                    f"{entry_of(window, 'gpu').version}, installed from gpu-v0.0.9")]
    assert [a.text() for a in window.notice_menu().actions()] == [window.notice_lines[0][1]]
    assert "HelixSR" not in window.big.notice.text()
    assert tab_text(window, "sustainable") == "Sustainable  ● 1"                # the count on its tab
    assert tab_text(window, "graphics") == "Graphics"
    window.records.set("gpu", entry_of(window, "gpu").tag)
    window.refresh()
    assert not window.states["gpu"].update and window.big.notice.isHidden() and window.notice_lines == []
    assert tab_text(window, "sustainable") == "Sustainable"
    assert "No updates" in window.updates_button.toolTip()


def test_the_installed_line_counts_installed_of_listed(qapp, home, settings_dir, tmp_path, launched):
    """Installed apps: installed / listed, a withdrawn app not counted (owner, 21-10-2026)."""
    entries = [replace(e, withdrawn="test") if e.key == "sftp" else e for e in load(MANIFEST)]
    w = mw.MainWindow(entries, FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    listed = len(entries) - 1
    assert w.big.installed.text() == f"0/{listed} installed"
    for name in ("bc250-governor-manager", "bc250-upscaler"):
        (home / ".local" / "bin" / name).write_text("#!/bin/sh\n")
    w.refresh()
    assert w.big.installed.text() == f"2/{listed} installed" and f"2 of the {listed} apps" in w.big.installed.toolTip()
    w.close()


def test_install_all_updates_one_after_the_other(window, launched, monkeypatch, home):
    """Install all updates: one question for every app the notice names (owner, 21-10-2026), with the board warning
    when one changes the board; then each in its own terminal, the next only when the one before ended (an installer
    waiting for the sudo password holds the batch); one message at the end names those that failed."""
    for name in ("bc250-governor-manager", "bc250-upscaler", "bc250-persistent-acpi-gui"):
        (home / ".local" / "bin" / name).write_text("#!/bin/sh\n")
    window.records.set("gpu", "gpu-v0.0.9")                  # an update
    window.records.set("upscaler", "upscaler-v0.0.1")        # an update
    window.refresh()                                         # acpi: installed, not recorded: a reinstall
    keys = [entry.key for entry, _ in window.marked]
    assert set(keys) == {"gpu", "upscaler", "acpi"}
    assert window.big.notice.text() == "● 2 updates, 1 reinstall"
    pill = window.updates_button
    assert pill.badge == "3" and pill.isEnabled() and "all 3" in pill.toolTip()
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a[2]), CANCEL)[1])
    pill.click()
    assert "Install these 3 updates" in asked[0] and "change how your BC-250 runs" in asked[0]   # acpi
    assert window.batch is None and launched == []                          # canceled: nothing happens
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: YES)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail("one question only"))
    pill.click()
    assert wait_for(lambda: len(launched) == 1)
    assert window.sources.prepared == [keys[0]] and pill.badge == "1/3" and not pill.isEnabled()
    # Its installer waits for the password: no exit file yet, so the batch waits too.
    window._check_pending()
    assert window.pending is not None and len(launched) == 1
    launched[0][1].write_text("0\n")
    window._check_pending()
    assert wait_for(lambda: len(launched) == 2) and window.records.get(keys[0]) != ""
    launched[1][1].write_text("1\n")                          # a failure: the batch goes on
    window._check_pending()
    assert wait_for(lambda: len(launched) == 3) and pill.badge == "3/3"
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    launched[2][1].write_text("0\n")
    window._check_pending()
    assert window.batch is None and not window.busy() and window.sources.prepared == keys
    assert len(shown) == 1 and "1 of the 3 updates did not install" in shown[0] and "exit status 1" in shown[0]
    failed = entry_of(window, keys[1])
    assert failed.name in shown[0] and [e.key for e, _ in window.marked] == [keys[1]]
    assert pill.badge == "1" and pill.isEnabled() and "1 the notice names" in pill.toolTip()


def test_stop_waiting_ends_the_batch(window, launched, monkeypatch, home):
    for name in ("bc250-governor-manager", "bc250-upscaler"):
        (home / ".local" / "bin" / name).write_text("#!/bin/sh\n")
    window.records.set("gpu", "gpu-v0.0.9")
    window.records.set("upscaler", "upscaler-v0.0.1")
    window.refresh()
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: YES)
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a[2]), YES)[1])
    window.install_all()
    assert wait_for(lambda: launched)
    window._on_refresh()                                     # its terminal was closed
    assert "The rest of the batch (1) is not installed then." in asked[-1]
    assert window.batch is None and window.pending is None and len(launched) == 1
    assert window.updates_button.badge == "2" and window.updates_button.isEnabled()


def test_install_all_apps_is_a_symbol_that_fills_the_open_category(window, launched, monkeypatch, qapp):
    """Install all apps (owner, 26-10-2026; in the header since the tabs went, 01-11-2026, a big symbol since
    05-11-2026, the number of apps of the open category not installed yet in its tooltip). A click installs them as
    one batch with one question; its badge shows the batch's progress; it is disabled once every app of the category
    is installed."""
    pill = window.apps_button
    expected = [e for e in window.entries if e.category == "sustainable"]
    assert window.shown_category() == "sustainable" and window.missing("sustainable") == expected
    assert pill.badge == "" and pill.toolTip().startswith("Install all apps.") and pill.isEnabled()
    assert f"all {len(expected)} apps on Sustainable" in pill.toolTip()
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a[2]), CANCEL)[1])
    pill.click()
    assert f"Install these {len(expected)} apps on Sustainable" in asked[0] and "change how your BC-250 runs" in asked[0]
    assert "Fan Control" in asked[0] and "Upscaler" not in asked[0]
    assert window.batch is None and launched == []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: YES)
    pill.click()
    assert wait_for(lambda: len(launched) == 1)
    assert window.sources.prepared == [expected[0].key]
    assert pill.badge == f"1/{len(expected)}" and not pill.isEnabled()
    assert window.updates_button.badge == "" and not window.updates_button.isEnabled()
    done: set[str] = set()                                   # some detect paths are under /opt: not writable here
    monkeypatch.setattr(mw, "is_installed", lambda entry: entry.key in done)
    for i, entry in enumerate(expected):
        launched[i][1].write_text("0\n")
        done.add(entry.key)
        window._check_pending()
        if i + 1 < len(expected):
            assert wait_for(lambda: len(launched) == i + 2)
    assert window.batch is None and not window.busy()
    assert window.sources.prepared == [e.key for e in expected]
    assert pill.badge == "" and not pill.isEnabled()
    assert pill.toolTip() == "Install all apps. Every app on Sustainable is installed."
    window.big.bar.setCurrentIndex(window.big.categories.index("graphics"))
    assert pill.isEnabled() and "on Graphics" in pill.toolTip()
    window.big.bar.setCurrentIndex(0)
    pill.click()
    assert window.batch is None and len(launched) == len(expected)         # disabled: nothing happens


def test_no_updates_no_batch(window, launched):
    assert window.updates_button.badge == "" and not window.updates_button.isEnabled()
    assert "No updates" in window.updates_button.toolTip()
    window.install_all()
    assert window.batch is None and launched == []


def test_updates_outside_the_suite(window, home):
    """In orange beside the category strip, and on the app's tile (owner, 01-11-2026: the notice is a menu)."""
    from bc250_core import upstream
    helix = upstream.Outside("HelixSR", "1.8.1", "1.9.3", "2026-10-16", "https://x/v1.9.3",
                             "Get HelixSR… on the Setup page updates it.")
    upstream.publish("upscaler", [helix])
    upstream.publish("pcsx2", [upstream.Outside("PCSX2 nightly", "2.9.127", "2.9.128")])
    window.refresh()
    assert window.big.outside.isHidden() and window.outside_lines == []       # neither app is installed
    (home / ".local" / "bin" / "bc250-upscaler").write_text("#!/bin/sh\n")
    window.records.set("upscaler", entry_of(window, "upscaler").tag)
    window.refresh()
    assert window.big.notice.isHidden() and window.big.outside.text() == "● 1 outside the suite"
    assert window.outside_lines == [("upscaler", "Upscaler Manager (Graphics): HelixSR 1.9.3 is out (2026-10-16), "
                                     "installed 1.8.1. Get HelixSR… on the Setup page updates it.")]
    assert [a.text() for a in window.outside_menu().actions()] == [window.outside_lines[0][1]]
    assert "Outside the suite" in window.big.outside.toolTip()
    tile = window.big.tiles["upscaler"]
    assert tile.status == "HelixSR 1.9.3 is out" and tile.status_colour == mw.ORANGE
    assert not any("●" in tab_text(window, c) for c in window.big.categories)   # the dots are the suite's updates
    # Beside an update of the suite's own:
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    window.records.set("gpu", "gpu-v0.0.9")
    window.refresh()
    assert window.big.notice.text() == "● 1 update" and window.big.outside.text() == "● 1 outside the suite"
    assert window.big.tiles["gpu"].status == "Update"                     # the suite's update comes first
    # The app found nothing more to install; the portal sees it when its window is active again.
    upstream.publish("upscaler", [])
    window.show_notice(window.marked)
    assert window.big.outside.isHidden() and tile.status == ""


def test_circular_arrow_and_count_for_reinstalls(window, home):
    # Installed but not recorded: by hand, or under an earlier key that RENAMED does not know (shadps4 became
    # shadps4-manager before RENAMED existed).
    for name in ("bc250-governor-manager", "bc250-upscaler"):
        (home / ".local" / "bin" / name).write_text("#!/bin/sh\n")
    window.records.set("upscaler", "upscaler-v0.0.1")                          # an update, for the count
    window.refresh()
    state = window.states["gpu"]
    assert state.status == "Reinstall needed" and state.reinstall and not state.update
    assert "Reinstall needed" in state.tooltip and "version is unknown" in state.tooltip
    assert state.action_tip.startswith("Reinstall ") and window.big.tiles["gpu"].marker == "reinstall"
    assert not window.states["upscaler"].reinstall and window.states["upscaler"].update
    assert window.big.notice.text() == "● 1 update, 1 reinstall"
    assert ("gpu", "GPU Manager (Sustainable): reinstall needed, its version is unknown") in window.notice_lines
    window.records.remove("upscaler")
    (home / ".local" / "bin" / "bc250-upscaler").unlink()
    window.refresh()
    assert window.big.notice.text() == "● 1 reinstall"
    window.records.set("gpu", entry_of(window, "gpu").tag)
    window.refresh()
    assert not state.reinstall and state.status == "Installed" and window.big.notice.isHidden()


def test_not_installed_and_withdrawn_need_no_reinstall(qapp, home, settings_dir, tmp_path, launched):
    entries = [replace(e, withdrawn="test") if e.key == "gpu" else e for e in load(MANIFEST)]
    w = mw.MainWindow(entries, FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    w.refresh()
    assert not w.states["gpu"].reinstall                                # the portal removes it instead
    assert not w.states["overlay"].reinstall                             # not installed
    w.close()


def test_local_build_banner(qapp, home, settings_dir, tmp_path, launched, window):
    assert window.big.banner.isHidden()                         # a published release: no banner
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                      local_build=Path("/home/me/bc250-bazzite-suite"))
    assert not w.big.banner.isHidden()
    assert "checkout /home/me/bc250-bazzite-suite" in w.big.banner.text()
    w.close()


def portal_window(tmp_path, release):
    return mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                         portal_check=lambda: release)


def test_newer_portal_release_is_offered(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    """The orange banner beside the category strip (owner, 04-11-2026, as the Windows Portable Suite's portal); a
    click on it updates the portal, as Y does."""
    release = ReleaseInfo(version="99.0.0", tag="portal-v99.0.0", url="https://example.invalid/r", published="2030-01-01")
    w = portal_window(tmp_path, release)
    banner = w.big.update_banner
    assert wait_for(lambda: not banner.isHidden())
    assert banner.text() == "UPDATE AVAILABLE, PRESS Y TO UPDATE"
    assert "Portal 99.0.0 is available. Released 2030-01-01." in banner.toolTip() and "Press Y" in banner.toolTip()
    assert banner in w.big.controls                                     # the focus reaches it, Enter presses it
    started = []
    monkeypatch.setattr(w, "install_portal_update", lambda: started.append(1))
    banner.click()
    assert started == [1]
    w._gamepad_action("update")                                         # Y, on any tile or none
    assert started == [1]                                               # not while the window is not active
    monkeypatch.setattr(mw.QApplication, "activeWindow", staticmethod(lambda: w))
    w._gamepad_action("update")
    assert started == [1, 1]
    w.close()


def test_a_new_build_of_this_version_is_offered(qapp, home, settings_dir, tmp_path, launched):
    """A release built again under the portal's own version (owner, 03-11-2026): offered when its tarball's sha256
    differs from the build this portal came from; not from a checkout, not for the same build."""
    from bc250_portal import __version__
    from bc250_portal.portal_update import PortalUpdate
    same = ReleaseInfo(version=__version__, tag=f"portal-v{__version__}", url="https://example.invalid/r")
    update = PortalUpdate(same, [], "a" * 64)
    for build, shown in ((None, False), ("a" * 64, False), ("b" * 64, True), ("", True)):
        w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                          portal_check=lambda: update, build=build)
        assert wait_for(lambda: not w.portal_checker.running, 3000)
        assert w.big.update_banner.isHidden() is not shown, build
        if shown:
            assert w.big.update_banner.toolTip().startswith(f"Portal {__version__}: a new build of this version.")
        w.close()
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                      portal_check=lambda: PortalUpdate(same, [], ""), build="b" * 64)   # no SHA256SUMS: no offer
    assert wait_for(lambda: not w.portal_checker.running, 3000) and w.big.update_banner.isHidden()
    w.close()


def test_a_download_counts_its_megabytes(window, tmp_path):
    """The tile says how far a download is (owner, 03-11-2026: Downloading… for a 90 MB release looked like a hang):
    the part file's size, read every PROGRESS_MS while the job runs."""
    entry = entry_of(window, "gpu")
    part = tmp_path / "work" / f".{entry.tag}.part" / entry.asset
    window._job = (entry, "install")
    window.refresh()
    assert window.states["gpu"].busy == "Downloading…"
    part.parent.mkdir(parents=True)
    with part.open("wb") as fh:
        fh.truncate(40_000_000)
    window.refresh()
    assert window.states["gpu"].busy == "Downloading… 40 MB"
    window._job = None
    window.refresh()
    assert window.states["gpu"].busy == ""


def test_the_exit_asks_nothing(window, monkeypatch):
    """Escape (B) and the close symbol close the portal without a question (owner, 12-11-2026). Only while a download
    or an install runs they ask, No the default, and say what exiting does to it."""
    closed, asked = [], []
    window.close = lambda: closed.append(1)
    answer = [QMessageBox.StandardButton.No]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a), answer[0])[1])
    window.escape()
    assert closed == [1] and asked == [] and window.exit_confirmed
    window.close_button.click()
    assert closed == [1, 1] and asked == []
    window.big.show_settings(True)
    window.escape()                                             # on the Settings page B goes back ...
    assert closed == [1, 1] and not window.big.in_settings()
    window.big.show_settings(True)
    window.close_button.click()                                 # ... and the close symbol closes
    assert closed == [1, 1, 1]
    window.big.show_settings(False)
    window._job = (entry_of(window, "gpu"), "install")
    window.escape()
    assert closed == [1, 1, 1] and asked[-1][2] == mw.EXIT_QUESTION + "\n\nThe download stops."
    assert asked[-1][3] == QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    assert asked[-1][4] == QMessageBox.StandardButton.No
    answer[0] = YES
    window.close_button.click()
    assert closed == [1, 1, 1, 1] and len(asked) == 2
    window._job = None


def test_the_desktops_close_asks_only_while_something_runs(window, monkeypatch):
    from PyQt6.QtGui import QCloseEvent
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a), QMessageBox.StandardButton.No)[1])
    window._job = (entry_of(window, "gpu"), "install")
    event = QCloseEvent()
    monkeypatch.setattr(event, "spontaneous", lambda: True)
    window.closeEvent(event)
    assert asked and not event.isAccepted()
    asked.clear()
    window._job = None
    event = QCloseEvent()
    monkeypatch.setattr(event, "spontaneous", lambda: True)
    window.closeEvent(event)                                    # Alt+F4 with nothing running: no question
    assert asked == [] and event.isAccepted()


def test_a_shortcut_starts_its_program(window, monkeypatch):
    """The header's shortcuts (owner, 12-11-2026): the file manager, Steam, YouTube in Brave Browser, and the
    desktop's Bluetooth, network, sound and display settings. One whose program is missing says what is needed and
    starts nothing."""
    from bc250_portal import shortcuts
    started, raised, said = [], [], []
    window.launch = lambda argv: (started.append(argv), True)[1]
    monkeypatch.setattr(window.raiser, "bring_to_front", lambda ids, pids=(): raised.append(tuple(ids)))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: said.append(a[2]))
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: said.append(a[2]))
    monkeypatch.setattr(shortcuts.shutil, "which", lambda name: f"/usr/bin/{name}")
    flatpaks = [0]
    monkeypatch.setattr(shortcuts.subprocess, "run",
                        lambda argv, **kw: shortcuts.subprocess.CompletedProcess(argv, flatpaks[0], "", ""))
    for button in window.shortcut_buttons:
        button.click()
    assert started == [["xdg-open", str(Path.home())], ["steam"],
                       ["flatpak", "run", "com.brave.Browser", "--kiosk", "https://www.youtube.com/"],
                       ["systemsettings", "kcm_bluetooth"], ["systemsettings", "kcm_networkmanagement"],
                       ["systemsettings", "kcm_pulseaudio"], ["systemsettings", "kcm_kscreen"]]
    assert raised[1] == ("steam",) and len(raised) == 7 and said == []
    started.clear()
    flatpaks[0] = 1                                             # Brave Browser is not installed
    window.youtube_button.click()
    assert started == [] and "Brave Browser is required" in said[-1]
    monkeypatch.setattr(shortcuts.shutil, "which", lambda name: None)
    window.steam_button.click()
    window.bluetooth_button.click()
    assert started == [] and "Steam is not installed" in said[-2] and "Bluetooth settings" in said[-1]
    window.volume_button.click()
    window.screen_button.click()
    assert started == [] and "sound settings" in said[-2] and "display settings" in said[-1]
    monkeypatch.setattr(shortcuts.shutil, "which", lambda name: f"/usr/bin/{name}")
    window.launch = lambda argv: False
    window.files_button.click()
    assert "could not be started" in said[-1]


def test_a_key_for_each_controller_action(window, monkeypatch):
    """Steam's desktop layout turns a pad's buttons into keys (owner, 05-11-2026): U, S, K and M do what Y, ☰, R3 and
    X do, for the buttons it gives no key of their own."""
    done = []
    monkeypatch.setattr(window, "act", done.append)
    for shortcut in window.action_shortcuts:
        shortcut.activated.emit()
    assert [s.key().toString() for s in window.action_shortcuts] == ["U", "S", "K", "M"]
    assert done == ["update", "settings", "keyboard", "menu"]
    assert sorted(mw.ACTION_KEYS.values()) == ["keyboard", "menu", "settings", "update"]


def test_the_s_key_opens_the_settings(window):
    window.act("settings")
    assert window.big.in_settings()
    window.act("settings")
    assert not window.big.in_settings()


def test_the_arrow_keys_move_between_a_questions_buttons(window, qapp):
    """With Steam's desktop layout a controller is the arrow keys and Enter: Qt's questions take them as they are."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    box = QMessageBox(QMessageBox.Icon.Question, "Portal", mw.EXIT_QUESTION,
                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, window)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    box.show()
    qapp.processEvents()
    no, yes = box.button(QMessageBox.StandardButton.No), box.button(QMessageBox.StandardButton.Yes)
    no.setFocus()
    qapp.processEvents()
    for key, now in ((Qt.Key.Key_Left, yes), (Qt.Key.Key_Right, no), (Qt.Key.Key_Up, yes)):
        QTest.keyClick(qapp.focusWidget(), key)
        qapp.processEvents()
        assert qapp.focusWidget() is now
    clicked = []
    box.buttonClicked.connect(clicked.append)
    QTest.keyClick(yes, Qt.Key.Key_Return)                              # Enter (A) presses the focused button
    assert clicked == [yes]
    box.close()


@pytest.mark.parametrize("release", [ReleaseInfo(version="0.0.1", tag="portal-v0.0.1"),
                                     ReleaseInfo(error="no connection (offline)"), ReleaseInfo()])
def test_no_portal_offer_when_not_newer_or_offline(qapp, home, settings_dir, tmp_path, launched, release):
    w = portal_window(tmp_path, release)
    assert wait_for(lambda: not w.portal_checker.running, 3000)
    assert w.big.update_banner.isHidden() and w.portal_update is None
    w.close()


def test_tiles_flow_in_file_order(window, qapp):
    window.show()
    big = window.big
    for category in ("sustainable", "gaming"):
        big.bar.setCurrentIndex(big.categories.index(category))
        tiles = [big.tiles[e.key] for e in window.entries if e.category == category]
        for width in (1400, 700, 1400):
            window.resize(width, 900)
            qapp.processEvents()
            columns = big.columns[category]
            grid = big.grids[category]
            places = [grid.getItemPosition(grid.indexOf(tile))[:2] for tile in tiles]
            assert places == [(i // columns, i % columns) for i in range(len(tiles))], width   # file order, by rows


def test_a_category_per_tab_in_order(window):
    assert [window.big.bar.tabText(i) for i in range(window.big.bar.count())] == [
        "Sustainable", "Graphics", "Gaming", "Utilities"]                   # no Development, no action tab
    assert window.big.categories == ["sustainable", "graphics", "gaming", "utilities"]
    for key, tile in window.big.tiles.items():
        inside = [c for c, grid in window.big.grids.items() if grid.indexOf(tile) >= 0]
        assert inside in ([window.states[key].entry.category], []), key    # laid out once its category opens
    assert {k for k, s in window.states.items() if s.entry.category == "graphics"} == {"upscaler", "ace", "mesh"}
    assert window.big.bar.currentIndex() == 0                               # the first category, the first time


def test_bazzite_test_is_the_first_tile_on_sustainable(window):
    """Bazzite Test is pinned as the first tile on Sustainable (owner, 20-10-2026)."""
    assert window.big.current_tiles()[0] is window.big.tiles["check"]
    assert window.big.grids["sustainable"].itemAtPosition(0, 0).widget() is window.big.tiles["check"]


def test_the_portal_always_opens_on_the_first_category(qapp, home, settings_dir, tmp_path, launched):
    """Whatever category was open last (owner, 20-10-2026)."""
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    w.big.bar.setCurrentIndex(w.big.categories.index("gaming"))
    w.close()
    again = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    assert again.big.bar.currentIndex() == 0 and again.big.current_category() == "sustainable"
    again.close()


def test_a_line_of_the_notice_goes_to_the_tile_of_its_app(window, home, qapp):
    window.show()
    qapp.processEvents()
    (home / ".local" / "bin" / "bc250-rpcs3-manager").write_text("#!/bin/sh\n")
    window.records.set("rpcs3", "rpcs3-v0.0.1")
    window.refresh()
    assert window.notice_lines[0][0] == "rpcs3" and "RPCS3 Manager (Gaming)" in window.notice_lines[0][1]
    window.notice_menu().actions()[0].trigger()
    assert window.big.current_category() == "gaming" and window.focusWidget() is window.big.tiles["rpcs3"]
    window.show_app("check")                                                    # on Sustainable
    assert window.big.current_category() == "sustainable" and window.focusWidget() is window.big.tiles["check"]


def test_the_tools_of_the_development_tab_are_utilities(window):
    """No Development tab (owner, 27-10-2026)."""
    assert "development" not in window.big.categories
    assert "package" not in window.states                         # Nexus Deps, a Nexus app since 07-11-2026
    assert window.big.bar.tabToolTip(window.big.categories.index("utilities")) == mw.CATEGORY_HINTS["utilities"]


def test_no_category_without_its_apps(qapp, home, settings_dir, tmp_path, launched):
    entries = [e for e in load(MANIFEST) if e.category != "gaming"]
    w = mw.MainWindow(entries, FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    assert w.big.categories == ["sustainable", "graphics", "utilities"]
    w.close()


def test_portal_offer_names_the_app_updates(qapp, home, settings_dir, tmp_path, launched):
    from bc250_portal.portal_update import AppChange, PortalUpdate
    release = ReleaseInfo(version="99.0.0", tag="portal-v99.0.0", url="https://example.invalid/r", published="2030-01-01")
    update = PortalUpdate(release, [AppChange("BC-250 ACE Queues", "0.1.0", "0.1.1"),
                                    AppChange("BC-250 Memory Manager", "0.1.0", "0.1.1")])
    w = portal_window(tmp_path, update)
    assert wait_for(lambda: not w.big.update_banner.isHidden())
    tip = w.big.update_banner.toolTip()
    assert tip.startswith("Portal 99.0.0: updates ACE Queues and Memory Manager.")
    assert "App updates come with the portal" in tip and "BC-250 Memory Manager: 0.1.0 → 0.1.1" in tip
    w.close()
    same = portal_window(tmp_path, PortalUpdate(release, []))
    assert wait_for(lambda: not same.big.update_banner.isHidden())
    assert "same app versions" in same.big.update_banner.toolTip()
    same.close()


def _portal_tarball(folder: Path, tag: str) -> Path:
    import tarfile
    source = folder / "src" / tag
    source.mkdir(parents=True)
    (source / "install.sh").write_text("#!/bin/sh\n")
    archive = folder / f"{tag}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(source, arcname=tag)
    return archive


def test_y_downloads_checks_and_installs_the_portal_then_restarts(qapp, home, settings_dir, tmp_path, launched,
                                                                  monkeypatch):
    """Y (or a right click, or the banner) while a newer portal is out (owner, 04-11-2026, as the Windows Portable
    Suite's portal): its tarball downloaded and checked, unpacked with the tarball beside it (install.sh records the
    build), its install.sh run in a terminal, and the new portal started when that ended well."""
    import hashlib
    import shutil
    from bc250_portal.portal_update import PortalUpdate
    tag = "portal-v99.0.0"
    archive = _portal_tarball(tmp_path, tag)
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    started = []
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                      launch=lambda argv: (started.append(argv), True)[1])
    asked = []
    w.sources.download = lambda url, dest: (asked.append(url), shutil.copy(archive, dest))
    w._portal_checked(PortalUpdate(ReleaseInfo("99.0.0", tag, "https://example.invalid/r"), [], sha))
    monkeypatch.setattr(mw.QApplication, "activeWindow", staticmethod(lambda: w))
    w.pending = object()                                     # an app installs: the portal waits for it
    told = []
    monkeypatch.setattr(mw.QMessageBox, "information", lambda *a, **k: told.append(a[2]))
    w._gamepad_action("update")
    assert told == [mw.WAIT_UPDATE] and asked == []
    w.pending = None
    w._gamepad_action("update")
    assert w.portal_stage == "download" and w.busy()
    assert wait_for(lambda: w.portal_stage == "install")
    assert asked == [f"{w.sources.repo_url}/releases/download/{tag}/{tag}.tar.gz"]    # its sha256 was known
    folder = w.portal_work() / tag
    assert (folder / "install.sh").is_file() and (w.portal_work() / f"{tag}.tar.gz").is_file()
    line, exit_file = launched[-1]
    assert line == f"cd {folder} && ./install.sh"
    assert w.big.update_banner.text() == "INSTALLING THE UPDATE…"
    exit_file.write_text("0\n")
    w._check_portal_install()
    assert started == [["sh", "-c", 'sleep 1; exec "$0"', str(home / ".local" / "bin" / "bc250-bazzite-suite")]]
    w.close()


def test_a_portal_update_that_fails_says_so(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    import shutil
    from bc250_portal.portal_update import PortalUpdate
    tag = "portal-v99.0.0"
    archive = _portal_tarball(tmp_path, tag)
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                      launch=lambda argv: True)
    w.sources.download = lambda url, dest: shutil.copy(archive, dest)
    w._portal_checked(PortalUpdate(ReleaseInfo("99.0.0", tag, "https://example.invalid/r"), [], "0" * 64))
    errors = []
    monkeypatch.setattr(mw.QMessageBox, "critical", lambda *a, **k: errors.append(a[2]))
    w.portal_update_action()
    assert wait_for(lambda: not w.portal_stage)
    assert "does not match its checksum" in errors[0] and launched == []
    assert w.big.update_banner.text() == "UPDATE AVAILABLE, PRESS Y TO UPDATE"   # Y tries again
    w.portal_update = PortalUpdate(w.portal_update.release, [], "")         # the sha256 from SHA256SUMS then
    sums = tmp_path / "SHA256SUMS"
    import hashlib
    sums.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {tag}.tar.gz\n")
    w.sources.download = lambda url, dest: shutil.copy(sums if url.endswith("SHA256SUMS") else archive, dest)
    w.portal_update_action()
    assert wait_for(lambda: w.portal_stage == "install")
    warned = []
    monkeypatch.setattr(mw.QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    launched[-1][1].write_text("1\n")
    w._check_portal_install()
    assert "exit status 1" in warned[0] and not w.portal_stage and not w.big.update_banner.isHidden()
    w.close()


def icons_window(tmp_path, desktop, names=("bc250-hdmi-cec.desktop", "bc250-governor-manager.desktop")):
    menu = tmp_path / "applications"
    menu.mkdir(exist_ok=True)
    for name in ("bc250-bazzite-suite.desktop", *names):
        (menu / name).write_text("[Desktop Entry]\n")
        (desktop / name).write_text("[Desktop Entry]\n")
    return mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                         desktop=desktop, menu=menu)


def test_first_start_asks_about_app_icons(qapp, home, settings_dir, tmp_path, launched, desktop, monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a[2]),
                                                                  QMessageBox.StandardButton.No)[1])
    w = icons_window(tmp_path, desktop)
    w.settle_icons()
    assert len(asked) == 1 and "Keep the app icons on the Desktop?" in asked[0]
    assert sorted(p.name for p in desktop.iterdir()) == ["bc250-bazzite-suite.desktop"]     # the portal's stays
    assert not w.icons_box.isChecked()
    w.settle_icons()
    assert len(asked) == 1                                                                   # asked once
    w.icons_box.setChecked(True)
    assert (desktop / "bc250-hdmi-cec.desktop").is_file() and (desktop / "bc250-governor-manager.desktop").is_file()
    w.close()


def test_keeping_the_icons(qapp, home, settings_dir, tmp_path, launched, desktop, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: YES)
    w = icons_window(tmp_path, desktop)
    w.settle_icons()
    assert w.icons_box.isChecked() and (desktop / "bc250-hdmi-cec.desktop").is_file()
    w.close()


def test_no_question_without_app_icons(qapp, home, settings_dir, tmp_path, launched, desktop, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("nothing to ask"))
    w = icons_window(tmp_path, desktop, names=())
    w.settle_icons()
    assert not w.icons_box.isChecked()
    w.close()


def test_an_install_with_icons_off_removes_the_new_icon(qapp, home, settings_dir, tmp_path, launched, desktop,
                                                        monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    w = icons_window(tmp_path, desktop)
    w.settle_icons()
    entry = next(e for e in w.entries if e.key == "cec")
    w.install(entry)
    assert wait_for(lambda: launched)
    (desktop / "bc250-hdmi-cec.desktop").write_text("[Desktop Entry]\n")                   # the installer's icon
    launched[0][1].write_text("0\n")
    w._check_pending()
    assert not (desktop / "bc250-hdmi-cec.desktop").exists() and (desktop / "bc250-bazzite-suite.desktop").exists()
    w.close()


def _withdrawn_window(home, tmp_path, installed: bool):
    entries = [replace(e, withdrawn="Privacy: shows the account ID.") if e.key == "upscaler" else e
               for e in load(MANIFEST)]
    if installed:
        (home / ".local" / "bin" / "bc250-upscaler").write_text("#!/bin/sh\n")
    return mw.MainWindow(entries, FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))


def test_a_withdrawn_app_is_not_available(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    w = _withdrawn_window(home, tmp_path, installed=False)
    try:
        state = w.states["upscaler"]
        assert state.status == "App not available" and w.big.tiles["upscaler"].status == "App not available"
        assert w.big.tiles["upscaler"].status_colour == mw.RED
        install = [a for a in w.tile_menu(state.entry).actions() if a.text() == "Install"][0]
        assert not install.isEnabled() and "Privacy: shows the account ID." in install.toolTip()
        assert "It cannot be installed." in state.tooltip
        assert w.states["gpu"].status != "App not available"
        w.remove_withdrawn()                                # not installed: nothing to remove
        assert launched == []
        w.big.tiles["upscaler"].click()                     # nothing to open or install
        assert launched == [] and w.sources.prepared == []
    finally:
        w.close()


def test_the_portal_removes_a_withdrawn_app(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    told = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: told.append(a[2]))
    w = _withdrawn_window(home, tmp_path, installed=True)
    try:
        assert wait_for(lambda: launched)                   # at start, after telling why
        assert told and "is not available any more" in told[0] and "Privacy: shows the account ID." in told[0]
        line, exit_file = launched[0]
        assert line.endswith("&& bash install.sh --uninstall")
        state = w.states["upscaler"]
        assert not state.opens and not state.update          # no opening, no update
        (home / ".local" / "bin" / "bc250-upscaler").unlink()
        exit_file.write_text("0\n")
        w._check_pending()
        assert state.status == "App not available" and "It cannot be installed." in state.tooltip
        w.remove_withdrawn()
        assert len(launched) == 1 and len(told) == 1        # removed: not again
    finally:
        w.close()


def test_a_withdrawn_app_that_could_not_be_removed_stays_removable(qapp, home, settings_dir, tmp_path, launched,
                                                                     monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    w = _withdrawn_window(home, tmp_path, installed=True)
    try:
        assert wait_for(lambda: launched)
        launched[0][1].write_text("1\n")
        w._check_pending()
        assert warned and "exit status 1" in warned[0]
        state = w.states["upscaler"]
        uninstall = [a for a in w.tile_menu(state.entry).actions() if a.text() == "Uninstall"][0]
        assert uninstall.isEnabled()                        # the user can try again by hand
        assert "The portal removes it from the board." in state.tooltip
        assert len(launched) == 1                           # tried once per start, not in a loop
    finally:
        w.close()


def _installed(tmp_path, version: str) -> Path:
    link = tmp_path / "opt" / "bc250-bazzite-suite"
    link.mkdir(parents=True, exist_ok=True)
    (link / "VERSION").write_text(version + "\n")
    return link


def test_restart_into_a_portal_installed_meanwhile(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    started = []
    link = _installed(tmp_path, mw.__version__)
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                      installed=link, launch=lambda argv: (started.append(argv), True)[1])
    assert w.restart_button.isHidden()                                      # the one installed is this one
    w._portal_checked(ReleaseInfo("99.0.0", "portal-v99.0.0", "https://example.invalid", "2026-10-14"))
    assert not w.big.update_banner.isHidden()
    _installed(tmp_path, "99.0.0")                                           # its install.sh ran in a terminal
    w.refresh()
    assert w.restart_button.text() == "● Restart: portal 99.0.0 is installed"
    assert w.restart_button.isEnabled() and w.big.update_banner.isHidden()   # the newer portal is here already
    w.pending = object()                                                     # an install runs: wait for it
    w.check_installed()
    assert not w.restart_button.isEnabled() and "running now" in w.restart_button.toolTip()
    w.restart_portal()
    assert started == []
    w.pending = None
    w.restart_portal()
    assert started == [["sh", "-c", 'sleep 1; exec "$0"', str(home / ".local" / "bin" / "bc250-bazzite-suite")]]
    assert not w.isVisible()


def test_restart_that_cannot_start(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                      installed=_installed(tmp_path, "99.0.0"), launch=lambda argv: False)
    w.show()
    w.restart_portal()
    assert "could not be started again" in warned[0] and w.isVisible()
    w.close()


def test_no_restart_from_a_checkout(window):
    from bc250_portal import installed_copy
    assert installed_copy() is None and window.installed is None and window.restart_button.isHidden()


def test_one_theme_for_every_app(window, home):
    """The theme pill shows the chosen theme; a click takes the next one, for every app; its tooltip says when it
    shows."""
    from bc250_core import theme
    pill = window.theme_pill
    assert theme.theme_name() == "gunmetal" and pill.value.text() == "Gunmetal"
    assert pill.caption.text() == "Theme switcher" and "next time it starts" in pill.toolTip()
    seen = []
    for _ in range(3):
        pill.click()
        seen.append((theme.theme_name(), pill.value.text()))
    assert seen == [("silver", "Silver"), ("warm", "Warm"), ("gunmetal", "Gunmetal")]
    assert theme.theme_file().is_relative_to(home)


def test_the_header_is_an_apps_header_with_symbols(window):
    """The suite's icon, spanning the name, ☰ and the close symbol at the top right and the row of big symbols
    (owner, 05-11-2026, in place of the pills): Refresh, Sys info, Install all apps and Install all updates, then the
    shortcuts (owner, 12-11-2026): Files, Steam, YouTube, Bluetooth, Network, Volume and Screen, what each does in
    its tooltip; on their right the installed count over the status. The Desktop
    icons, Sound, the theme, the wallpaper, the clock and the weather on the Settings page behind ☰ (owner,
    04-11-2026 and 05-11-2026)."""
    symbols = window.header_buttons
    listed = len(window.entries)
    sound = "Yes" if window.sounds.available() else "No"             # No on a machine without an audio output
    assert symbols == [window.refresh_button, window.sysinfo_button, window.apps_button, window.updates_button,
                       window.files_button, window.steam_button, window.youtube_button, window.bluetooth_button,
                       window.network_button, window.volume_button, window.screen_button]
    assert window.big.status.weather.isHidden()                         # no place chosen: no weather
    corner = [window.settings_button, window.close_button]
    assert all(isinstance(s, mw.SymbolButton) for s in [*symbols, *corner])
    assert [s.toolTip().split(":")[0].split(".")[0] for s in [*symbols, *corner]] == [
        "Refresh", "Sys info", "Install all apps", "Install all updates", "Files", "Steam", "YouTube", "Bluetooth",
        "Network", "Volume", "Screen", "Settings", "Exit"]
    assert [window.big.symbol_row.indexOf(s) for s in symbols] == list(range(11))
    upper = window.big.upper                                            # the top right: ☰, then the close symbol
    assert [upper.indexOf(s) for s in corner] == [upper.count() - 2, upper.count() - 1]
    assert window.big.installed.text() == f"0/{listed} installed"
    assert " | " in window.big.status.text()
    assert [(p.value.text(), p.caption.text()) for p in window.setting_pills] == [
        ("No", "Icons on Desktop"), (sound, "Sound"), ("Gunmetal", "Theme switcher"), ("None", "Wallpaper"),
        ("12 h", "Clock"), ("None", "Weather"), ("100 %", "Touchpad")]
    assert "verified by checksum" in window.source_text


def test_the_sys_info_symbol_opens_one_window_read_each_time(window, qapp, monkeypatch):
    """Sys info (owner, 20-10-2026): a small window with what the system reports, read again each time it opens;
    Copy puts it on the clipboard as text."""
    reads = iter([[("Board", [("Board", "ASRock AMD BC-250")])],
                  [("Board", [("Board", "ASRock AMD BC-250")]), ("BIOS", [("Version", "P5.00")])]])
    monkeypatch.setattr(mw.sysinfo, "collect", lambda: next(reads))
    window.sysinfo_button.click()
    first = window.sysinfo_window
    assert first.isVisible() and [h for h, _ in first.sections] == ["Board"]
    from PyQt6.QtCore import Qt
    assert first.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)    # semi-transparent (owner, 20-10-2026)
    picture = first.grab().toImage()
    assert picture.pixelColor(2, 2).alphaF() == pytest.approx(mw.SYSINFO_OPACITY / 100, abs=0.01)
    window.sysinfo_button.click()
    assert window.sysinfo_window is first and [h for h, _ in first.sections] == ["Board", "BIOS"]
    first.copy()
    assert qapp.clipboard().text() == "Board\n  Board: ASRock AMD BC-250\nBIOS\n  Version: P5.00"
    first.close()


def test_the_wallpaper(window, home, tmp_path, monkeypatch):
    """A picture of at least 1920 x 1080 in 16:9 becomes the wallpaper (a copy in the portal's state folder);
    another is refused, with the rules (owner, 20-10-2026)."""
    from PyQt6.QtGui import QColor, QImage
    from bc250_portal import state_dir, wallpaper

    def picture(name: str, width: int, height: int) -> Path:
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor("#ff0000"))
        path = tmp_path / name
        image.save(str(path))
        return path

    small, square, good = picture("small.png", 1280, 720), picture("square.png", 2000, 2000), \
        picture("good.jpg", 2560, 1440)
    assert "smaller than 1920 x 1080" in wallpaper.problem(small)
    assert "not 16:9" in wallpaper.problem(square)
    assert wallpaper.problem(picture("odd.png", 1920, 1082)) == ""          # a few pixels off
    assert "not a PNG" in wallpaper.problem(tmp_path / "notes.txt")
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    for chosen in (small, good):
        monkeypatch.setattr(mw.QFileDialog, "getOpenFileName", lambda *a, c=chosen, **k: (str(c), ""))
        window.choose_wallpaper()
    assert len(warned) == 1 and "smaller than" in warned[0] and wallpaper.RULES in warned[0]
    assert wallpaper.current() == state_dir() / "wallpaper.jpg" and state_dir().is_relative_to(home)
    assert window.wallpaper_pill.value.text() == "Custom" and not window.big.picture.isNull()
    good.unlink()                                           # the portal keeps its own copy
    window.resize(900, 700)
    window.show()
    assert QColor(window.big.grab().toImage().pixel(10, 350)).red() > 60       # red under the veil, in the margin
    window.remove_wallpaper()
    assert wallpaper.current() is None and window.wallpaper_pill.value.text() == "None"
    assert window.big.picture.isNull()


def test_the_example_wallpaper(window):
    """The portal ships an example wallpaper, to show how one looks, but never sets it by itself: the user chooses it
    in the menu (owner, 20-10-2026). It meets the portal's own rules."""
    from PyQt6.QtGui import QColor, QImage
    from bc250_portal import wallpaper

    def menu() -> dict[str, tuple[bool, bool]]:
        return {a.text(): (a.isChecked(), a.isEnabled()) for a in window.wallpaper_menu().actions()}

    assert wallpaper.EXAMPLE.is_file() and wallpaper.problem(wallpaper.EXAMPLE) == ""
    assert wallpaper.shown() is None and window.wallpaper_pill.value.text() == "None"   # none at first
    assert window.big.picture.isNull() and menu()["Example wallpaper"] == (False, True)
    assert not menu()["No wallpaper"][1]
    window.example_wallpaper()
    assert wallpaper.shown() == wallpaper.EXAMPLE and wallpaper.current() is None
    assert window.wallpaper_pill.value.text() == "Example" and not window.big.picture.isNull()
    assert menu()["Example wallpaper"] == (True, False) and menu()["No wallpaper"] == (False, True)
    assert wallpaper.saved() == []                          # not among the pictures used before
    window.remove_wallpaper()
    assert wallpaper.shown() is None and window.wallpaper_pill.value.text() == "None"
    window.example_wallpaper()
    picture = wallpaper.state_dir().parent / "mine.png"
    image = QImage(1920, 1080, QImage.Format.Format_RGB32)
    image.fill(QColor("#00ff00"))
    image.save(str(picture))
    window.apply_wallpaper(picture)                         # a picture of one's own replaces the example
    assert not wallpaper.is_example() and window.wallpaper_pill.value.text() == "Custom"
    assert menu()["Example wallpaper"] == (False, True)
    window.example_wallpaper()
    assert wallpaper.current() is None and wallpaper.shown() == wallpaper.EXAMPLE
    assert window.wallpaper_pill.value.text() == "Example"


def test_the_wallpapers_used_before(window, tmp_path):
    """The portal remembers where the last 10 wallpapers came from, newest first and each once, and offers them again
    in the Wallpaper pill's menu (owner, 20-10-2026): the current one ticked, one moved or deleted grayed out."""
    from PyQt6.QtGui import QColor, QImage
    from bc250_portal import state_dir, wallpaper

    def picture(n: int) -> Path:
        image = QImage(1920, 1080, QImage.Format.Format_RGB32)
        image.fill(QColor(n * 20, 0, 0))
        path = tmp_path / f"wall{n}.png"
        image.save(str(path))
        return path

    def entries() -> list[tuple[str, bool, bool]]:
        actions = window.wallpaper_menu().actions()
        used = actions[[a.text() for a in actions].index("Used before") + 1:]
        return [(a.text(), a.isChecked(), a.isEnabled()) for a in used]

    assert wallpaper.saved() == [] and "Used before" not in [a.text() for a in window.wallpaper_menu().actions()]
    pictures = [picture(n) for n in range(12)]
    for path in pictures:
        window.apply_wallpaper(path)
    assert wallpaper.saved() == pictures[:1:-1]                                    # the newest 10, newest first
    assert json.loads((state_dir() / wallpaper.HISTORY).read_text())["saved"][0] == str(pictures[11])
    window.apply_wallpaper(pictures[5])                                         # again: first, and only once
    assert wallpaper.saved()[:2] == [pictures[5], pictures[11]] and len(wallpaper.saved()) == 10
    pictures[11].unlink()
    shown = entries()
    assert shown[0] == ("wall5.png", True, False)                               # the current one
    assert shown[1] == ("wall11.png (not found)", False, False)
    assert shown[2] == ("wall10.png", False, True) and len(shown) == 10
    window.wallpaper_menu().actions()[-1].trigger()                             # the oldest, chosen again
    assert wallpaper.saved()[0] == pictures[2] and wallpaper.current().read_bytes() == pictures[2].read_bytes()
    window.remove_wallpaper()                                                   # none now: none ticked
    assert not any(checked for _, checked, _ in entries()) and len(wallpaper.saved()) == 10


def test_the_wallpapers_transparency(window):
    """A slider in the Wallpaper pill's menu sets how much of the theme's color lies over the picture, while it moves
    and for the next start (owner, 20-10-2026): 60 % at first, as before, up to 90 %; off without a wallpaper."""
    from PyQt6.QtGui import QColor, QPalette

    def slider_action():
        return next(a for a in window.wallpaper_menu().actions() if a.text() == "Transparency")

    assert window.transparency() == mw.VEIL == 60 and not slider_action().isEnabled()
    window.example_wallpaper()
    action = slider_action()
    assert action.isEnabled() and window.transparency_slider.value() == 60
    assert "Transparency 60 %" in window.wallpaper_pill.toolTip()
    assert window.transparency_slider.maximum() == mw.VEIL_MAX == 90
    window.resize(900, 700)
    window.show()
    veil = QColor(window.palette().color(QPalette.ColorRole.Window))

    def distance() -> int:
        pixel = QColor(window.big.grab().toImage().pixel(10, 350))
        return sum(abs(a - b) for a, b in zip(pixel.getRgb()[:3], veil.getRgb()[:3]))

    before = distance()
    window.transparency_slider.setValue(88)                 # rounded to the step
    assert window.big.veil == 90 and window.settings.value(mw.VEIL_KEY, type=int) == 90
    assert distance() < before                              # nearer the theme's own color
    assert "Transparency 90 %" in window.wallpaper_pill.toolTip()
    window.settings.setValue(mw.VEIL_KEY, 250)              # a value from elsewhere: kept within the slider's range
    assert window.transparency() == 90


def test_a_checkout_install_is_compared_by_its_version(window, home):
    """A portal from a release, an app installed from a checkout (owner, 26-10-2026): the recorded version against
    the pin, as a tag's; a record without one (portal 9.2.0 and earlier) needs a reinstall."""
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    state = window.states["gpu"]
    window.records.set("gpu", "local-v0.0.9")
    window.refresh()
    assert state.status == "Update" and state.update and not state.reinstall
    assert "installed from the suite checkout (v0.0.9), this portal pins" in state.tooltip
    assert "installed from the suite checkout (v0.0.9)" in window.notice_lines[0][1]
    window.records.set("gpu", f"local-v{state.entry.version}")
    window.refresh()
    assert state.status == "Installed" and not state.update and not state.reinstall
    assert f"Installed from the suite checkout (v{state.entry.version})." in state.tooltip
    assert window.big.notice.isHidden()
    window.records.set("gpu", "local")
    window.refresh()
    assert state.status == "Reinstall needed" and state.reinstall and not state.update
    assert "without recording its version" in state.tooltip
    assert window.big.notice.text() == "● 1 reinstall"


def test_a_checkout_portal_shows_its_own_installs_as_installed(qapp, home, settings_dir, tmp_path, launched):
    sources = FakeSources(tmp_path / "work")
    sources.checkout = Path("/checkout")                                    # a portal from a checkout
    w = mw.MainWindow(load(MANIFEST), sources, Records(tmp_path / "installed.json"))
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    state = w.states["gpu"]
    for record in ("local-v0.0.9", "local"):
        w.records.set("gpu", record)
        w.refresh()
        assert state.status == "Installed" and not state.update and not state.reinstall
        assert w.big.notice.isHidden()
    assert "Installed from the suite checkout (v0.0.9)." not in state.tooltip
    assert "Installed from the suite checkout." in state.tooltip
    assert "local checkout /checkout" in w.source_text
    w.records.set("gpu", "gpu-v0.0.9")                                      # from a release: an update, as before
    w.refresh()
    assert state.status == "Update"
    w.close()


def test_a_checkout_install_records_the_staged_version(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: YES)
    sources = FakeSources(tmp_path / "work")
    sources.checkout = Path("/checkout")
    w = mw.MainWindow(load(MANIFEST), sources, Records(tmp_path / "installed.json"))
    entry = w.states["upscaler"].entry
    folder = sources.folder(entry)
    folder.mkdir(parents=True)
    (folder / "VERSION").write_text("1.2.3\n")
    w.install(entry)
    assert wait_for(lambda: launched)
    assert w.pending.tag == "local-v1.2.3"
    w.cancel_pending()
    w.close()


# ------------------------------------------------------------------------- an app to the front (owner, 05-11-2026)
class FakeRaiser:
    def __init__(self):
        self.asked: list[tuple[list[str], list[int]]] = []

    def bring_to_front(self, app_ids, pids=()):
        self.asked.append((list(app_ids), list(pids)))
        return True

    def close(self):
        pass


class FakeProcess:
    count = 100

    def __init__(self, argv, **_kw):
        FakeProcess.count += 1
        self.pid, self.argv, self.ended = FakeProcess.count, argv, False

    def poll(self):
        return 0 if self.ended else None


def test_a_running_app_comes_to_the_front_without_a_second_warning(qapp, home, settings_dir, tmp_path, launched,
                                                                   monkeypatch):
    """Pressing the tile of an app that runs (behind the portal) starts it again, which asks it to show itself, and
    has KWin make its window the active one: by its app id, the launcher's name, and the process the portal started.
    The board warning comes when it is opened, not each time it comes back to the front."""
    raiser = FakeRaiser()
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                      raiser=raiser)
    started = []
    monkeypatch.setattr(mw.subprocess, "Popen", lambda argv, **kw: started.append(FakeProcess(argv, **kw))
                        or started[-1])
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]) or YES)
    gpu = w.states["gpu"].entry
    command = gpu.launch[0][1]
    w.open_app(gpu, command)
    first = started[0]
    assert len(warnings) == 1 and raiser.asked == [(["bc250-governor-manager"], [first.pid])]
    w.open_app(gpu, command)                            # it runs: to the front, no second warning
    assert len(warnings) == 1 and len(started) == 2 and raiser.asked[-1] == (["bc250-governor-manager"], [first.pid])
    first.ended = True                                  # closed since: opening it warns again
    w.open_app(gpu, command)
    assert len(warnings) == 2 and raiser.asked[-1] == (["bc250-governor-manager"], [started[2].pid])
    w.close()


# -------------------------------------------------------------------------- clock and weather (owner, 05-11-2026)
class FakeMouse:
    def __init__(self):
        self.moves, self.presses, self.closed = [], [], False

    def move(self, dx, dy):
        self.moves.append((dx, dy))

    def press(self, button, down):
        self.presses.append((button, down))

    def close(self):
        self.closed = True


def test_the_clock_pill_sets_the_hours_the_seconds_and_the_zone(window):
    assert window.clock_style() == mw.status.ClockStyle()        # as the clock always was
    menu = window.clock_menu()
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts[:3] == ["12-hour clock (AM/PM)", "24-hour clock", "Seconds"]
    assert texts[-2:] == ["CET, Central European Time (CEST in summer)", "UTC"] and texts[-3].startswith("The board's")
    for action in menu.actions():
        if action.data() in (("hours", 24), ("seconds", True), ("zone", "utc")):
            window._clock_action(action)
    menu.deleteLater()
    assert window.clock_style() == mw.status.ClockStyle(24, True, "utc")
    assert window.clock_pill.value.text() == "24 h" and "UTC" in window.clock_pill.toolTip()
    line = window.big.status.text().replace("\n", " | ")
    assert line.endswith(" UTC") and line.count(":") == 2                    # 18:44:07 UTC: with the seconds
    window.settings.setValue(mw.CLOCK_KEYS[2], "mars")                      # an unknown zone: the board's
    assert window.clock_style().zone == "local"


def test_the_status_is_three_lines(qapp):
    """A line each (owner, 12-11-2026), whatever the room: the loads, the date and time, and the weather with a place
    chosen (its symbol, the place, the temperature and the sky); two lines without a place."""
    from bc250_portal import glyphs
    from bc250_portal.bigpicture import PLACE_W, StatusLine
    status = StatusLine()
    status.show()
    status.set_parts("CPU 12% 54°C | GPU 3% 61°C", "Thursday 11/5/26 | 07:44:05 PM CEST")
    status.resize(status.sizeHint().width() + 400, status.sizeHint().height())     # room for one line: still two
    assert status.text() == "CPU 12% 54°C | GPU 3% 61°C\nThursday 11/5/26 | 07:44:05 PM CEST"
    assert status.lines.text() == status.text() and status.weather.isHidden()
    two = status.sizeHint().height()
    status.set_weather("Amsterdam", "8°C  Overcast", glyphs.weather("cloudy"), True, "Amsterdam: Overcast, 8°C.")
    assert status.text().splitlines()[2] == "Amsterdam  8°C  Overcast" == status.sky.text()
    assert not status.weather.isHidden() and not status.symbol.pixmap().isNull()
    assert status.weather.toolTip() == "Amsterdam: Overcast, 8°C." and status.sizeHint().height() > two
    status.set_weather("Amsterdam", "", glyphs.weather("cloudy"), False, "")          # on its way: the place alone
    assert status.sky.text() == "Amsterdam"
    status.set_weather("Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch", "8°C  Overcast",
                       glyphs.weather("cloudy"), True, "")
    place = status.sky.text().split("  ")[0]
    assert place.endswith("…") and status.sky.fontMetrics().horizontalAdvance(place) <= PLACE_W
    assert status.narrowest() >= status.sky.fontMetrics().horizontalAdvance(status.sky.text())
    status.set_weather("", "", None, False, "")
    assert status.weather.isHidden() and len(status.text().splitlines()) == 2
    status.close()


def test_the_weather_shows_under_the_clock_once_a_place_is_chosen(qapp, home, settings_dir, tmp_path, launched):
    """No place: no weather, nothing asked. A place: its weather from Open-Meteo as the status' third line (owner,
    12-11-2026), the symbol, the name, the temperature and the sky; Open-Meteo down keeps the last weather and says
    why in the tooltip; No weather removes it."""
    asked = []

    def fetch(url, params):
        asked.append(url)
        if fetch.down:
            raise mw.weather.WeatherError("Open-Meteo is unavailable for now (503: overloaded).")
        return {"current": {"temperature_2m": 8.2, "weather_code": 3, "is_day": 1}}
    fetch.down = False
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                      weather_fetch=fetch)
    line = w.big.status
    assert line.weather.isHidden() and w.weather_pill.value.text() == "None" and asked == []
    w.set_place(mw.weather.Place("Amsterdam", "North Holland", "Netherlands", 52.37, 4.89))
    assert wait_for(lambda: w.weather is not None)
    assert asked == [mw.weather.FORECAST_URL] and w.weather_timer.isActive()
    assert not line.weather.isHidden() and line.sky.text() == "Amsterdam  8°C  Overcast" and line.known
    assert "Overcast, 8°C" in line.weather.toolTip() and w.weather_pill.full_value == "Amsterdam"
    assert mw.weather.Place.from_json(w.settings.value(mw.PLACE_KEY)).name == "Amsterdam"
    fetch.down = True
    w.update_weather()
    assert wait_for(lambda: w.weather_error != "")
    assert w.weather is not None and "unavailable for now" in line.weather.toolTip()
    assert line.sky.text() == "Amsterdam  8°C  Overcast"                       # the last weather stays
    menu = w.weather_menu()
    assert [a.text() for a in menu.actions()] == ["Choose a place…", "Update the weather now", "No weather"]
    w._weather_action(menu.actions()[2])
    menu.deleteLater()
    assert line.weather.isHidden() and not w.weather_timer.isActive() and w.settings.value(mw.PLACE_KEY) == ""
    w.close()


def test_a_long_place_name_ends_in_an_ellipsis_on_its_pill(window):
    window.set_place(mw.weather.Place("Llanfairpwllgwyngyll", "Wales", "United Kingdom", 53.2, -4.2))
    pill = window.weather_pill
    assert pill.full_value == "Llanfairpwllgwyngyll" and pill.value.text().endswith("…")
    assert pill.value.fontMetrics().horizontalAdvance(pill.value.text()) < pill.width()
    window.set_place(None)


def test_the_touchpad_moves_the_pointer_only_while_the_portal_has_the_focus(qapp, home, settings_dir, tmp_path,
                                                                             launched, monkeypatch):
    mouse = FakeMouse()
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                      mouse=mouse)
    monkeypatch.setattr(mw.QApplication, "activeWindow", staticmethod(lambda: None))
    w.gamepad.pointer_moved.emit(10.0, 5.0)
    w.gamepad.pointer_pressed.emit(False, True)
    assert mouse.moves == [] and mouse.presses == []                    # a game has the focus: not ours
    w.gamepad.pointer_pressed.emit(False, False)
    assert mouse.presses == [(mw.pointer.BTN_LEFT, False)]              # a release always goes through
    monkeypatch.setattr(mw.QApplication, "activeWindow", staticmethod(lambda: w))
    w.gamepad.pointer_moved.emit(10.0, 5.0)
    w.gamepad.pointer_pressed.emit(True, True)
    assert mouse.moves == [(10.0, 5.0)] and mouse.presses[-1] == (mw.pointer.BTN_RIGHT, True)
    w.close()
    assert mouse.closed


def test_the_touchpad_pill_steps_through_the_speeds(window):
    """The Touchpad pill (owner, 05-11-2026): a click for the next speed, at once and kept, round to the slowest."""
    assert window.touch_speed() == 100 and window.gamepad.touch_speed == mw.TOUCH_SPEED
    window.touch_pill.click()
    assert window.touch_speed() == 125 and window.gamepad.touch_speed == mw.TOUCH_SPEED * 1.25
    assert window.touch_pill.full_value == "125 %" and window.settings.value(mw.TOUCH_KEY, type=int) == 125
    window.touch_pill.click()
    window.touch_pill.click()
    assert window.touch_speed() == 50 and window.touch_pill.full_value == "50 %"
    window.settings.setValue(mw.TOUCH_KEY, 333)                 # not a step: the normal speed
    assert window.touch_speed() == 100

