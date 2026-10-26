# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from bios_reader.main_window import MainWindow


@pytest.fixture
def window(qapp, sys_root, tables_dir, stock):
    w = MainWindow(sys_root, tables_dir)
    w.load_board()
    yield w
    w.close()


def tabs(w) -> list[str]:
    return [w.screen.tabs.tabText(i) for i in range(w.screen.tabs.count())]


def rows(w) -> list[tuple[str, str]]:
    items = w.screen.items
    return [(items.topLevelItem(i).text(0), items.topLevelItem(i).text(1)) for i in range(items.topLevelItemCount())]


def open_row(w, text):
    items = w.screen.items
    item = next(items.topLevelItem(i) for i in range(items.topLevelItemCount()) if items.topLevelItem(i).text(0) == text)
    items.setCurrentItem(item)
    w.screen._activate(item)


def test_running_board(window):
    assert window.badge.text() == "Stock BIOS P9.99"
    assert "This board" in window.source.text()
    assert window.note.text().startswith("The main Setup variable")
    assert tabs(window) == ["Main"]                               # the hidden tab is not listed
    assert ("BIOS Vendor", "Vendor Inc.") in rows(window)         # filled from DMI
    assert ("Mode", "[?]") in rows(window)                        # Setup is not readable while running
    assert not window.board_button.isEnabled()


def test_hidden_items_and_tabs(window):
    window.hidden_box.setChecked(True)
    assert tabs(window) == ["Main", "Hidden tab (hidden)", "Not linked (hidden)"]
    window.screen.tabs.setCurrentIndex(2)
    assert rows(window)[1][0] == "▶ Orphan"
    open_row(window, "▶ Orphan")
    assert rows(window)[0][0] == "Lost"
    assert window.screen.crumbs.text() == "Not linked  ›  Orphan"
    window.screen.go_back()
    assert window.screen.crumbs.text() == "Not linked"


def test_submenu_and_help(window, dump_file):
    assert window.load_dump_file(dump_file)
    assert window.badge.text() == "Stock BIOS P9.99"
    assert ("Mode", "[On]") in rows(window)
    assert ("Level", "[0x1234]") in rows(window)
    open_row(window, "▶ Sub")
    assert rows(window) == [("Deep", "[Disabled]")]
    html = window.screen.help_html(window.bios.formsets[0], window.bios.formsets[0].form(2).statements[2])
    assert "Pick a mode" in html and "Default" in html and "Setup + 0x0" in html
    window.load_board()
    assert window.source.text().startswith("<b>This board</b>")


def test_bad_dump_file(window, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a))
    bad = tmp_path / "x.bin"
    bad.write_bytes(bytes(100))
    assert not window.load_dump_file(bad)
    assert shown and window.bios.source == "running"


def test_show_hidden_is_remembered(qapp, sys_root, tables_dir, stock):
    w = MainWindow(sys_root, tables_dir)
    w.hidden_box.setChecked(True)
    w.close()
    again = MainWindow(sys_root, tables_dir)
    assert again.hidden_box.isChecked()
    again.close()
