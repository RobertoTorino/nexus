# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal window with the terminal, downloads and dialogs replaced by fakes."""

from __future__ import annotations

import json

from dataclasses import replace
from pathlib import Path, PurePosixPath

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QMessageBox

from bc250_portal import MANIFEST
from bc250_portal import main_window as mw
from bc250_portal.manifest import load, load_checkout
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


def test_bazzite_test_first_without_uninstall(window):
    keys = list(window.cards)
    assert keys[0] == "check"
    assert window.cards["check"].uninstall_button.isHidden()
    assert not window.cards["gpu"].uninstall_button.isHidden()
    assert not window.cards["acpi"].open_button.isHidden()
    assert window.cards["compute"].open_button.menu() is not None        # Bisect / Unlock


def test_every_card_has_its_icon(qapp, home, settings_dir, tmp_path, launched):
    entries = load(MANIFEST) + load_checkout(MANIFEST)
    w = mw.MainWindow(entries, FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    for key, card in w.cards.items():
        assert (mw.APP_ICONS / f"{key}.webp").is_file(), key
        assert card.has_icon and card.icon.iconSize().width() == mw.ICON_PX, key
    w.close()


def test_open_menu_shows_each_window_icon(window):
    for key in ("compute", "cores"):
        actions = window.cards[key].icon.menu().actions()
        assert [a.text() for a in actions] == ["Bisect", "Unlock"]
        assert all(not a.icon().isNull() for a in actions), key
        assert (mw.APP_ICONS / f"{mw.LAUNCH_ICON_FILES[(key, 'Unlock')]}.webp").is_file()


def test_card_without_icon_file_shows_its_initial(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    monkeypatch.setattr(mw, "APP_ICONS", tmp_path / "no-icons")
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    assert all(not card.has_icon and not card.icon.isHidden() for card in w.cards.values())
    w.close()


def test_the_logo_opens_the_wiki(window, monkeypatch):
    from bc250_core import SUITE_MANUAL_URL
    opened = []
    monkeypatch.setattr(mw.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    window.logo.clicked.emit()
    assert opened == [SUITE_MANUAL_URL]
    assert "wiki" in window.logo.toolTip()


def test_the_header_shows_the_suite_stage(window):
    """Beside the version, with what it means on hover; hidden once STAGE is ""."""
    import bc250_portal
    assert window.stage.text() == bc250_portal.STAGE
    assert window.stage.toolTip() == bc250_portal.STAGE_NOTE
    assert window.stage.isVisibleTo(window) == bool(bc250_portal.STAGE)


def test_the_tiles_icon_hover_and_press(window, home):
    """Under the mouse the icon dims a little, with no border (owner, 20-10-2026); pressed, it sinks, with no color
    behind it (no purple flash on a click)."""
    from PyQt6.QtCore import QEvent
    card = window.cards["gpu"]
    style = card.icon.styleSheet()
    assert "QToolButton:hover { background:transparent; border-color:transparent; }" in style
    assert "pressed:enabled" in style and "padding-top:2px" in style        # the icon sinks while pressed
    assert "QToolButton:pressed:enabled { background:transparent;" in style and "B39DDB" not in style
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    window.refresh()
    assert card.icon.isEnabled()

    def alpha() -> int:
        image = card.icon.icon().pixmap(mw.QSize(mw.ICON_PX, mw.ICON_PX)).toImage()
        return max(image.pixelColor(x, y).alpha() for x in range(0, mw.ICON_PX, 8) for y in range(0, mw.ICON_PX, 8))

    full = alpha()
    card.eventFilter(card.icon, QEvent(QEvent.Type.Enter))
    assert alpha() == round(full * mw.HOVER_OPACITY) or abs(alpha() - full * mw.HOVER_OPACITY) <= 1
    card.eventFilter(card.icon, QEvent(QEvent.Type.Leave))
    assert alpha() == full


def test_icons_and_symbols_keep_their_size(window):
    """The theme gives every tool button a padding: on the tiles it shrank the 128 px icon and left the Install and
    Uninstall symbols a third of their size (19-10-2026). Rendered: the symbol fills its SYMBOL_PX."""
    card = window.cards["gpu"]
    for button in (card.icon, card.install_button, card.uninstall_button):
        assert "padding:0;" in button.styleSheet() and "background:transparent;" in button.styleSheet()
    from bc250_core.theme import stylesheet
    window.setStyleSheet(stylesheet())                      # the theme's sheet, as create_app() puts it on the app
    window.show()
    image = card.install_button.grab().toImage()
    ink = [x for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x, y).alpha() > 128]
    assert max(ink) - min(ink) >= mw.SYMBOL_PX * 0.6                          # was about 10 px of a 28 px symbol


def test_short_names_drop_the_suite_prefix(window):
    assert mw.short_name("BC-250 Bazzite Test") == "Bazzite Test"
    assert mw.short_name("BC250 Suite Releases") == "Suite Releases"
    assert mw.short_name("Media Tool") == "Media Tool"
    assert window.cards["gpu"].title.text() == "GPU Governor Manager"
    assert "BC-250 GPU Governor Manager" in window.cards["gpu"].icon.toolTip()     # the full name on hover
    assert window.cards["cec"].title.text() == "HDMI-CEC"                          # apps.toml's short


def test_icon_opens_only_an_installed_program(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    entries = [replace(e, launch=()) if e.key == "gpu" else e for e in load(MANIFEST)]
    w = mw.MainWindow(entries, FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    acpi = w.cards["acpi"]
    assert not acpi.icon.isEnabled() and "Not installed" in acpi.icon.toolTip()
    for name in ("bc250-governor-manager", "bc250-persistent-acpi-gui"):
        (home / ".local" / "bin" / name).write_text("#!/bin/sh\n")
    w.refresh()
    assert acpi.icon.isEnabled() and "Click to open it." in acpi.icon.toolTip()
    assert not w.cards["gpu"].icon.isEnabled()                         # not a program
    opened = []
    monkeypatch.setattr(w, "open_app", lambda entry, command: opened.append(command))
    acpi.open_clicked.disconnect()
    acpi.open_clicked.connect(w.open_app)
    acpi.icon.click()
    assert opened == ["~/.local/bin/bc250-persistent-acpi-gui"]
    w.close()


def test_icon_is_greyed_until_installed(window, home):
    card = window.cards["overlay"]
    assert card.icon.icon().cacheKey() == card._icons[1].cacheKey()
    (home / ".local" / "bin" / "bc250-system-overlay").write_text("#!/bin/sh\n")
    window.refresh()
    assert card.icon.icon().cacheKey() == card._icons[0].cacheKey()


def test_board_warning_under_the_icon(window):
    assert not window.cards["gpu"].board.isHidden()
    assert window.cards["overlay"].board.isHidden()


def test_states_follow_detection_and_records(window, home):
    card = window.cards["gpu"]
    assert card.status == "Not installed" and card.install_button.toolTip().startswith("Install ")
    assert not card.uninstall_button.isEnabled()
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    window.refresh()
    assert card.status == "Reinstall needed" and card.install_button.toolTip().startswith("Reinstall ")
    assert card.uninstall_button.isEnabled()
    window.records.set("gpu", next(e.tag for e in window.entries if e.key == "gpu"))
    window.refresh()
    assert card.status == "Installed" and card.install_button.toolTip().startswith("Reinstall ")
    window.records.set("gpu", "gpu-v0.0.9")
    window.refresh()
    assert card.status == "Update" and card.install_button.toolTip().startswith("Update ")


def _same_icon(button, icon) -> bool:
    size = mw.QSize(mw.SYMBOL_PX, mw.SYMBOL_PX)
    return button.icon().pixmap(size).toImage() == icon.pixmap(size).toImage()


def test_bazzite_test_has_only_reinstall(window, home):
    """With the arrow into a tray, as every app (owner, 14-10-2026), and the version it reinstalls."""
    card = window.cards["check"]
    (home / ".local" / "bin" / "bc250-bazzite-test").write_text("#!/bin/sh\n")
    window.records.set("check", card.entry.tag)
    window.refresh()
    assert card.install_button.toolTip() == f"Reinstall BC-250 Bazzite Test v{card.entry.version}"
    assert card.uninstall_button.isHidden()
    assert _same_icon(card.install_button, mw.glyphs.install(card._ink()))
    window.records.set("check", "")                                      # not installed by the portal
    window.refresh()
    assert _same_icon(card.install_button, mw.glyphs.reinstall(mw.RED))


def test_board_change_needs_confirmation(window, launched, monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: (asked.append(a[2]), CANCEL)[1])
    window.install(next(e for e in window.entries if e.key == "acpi"))
    assert asked and "changes how your BC-250 runs" in asked[0]
    assert window.sources.prepared == [] and launched == []                 # canceled: nothing happens


def test_no_warning_for_bazzite_test(window, launched, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail("no board warning expected"))
    window.install(window.entries[0])
    assert wait_for(lambda: launched)
    line, exit_file = launched[0]
    assert line.endswith("&& bash install.sh") and "local-check" not in line
    assert window.pending is not None and window.cards["check"].status == "Installing…"
    assert not window.cards["check"].busy_label.isHidden()
    assert not window.cards["gpu"].install_button.isEnabled()          # one action at a time


def test_install_success_records_tag(window, launched, monkeypatch, home):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: YES)
    entry = next(e for e in window.entries if e.key == "gpu")
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
    assert window.cards["gpu"].status == "Installed"


def test_failed_install_warns_and_records_nothing(window, launched, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: YES)
    entry = next(e for e in window.entries if e.key == "upscaler")
    window.install(entry)
    assert wait_for(lambda: launched)
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    launched[0][1].write_text("1\n")
    window._check_pending()
    assert window.records.get("upscaler") == "" and shown and "exit status 1" in shown[0]


def test_uninstall_forgets_release(window, launched, monkeypatch, home):
    entry = next(e for e in window.entries if e.key == "upscaler")
    (home / ".local" / "bin" / "bc250-upscaler").write_text("#!/bin/sh\n")
    window.records.set("upscaler", entry.tag)
    window.refresh()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: YES)
    window.uninstall(entry)
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
    assert window.pending is None and window.cards["gpu"].install_button.isEnabled()


def test_shell_line_quotes_folder():
    line = mw.shell_line(PurePosixPath("/tmp/a b"), ("bash x.sh", "bash y.sh"))
    assert line == "cd '/tmp/a b' && bash x.sh && bash y.sh"


def test_red_dot_and_count_for_updates(window, home):
    for name in ("bc250-governor-manager", "bc250-upscaler"):
        (home / ".local" / "bin" / name).write_text("#!/bin/sh\n")
    window.records.set("gpu", "gpu-v0.0.9")              # older than the pin: an update
    window.records.set("upscaler", next(e.tag for e in window.entries if e.key == "upscaler"))   # the pinned one
    window.refresh()
    assert not window.cards["gpu"].dot.isHidden()
    assert window.cards["upscaler"].dot.isHidden()
    assert "gpu-v0.0.9" in window.cards["gpu"].dot.toolTip()
    notice = window.notice.text()
    assert "\u25cf 1 update</b>" in notice and "<a href='gpu'>GPU Governor Manager</a> (Sustainable): update to v" in notice
    assert "installed from gpu-v0.0.9" in notice and "HelixSR" not in notice
    sustainable = window.tabs.indexOf(window.pages["sustainable"])
    assert window.tabs.tabText(sustainable) == "Sustainable  \u25cf 1"                # the count on its tab
    assert window.tabs.tabText(window.tabs.indexOf(window.pages["graphics"])) == "Graphics"
    window.records.set("gpu", next(e.tag for e in window.entries if e.key == "gpu"))
    window.refresh()
    assert window.cards["gpu"].dot.isHidden() and window.notice.text().startswith("<span style='color:gray;'>No updates")
    assert window.tabs.tabText(sustainable) == "Sustainable"


def test_installed_apps_pill_counts_installed_of_listed(qapp, home, settings_dir, tmp_path, launched):
    """Installed apps: installed / listed, a withdrawn app not counted (owner, 21-10-2026)."""
    entries = [replace(e, withdrawn="test") if e.key == "sftp" else e for e in load(MANIFEST)]
    w = mw.MainWindow(entries, FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    listed = len(entries) - 1
    assert w.installed_pill.value.text() == f"0/{listed}"
    for name in ("bc250-governor-manager", "bc250-upscaler"):
        (home / ".local" / "bin" / name).write_text("#!/bin/sh\n")
    w.refresh()
    assert w.installed_pill.value.text() == f"2/{listed}" and f"2 of the {listed} apps" in w.installed_pill.toolTip()
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
    pill = window.updates_pill
    assert pill.value.text() == "3" and pill.isEnabled() and "all 3" in pill.toolTip()
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a[2]), CANCEL)[1])
    pill.click()
    assert "Install these 3 updates" in asked[0] and "change how your BC-250 runs" in asked[0]   # acpi
    assert window.batch is None and launched == []                          # canceled: nothing happens
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: YES)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail("one question only"))
    pill.click()
    assert wait_for(lambda: len(launched) == 1)
    assert window.sources.prepared == [keys[0]] and pill.value.text() == "1/3" and not pill.isEnabled()
    # Its installer waits for the password: no exit file yet, so the batch waits too.
    window._check_pending()
    assert window.pending is not None and len(launched) == 1
    launched[0][1].write_text("0\n")
    window._check_pending()
    assert wait_for(lambda: len(launched) == 2) and window.records.get(keys[0]) != ""
    launched[1][1].write_text("1\n")                          # a failure: the batch goes on
    window._check_pending()
    assert wait_for(lambda: len(launched) == 3) and pill.value.text() == "3/3"
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    launched[2][1].write_text("0\n")
    window._check_pending()
    assert window.batch is None and not window.busy() and window.sources.prepared == keys
    assert len(shown) == 1 and "1 of the 3 updates did not install" in shown[0] and "exit status 1" in shown[0]
    failed = next(e for e in window.entries if e.key == keys[1])
    assert failed.name in shown[0] and [e.key for e, _ in window.marked] == [keys[1]]
    assert pill.value.text() == "1" and pill.isEnabled()


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
    assert window.updates_pill.value.text() == "2" and window.updates_pill.isEnabled()


def test_install_all_apps_is_the_last_tab_and_fills_the_open_category(window, launched, monkeypatch, qapp):
    """Install all apps (owner, 26-10-2026): the last tab is a button that looks like a tab. A click installs every
    app of the open category not installed yet as one batch with one question; the tab shows the batch's progress;
    it never opens; on Development it is disabled, and so it is once every app of the category is installed."""
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest
    bar, last = window.tabs.tabBar(), window.install_tab
    assert last == window.tabs.count() - 1 and window.tabs.tabText(last) == "Install all apps"
    assert bar.action_index == last and not window.tabs.tabIcon(last).isNull()
    expected = [e for e in window.entries if e.category == "sustainable"]
    assert window.shown_category() == "sustainable" and window.missing("sustainable") == expected
    assert window.tabs.isTabEnabled(last) and f"all {len(expected)} apps on Sustainable" in window.tabs.tabToolTip(last)
    window.show()
    qapp.processEvents()
    window.tabs.setCurrentIndex(last)                        # the keyboard landing on it: it goes back
    assert window.tabs.currentIndex() == 0 and window.shown_category() == "sustainable"
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a[2]), CANCEL)[1])
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=bar.tabRect(last).center())
    assert window.tabs.currentIndex() == 0                   # a click does not open it
    assert f"Install these {len(expected)} apps on Sustainable" in asked[0] and "change how your BC-250 runs" in asked[0]
    assert "Fan Control" in asked[0] and "Upscaler" not in asked[0]
    assert window.batch is None and launched == []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: YES)
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=bar.tabRect(last).center())
    assert wait_for(lambda: len(launched) == 1)
    assert window.sources.prepared == [expected[0].key]
    assert window.tabs.tabText(last) == f"Installing 1 of {len(expected)}" and not window.tabs.isTabEnabled(last)
    assert window.updates_pill.value.text() == "0" and not window.updates_pill.isEnabled()
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
    assert window.tabs.tabText(last) == "Install all apps" and not window.tabs.isTabEnabled(last)
    assert window.tabs.tabToolTip(last) == "Every app on Sustainable is installed."
    window.tabs.setCurrentWidget(window.pages["graphics"])
    assert window.tabs.isTabEnabled(last) and "on Graphics" in window.tabs.tabToolTip(last)
    window.tabs.setCurrentWidget(window.pages["development"])
    assert window.missing("development") == [] and not window.tabs.isTabEnabled(last)
    assert "tools for working on the suite" in window.tabs.tabToolTip(last)
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=bar.tabRect(last).center())
    assert window.batch is None and len(launched) == len(expected)         # disabled: nothing happens


def test_no_updates_no_batch(window, launched):
    assert window.updates_pill.value.text() == "0" and not window.updates_pill.isEnabled()
    assert "No updates" in window.updates_pill.toolTip()
    window.install_all()
    assert window.batch is None and launched == []


def test_updates_outside_the_suite(window, home):
    from bc250_core import upstream
    helix = upstream.Outside("HelixSR", "1.8.1", "1.9.3", "2026-10-16", "https://x/v1.9.3",
                             "Get HelixSR… on the Setup page updates it.")
    upstream.publish("upscaler", [helix])
    upstream.publish("pcsx2", [upstream.Outside("PCSX2 nightly", "2.9.127", "2.9.128")])
    window.refresh()
    assert "Outside" not in window.notice.text()                        # neither app is installed
    (home / ".local" / "bin" / "bc250-upscaler").write_text("#!/bin/sh\n")
    window.records.set("upscaler", next(e.tag for e in window.entries if e.key == "upscaler"))
    window.refresh()
    notice = window.notice.text()
    assert "No updates" not in notice and "\u25cf Outside the suite</b>" in notice
    assert ("<a href='upscaler'>Upscaler Manager</a> (Graphics): HelixSR 1.9.3 is out (2026-10-16), installed 1.8.1. "
            "Get HelixSR… on the Setup page updates it.") in notice
    assert "PCSX2" not in notice and "Outside the suite" in window.notice.toolTip()
    sustainable_tabs = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert not any("\u25cf" in t for t in sustainable_tabs)              # the tab dots are the suite's updates
    # Beside an update of the suite's own:
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    window.records.set("gpu", "gpu-v0.0.9")
    window.refresh()
    notice = window.notice.text()
    assert notice.index("\u25cf 1 update</b>") < notice.index("Outside the suite")
    # The app found nothing more to install; the portal sees it when its window is active again.
    upstream.publish("upscaler", [])
    window.show_notice(window.marked)
    assert "Outside the suite" not in window.notice.text() and "Outside" not in window.notice.toolTip()


def test_circular_arrow_and_count_for_reinstalls(window, home):
    # Installed but not recorded: by hand, or under an earlier key that RENAMED does not know (shadps4 became
    # shadps4-manager before RENAMED existed).
    for name in ("bc250-governor-manager", "bc250-upscaler"):
        (home / ".local" / "bin" / name).write_text("#!/bin/sh\n")
    window.records.set("upscaler", "upscaler-v0.0.1")                          # an update, for the count
    window.refresh()
    card = window.cards["gpu"]
    assert card.status == "Reinstall needed" and not card.badge.isHidden() and card.dot.isHidden()
    assert "Reinstall needed" in card.icon.toolTip() and "version is unknown" in card.badge.toolTip()
    assert card.install_button.toolTip().startswith("Reinstall ")
    assert window.cards["upscaler"].badge.isHidden() and not window.cards["upscaler"].dot.isHidden()
    assert "\u25cf 1 update, 1 reinstall</b>" in window.notice.text()
    assert "<a href='gpu'>GPU Governor Manager</a> (Sustainable): reinstall needed" in window.notice.text()
    window.records.remove("upscaler")
    (home / ".local" / "bin" / "bc250-upscaler").unlink()
    window.refresh()
    assert "\u25cf 1 reinstall</b>" in window.notice.text()
    window.records.set("gpu", next(e.tag for e in window.entries if e.key == "gpu"))
    window.refresh()
    assert card.badge.isHidden() and card.status == "Installed" and "No updates" in window.notice.text()


def test_not_installed_and_withdrawn_need_no_reinstall(qapp, home, settings_dir, tmp_path, launched):
    entries = [replace(e, withdrawn="test") if e.key == "gpu" else e for e in load(MANIFEST)]
    w = mw.MainWindow(entries, FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    w.refresh()
    assert w.cards["gpu"].badge.isHidden()                              # the portal removes it instead
    assert w.cards["overlay"].badge.isHidden()                               # not installed
    w.close()


def test_local_build_banner(qapp, home, settings_dir, tmp_path, launched, window):
    assert window.local_banner.isHidden()                       # a published release: no banner
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                      local_build=Path("/home/me/bc250-bazzite-suite"))
    assert not w.local_banner.isHidden()
    assert "checkout /home/me/bc250-bazzite-suite" in w.local_banner.text()
    w.close()


def portal_window(tmp_path, release):
    return mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"),
                         portal_check=lambda: release)


def test_newer_portal_release_is_offered(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    opened = []
    monkeypatch.setattr(mw.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    release = ReleaseInfo(version="99.0.0", tag="portal-v99.0.0", url="https://example.invalid/r", published="2030-01-01")
    w = portal_window(tmp_path, release)
    assert wait_for(lambda: not w.portal_button.isHidden())
    assert w.portal_button.text().endswith("Portal 99.0.0 available")
    w.portal_button.click()
    assert opened == ["https://example.invalid/r"]
    w.close()


@pytest.mark.parametrize("release", [ReleaseInfo(version="0.0.1", tag="portal-v0.0.1"),
                                     ReleaseInfo(error="no connection (offline)"), ReleaseInfo()])
def test_no_portal_offer_when_not_newer_or_offline(qapp, home, settings_dir, tmp_path, launched, release):
    w = portal_window(tmp_path, release)
    assert wait_for(lambda: not w.portal_checker.running, 3000)
    assert w.portal_button.isHidden()
    w.close()


def test_tiles_flow_in_file_order(window, qapp):
    window.show()
    for category in ("sustainable", "gaming"):
        window.tabs.setCurrentWidget(window.pages[category])
        tiles = [card for card in window.cards.values() if card.entry.category == category]
        for width in (1400, 700, 300, 1400):
            window.resize(width, 720)
            qapp.processEvents()
            page = window.pages[category]
            columns = window.columns
            assert columns == window.column_count(page.width() - page.verticalScrollBar().sizeHint().width()
                                                  - mw.PAGE_MARGIN), width
            grid = window.grids[category]
            places = [grid.getItemPosition(grid.indexOf(card))[:2] for card in tiles]
            assert places == [(i // columns, i % columns) for i in range(len(tiles))]   # file order, by rows
    step = mw.TILE_WIDTH + mw.TILE_SPACING
    assert window.column_count(0) == 1
    assert window.column_count(3 * step - mw.TILE_SPACING) == 3 and window.column_count(3 * step - 13) == 2


def test_a_tab_per_category_in_order(window):
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == [
        "Sustainable", "Graphics", "Gaming", "Utilities", "Development", "Install all apps"]    # the last: a button
    for key, card in window.cards.items():
        inside = [c for c, grid in window.grids.items() if grid.indexOf(card) >= 0]
        assert inside == [card.entry.category], key
    assert {k for k, c in window.cards.items() if c.entry.category == "graphics"} == {"upscaler", "ace", "mesh"}
    assert window.tabs.currentWidget() is window.pages["sustainable"]           # the first tab, the first time


def test_bazzite_test_is_the_first_tile_on_sustainable(window):
    """Bazzite Test is pinned as the first tile on the Sustainable tab; the notice of updates stays above the tabs
    (owner, 20-10-2026)."""
    grid = window.grids["sustainable"]
    assert grid.itemAtPosition(0, 0).widget() is window.cards["check"]
    assert window.tabs.isAncestorOf(window.cards["check"]) and not window.tabs.isAncestorOf(window.notice)


def test_the_portal_always_opens_on_the_first_tab(qapp, home, settings_dir, tmp_path, launched):
    """Whatever tab was open last (owner, 20-10-2026)."""
    w = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    w.tabs.setCurrentWidget(w.pages["gaming"])
    w.close()
    again = mw.MainWindow(load(MANIFEST), FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    assert again.tabs.currentIndex() == 0 and again.tabs.currentWidget() is again.pages["sustainable"]
    again.close()


def test_a_link_in_the_notice_opens_the_tab_of_its_app(window, home):
    (home / ".local" / "bin" / "bc250-rpcs3-manager").write_text("#!/bin/sh\n")
    window.records.set("rpcs3", "rpcs3-v0.0.1")
    window.refresh()
    assert "<a href='rpcs3'>RPCS3 Manager</a> (Gaming)" in window.notice.text()
    window.notice.linkActivated.emit("rpcs3")
    assert window.tabs.currentWidget() is window.pages["gaming"]
    window.notice.linkActivated.emit("check")                                   # on Sustainable
    assert window.tabs.currentWidget() is window.pages["sustainable"]


def test_development_tab_says_it_is_not_needed(window):
    page = window.pages["development"].widget()
    assert "You do not need these to use the board." in page.findChild(mw.QLabel).text()
    assert {k for k, c in window.cards.items() if c.entry.development} == {"mtool", "package", "ncgui"}


def test_no_tab_without_its_apps(qapp, home, settings_dir, tmp_path, launched):
    entries = [e for e in load(MANIFEST) if e.category not in ("gaming", "development")]
    w = mw.MainWindow(entries, FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    assert list(w.pages) == ["sustainable", "graphics", "utilities"]
    w.close()


def test_checkout_only_app_has_no_update(qapp, home, settings_dir, tmp_path, launched):
    entries = load(MANIFEST) + load_checkout(MANIFEST)
    sources = FakeSources(tmp_path / "work")
    sources.checkout = Path("/checkout")                                    # a portal from a checkout
    w = mw.MainWindow(entries, sources, Records(tmp_path / "installed.json"))
    card = w.cards["suite"]
    assert w.grids["development"].indexOf(card) >= 0
    (home / ".local" / "bin" / "bc250-release").write_text("#!/bin/sh\n")
    w.records.set("suite", "local")
    w.refresh()
    assert card.status == "Installed" and card.dot.isHidden() and "suite checkout" in card.icon.toolTip()
    w.close()


def test_portal_offer_names_the_app_updates(qapp, home, settings_dir, tmp_path, launched):
    from bc250_portal.portal_update import AppChange, PortalUpdate
    release = ReleaseInfo(version="99.0.0", tag="portal-v99.0.0", url="https://example.invalid/r", published="2030-01-01")
    update = PortalUpdate(release, [AppChange("BC-250 ACE Queues", "0.1.0", "0.1.1"),
                                    AppChange("BC-250 Memory Manager", "0.1.0", "0.1.1")])
    w = portal_window(tmp_path, update)
    assert wait_for(lambda: not w.portal_button.isHidden())
    assert w.portal_button.text().endswith("Portal 99.0.0: updates ACE Queues and Memory Manager")
    tip = w.portal_button.toolTip()
    assert "App updates come with the portal" in tip and "BC-250 Memory Manager: 0.1.0 → 0.1.1" in tip
    w.close()
    same = portal_window(tmp_path, PortalUpdate(release, []))
    assert wait_for(lambda: not same.portal_button.isHidden())
    assert same.portal_button.text().endswith("Portal 99.0.0 available") and "same app versions" in same.portal_button.toolTip()
    same.close()


SUITE = Path(__file__).resolve().parents[2]                                  # this checkout


def test_a_release_portal_finds_the_checkout_without_asking(qapp, home, settings_dir, tmp_path, launched,
                                                            monkeypatch):
    """A portal installed from a release installs the checkout-only apps too, from the checkout on this machine."""
    from bc250_portal import remembered_checkout
    monkeypatch.setattr(mw.QFileDialog, "getExistingDirectory", lambda *a: pytest.fail("asked for a folder"))
    monkeypatch.setattr(QMessageBox, "question", lambda *a: pytest.fail("asked a question"))
    (home / ".local/bin/bc250-release").write_text(f'#!/bin/sh\nexec "{SUITE}/apps/suite/run.sh"\n')
    entries = load(MANIFEST) + load_checkout(MANIFEST)
    sources = FakeSources(tmp_path / "work")                                # a release: no checkout of its own
    w = mw.MainWindow(entries, sources, Records(tmp_path / "installed.json"))
    w.install(w.cards["installer-tests"].entry)
    assert wait_for(lambda: launched)
    assert sources.apps_checkout == SUITE and remembered_checkout() == SUITE
    assert launched[0][0].startswith(f"cd {SUITE / 'tools/installer-tests/gui'} && ")
    assert sources.prepared == ["installer-tests"] and w.pending.tag == "local"
    assert sources.folder(w.cards["gpu"].entry).name == w.cards["gpu"].entry.tag   # releases as before
    w.cancel_pending()
    w.close()


def test_without_a_checkout_it_asks_first(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    from bc250_portal import remembered_checkout
    entries = load(MANIFEST) + load_checkout(MANIFEST)
    sources = FakeSources(tmp_path / "work")
    w = mw.MainWindow(entries, sources, Records(tmp_path / "installed.json"))
    card = w.cards["installer-tests"]
    assert card.status == "Not installed" and card.install_button.isEnabled() and "found no checkout" in card.icon.toolTip()
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a: asked.append(a[2]) or QMessageBox.StandardButton.No)
    monkeypatch.setattr(mw.QFileDialog, "getExistingDirectory", lambda *a: pytest.fail("no folder without a yes"))
    w.install(card.entry)
    assert "found none" in asked[0] and sources.prepared == [] and remembered_checkout() is None
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(mw.QFileDialog, "getExistingDirectory", lambda *a: str(SUITE))
    w.install(card.entry)
    assert wait_for(lambda: launched) and remembered_checkout() == SUITE
    w.cancel_pending()
    w.close()


def test_a_folder_that_is_not_the_suite_is_refused(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    from bc250_portal import remembered_checkout
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text, *a: warned.append(text))
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(mw.QFileDialog, "getExistingDirectory", lambda *a: str(tmp_path))
    entries = load(MANIFEST) + load_checkout(MANIFEST)
    sources = FakeSources(tmp_path / "work")
    w = mw.MainWindow(entries, sources, Records(tmp_path / "installed.json"))
    w.install(w.cards["suite"].entry)
    assert "is not a BC250 Bazzite Suite checkout" in warned[0]
    assert sources.apps_checkout is None and sources.prepared == [] and remembered_checkout() is None
    w.close()


def test_an_installed_checkout_app_still_opens(qapp, home, settings_dir, tmp_path, launched):
    entries = load(MANIFEST) + load_checkout(MANIFEST)
    w = mw.MainWindow(entries, FakeSources(tmp_path / "work"), Records(tmp_path / "installed.json"))
    (home / ".local" / "bin" / "bc250-release").write_text("#!/bin/sh\n")   # installed from a checkout before
    w.refresh()
    card = w.cards["suite"]
    assert card.status == "Reinstall needed" and card.icon.isEnabled() and card.uninstall_button.isEnabled()
    assert w.cards["mtool"].install_button.isEnabled()                  # released development apps as usual
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
        card = w.cards["upscaler"]
        assert not card.withdrawn.isHidden() and card.withdrawn.text() == "App not available"
        assert card.status == "App not available" and not card.install_button.isEnabled()
        assert "Privacy: shows the account ID." in card.install_button.toolTip()
        assert "It cannot be installed." in card.icon.toolTip()
        assert w.cards["gpu"].withdrawn.isHidden()
        w.remove_withdrawn()                                # not installed: nothing to remove
        assert launched == []
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
        card = w.cards["upscaler"]
        assert not card.icon.isEnabled() and card.dot.isHidden()          # no opening, no update
        (home / ".local" / "bin" / "bc250-upscaler").unlink()
        exit_file.write_text("0\n")
        w._check_pending()
        assert card.status == "App not available" and "It cannot be installed." in card.icon.toolTip()
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
        card = w.cards["upscaler"]
        assert card.uninstall_button.isEnabled()            # the user can try again by hand
        assert "The portal removes it from the board." in card.icon.toolTip()
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
    assert not w.portal_button.isHidden()
    _installed(tmp_path, "99.0.0")                                           # its install.sh ran in a terminal
    w.check_installed()
    assert w.restart_button.text() == "\u25cf Restart: portal 99.0.0 is installed"
    assert w.restart_button.isEnabled() and w.portal_button.isHidden()
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
    """The theme pill shows the chosen theme; a click takes the next one, for every app; the portal says when it
    shows."""
    from bc250_core import theme
    pill = window.theme_pill
    assert theme.theme_name() == "gunmetal" and pill.value.text() == "Gunmetal"
    assert pill.caption.text() == "Theme switcher"
    assert window.theme_note.isHidden()
    seen = []
    for _ in range(3):
        pill.click()
        seen.append((theme.theme_name(), pill.value.text()))
    assert seen == [("silver", "Silver"), ("warm", "Warm"), ("gunmetal", "Gunmetal")]
    assert theme.theme_file().is_relative_to(home) and not window.theme_note.isHidden()


def test_the_header_is_an_apps_header_with_pills(window):
    """The portal's icon as large as the tiles' icons; beside it the name, where the apps install from, and the
    pills: Refresh, Installed apps, Install all updates, the Desktop icons, the theme, the wallpaper and Sys info
    (owner, 20-10-2026 and 21-10-2026)."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent
    assert window.logo.width() == window.logo.height() == mw.ICON_PX
    pills = (window.refresh_pill, window.installed_pill, window.updates_pill, window.icons_box, window.theme_pill,
             window.wallpaper_pill, window.sysinfo_pill)
    listed = len(window.entries)
    assert [(p.value.text(), p.caption.text()) for p in pills] == [
        ("Refresh", "Click to refresh"), (f"0/{listed}", "Installed apps"), ("0", "Install all updates"),
        ("No", "Icons on Desktop"), ("Gunmetal", "Theme switcher"), ("None", "Wallpaper"), ("Sys info", "Click to view")]
    assert all(f"border-left:4px solid {mw.BLUE}" in p.styleSheet() for p in pills)     # as the apps' boxes
    widths = {p.width() for p in pills}                     # all as wide as the widest (owner, 20-10-2026)
    assert len(widths) == 1 and widths.pop() >= max(p.sizeHint().width() for p in pills)
    refreshed = []
    window.refresh_pill.clicked.connect(lambda: refreshed.append(1))
    window.refresh_pill.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier))
    assert refreshed == [1]
    toggled = []
    window.icons_box.toggled.connect(toggled.append)
    window.icons_box.click()
    assert window.icons_box.isChecked() and window.icons_box.value.text() == "Yes" and toggled == [True]
    window.icons_box.setChecked(True)                       # no change: no signal
    assert toggled == [True]


def test_the_tabs_are_as_large_as_the_pills(window, qapp):
    """Each category tab as wide and as high as a header pill (owner, 21-10-2026), also after the pills widen; a gap
    above the tabs, so the line over them is a divider."""
    window.show()
    qapp.processEvents()
    bar, pill = window.tabs.tabBar(), window.refresh_pill
    categories = range(len(window.pages))                    # the action tab is as wide as its text needs
    assert {bar.tabRect(i).width() for i in categories} == {pill.width()}
    assert {bar.tabRect(i).height() for i in range(bar.count())} == {pill.height() + mw.PillTabBar.GAP}  # the gap
    window.theme_pill.set_value("A much longer theme name")
    qapp.processEvents()
    assert pill.minimumWidth() > 0 and bar.tabRect(0).width() == pill.minimumWidth()


def test_the_sys_info_pill_opens_one_window_read_each_time(window, qapp, monkeypatch):
    """Sys info (owner, 20-10-2026): a small window with what the system reports, read again each time it opens;
    Copy puts it on the clipboard as text."""
    reads = iter([[("Board", [("Board", "ASRock AMD BC-250")])],
                  [("Board", [("Board", "ASRock AMD BC-250")]), ("BIOS", [("Version", "P5.00")])]])
    monkeypatch.setattr(mw.sysinfo, "collect", lambda: next(reads))
    window.sysinfo_pill.click()
    first = window.sysinfo_window
    assert first.isVisible() and [h for h, _ in first.sections] == ["Board"]
    from PyQt6.QtCore import Qt
    assert first.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)    # semi-transparent (owner, 20-10-2026)
    picture = first.grab().toImage()
    assert picture.pixelColor(2, 2).alphaF() == pytest.approx(mw.SYSINFO_OPACITY / 100, abs=0.01)
    window.sysinfo_pill.click()
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
    assert window.wallpaper_pill.value.text() == "Custom" and not window.backdrop.picture.isNull()
    good.unlink()                                           # the portal keeps its own copy
    window.resize(900, 700)
    window.show()
    assert QColor(window.backdrop.grab().toImage().pixel(450, 600)).red() > 60      # red under the veil
    window.remove_wallpaper()
    assert wallpaper.current() is None and window.wallpaper_pill.value.text() == "None"
    assert window.backdrop.picture.isNull()


def test_the_example_wallpaper(window):
    """The portal ships an example wallpaper, to show how one looks, but never sets it by itself: the user chooses it
    in the menu (owner, 20-10-2026). It meets the portal's own rules."""
    from PyQt6.QtGui import QColor, QImage
    from bc250_portal import wallpaper

    def menu() -> dict[str, tuple[bool, bool]]:
        return {a.text(): (a.isChecked(), a.isEnabled()) for a in window.wallpaper_menu().actions()}

    assert wallpaper.EXAMPLE.is_file() and wallpaper.problem(wallpaper.EXAMPLE) == ""
    assert wallpaper.shown() is None and window.wallpaper_pill.value.text() == "None"   # none at first
    assert window.backdrop.picture.isNull() and menu()["Example wallpaper"] == (False, True)
    assert not menu()["No wallpaper"][1]
    window.example_wallpaper()
    assert wallpaper.shown() == wallpaper.EXAMPLE and wallpaper.current() is None
    assert window.wallpaper_pill.value.text() == "Example" and not window.backdrop.picture.isNull()
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
        pixel = QColor(window.backdrop.grab().toImage().pixel(450, 600))
        return sum(abs(a - b) for a, b in zip(pixel.getRgb()[:3], veil.getRgb()[:3]))

    before = distance()
    window.transparency_slider.setValue(88)                 # rounded to the step
    assert window.backdrop.veil == 90 and window.settings.value(mw.VEIL_KEY, type=int) == 90
    assert distance() < before                              # nearer the theme's own color
    assert "Transparency 90 %" in window.wallpaper_pill.toolTip()
    window.settings.setValue(mw.VEIL_KEY, 250)              # a value from elsewhere: kept within the slider's range
    assert window.transparency() == 90


def test_a_checkout_install_is_compared_by_its_version(window, home):
    """A portal from a release, an app installed from a checkout (owner, 26-10-2026): the recorded version against
    the pin, as a tag's; a record without one (portal 9.2.0 and earlier) needs a reinstall."""
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    card = window.cards["gpu"]
    window.records.set("gpu", "local-v0.0.9")
    window.refresh()
    assert card.status == "Update" and not card.dot.isHidden() and card.badge.isHidden()
    assert "installed from the suite checkout (v0.0.9), this portal pins" in card.icon.toolTip()
    assert "installed from the suite checkout (v0.0.9)" in window.notice.text()
    window.records.set("gpu", f"local-v{card.entry.version}")
    window.refresh()
    assert card.status == "Installed" and card.dot.isHidden() and card.badge.isHidden()
    assert f"Installed from the suite checkout (v{card.entry.version})." in card.icon.toolTip()
    assert "No updates" in window.notice.text()
    window.records.set("gpu", "local")
    window.refresh()
    assert card.status == "Reinstall needed" and not card.badge.isHidden() and card.dot.isHidden()
    assert "without recording its version" in card.icon.toolTip() and "suite checkout" in card.badge.toolTip()
    assert "1 reinstall" in window.notice.text()


def test_a_checkout_portal_shows_its_own_installs_as_installed(qapp, home, settings_dir, tmp_path, launched):
    sources = FakeSources(tmp_path / "work")
    sources.checkout = Path("/checkout")                                    # a portal from a checkout
    w = mw.MainWindow(load(MANIFEST), sources, Records(tmp_path / "installed.json"))
    (home / ".local" / "bin" / "bc250-governor-manager").write_text("#!/bin/sh\n")
    card = w.cards["gpu"]
    for record in ("local-v0.0.9", "local"):
        w.records.set("gpu", record)
        w.refresh()
        assert card.status == "Installed" and card.dot.isHidden() and card.badge.isHidden()
        assert "No updates" in w.notice.text()
    assert "Installed from the suite checkout (v0.0.9)." not in card.icon.toolTip()
    assert "Installed from the suite checkout." in card.icon.toolTip()
    w.records.set("gpu", "gpu-v0.0.9")                                      # from a release: an update, as before
    w.refresh()
    assert card.status == "Update"
    w.close()


def test_a_checkout_install_records_the_staged_version(qapp, home, settings_dir, tmp_path, launched, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: YES)
    sources = FakeSources(tmp_path / "work")
    sources.checkout = Path("/checkout")
    w = mw.MainWindow(load(MANIFEST), sources, Records(tmp_path / "installed.json"))
    entry = w.cards["upscaler"].entry
    folder = sources.folder(entry)
    folder.mkdir(parents=True)
    (folder / "VERSION").write_text("1.2.3\n")
    w.install(entry)
    assert wait_for(lambda: launched)
    assert w.pending.tag == "local-v1.2.3"
    w.cancel_pending()
    w.close()
