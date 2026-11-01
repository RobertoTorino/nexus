# SPDX-License-Identifier: GPL-3.0-or-later
"""The setup screens as the window lists them (screens.py): the pages, a menu's lines with their values, the hidden
ones only when asked, and everything about one setting."""

from __future__ import annotations

from bios_reader import bios, screens
from bios_reader.bios import Identity


def load(bios_file):
    b = bios.load_file(bios_file)
    return b, bios.Screens(b)


def test_the_pages(bios_file):
    _, sc = load(bios_file)
    assert [p.title for p in screens.pages(sc)] == ["Main"]
    shown = screens.pages(sc, show_hidden=True)
    assert [p.title for p in shown] == ["Main", "Hidden tab", screens.UNLINKED]
    assert shown[1].hidden_reason and shown[2].hidden_reason
    orphan = shown[2].form.statements
    assert [(st.kind, st.prompt) for st in orphan] == [("subtitle", "Setup"), ("ref", "Orphan")]


def test_a_long_title_is_cut_at_a_word():
    warning = ("WARNING - DAMAGE CAUSED BY USE OF YOUR AMD PROCESSOR OUTSIDE OF SPECIFICATION OR IN EXCESS OF "
               "FACTORY SETTINGS\r\nOperating your AMD processor ...")
    assert screens.short(warning) == "WARNING - DAMAGE CAUSED BY USE OF YOUR AMD …"
    assert screens.short("AMD Overclocking") == "AMD Overclocking"


def test_a_menus_lines(bios_file):
    b, sc = load(bios_file)
    main = screens.pages(sc)[0]
    lines = screens.entries(sc, main.formset, main.form)
    assert [(e.prompt, e.value) for e in lines] == [
        ("BIOS Info", ""), ("BIOS Vendor", "Vendor Inc."), ("Mode", "On"), ("Feature", "Disabled"),
        ("Level", "0x1234"), ("Detail", "Auto"), ("Sub", "")]
    assert lines[0].statement is None and lines[-1].link
    assert not any(e.hidden for e in lines)
    device = screens.entries(sc, main.formset, main.form, identity=Identity("Maker", "P9.99", ""))
    assert device[1].value == "Maker"                               # the BIOS's version texts show the device's


def test_hidden_lines_only_when_asked(bios_file):
    b, sc = load(bios_file)
    b.device = {b.stores()[0]: bytes([0, 0, 0, 0, 0, 0, 0, 0])}    # Mode Off: Detail is hidden
    sc = bios.Screens(b)
    main = screens.pages(sc)[0]
    assert "Detail" not in [e.prompt for e in screens.entries(sc, main.formset, main.form)]
    detail = next(e for e in screens.entries(sc, main.formset, main.form, show_hidden=True) if e.prompt == "Detail")
    assert detail.hidden
    tab = screens.pages(sc, show_hidden=True)[1]
    assert all(e.hidden for e in screens.entries(sc, tab.formset, tab.form, show_hidden=True))


def test_everything_about_a_setting(bios_file):
    b, sc = load(bios_file)
    main = screens.pages(sc)[0]
    mode = next(st for st in main.form.statements if st.prompt == "Mode")
    text = screens.detail(sc, main.formset, main.form, mode)
    assert text.startswith("Pick a mode")
    assert "Value: On (from the file)" in text and "Default: Off" in text
    assert "Stored at: Setup + 0x0 (1 byte)" in text and "  Off (default)" in text
    assert screens.summary(sc, main.formset, main.form, mode) == "On, from the file  ·  default Off"
    b.stored = {}
    sc = bios.Screens(b)
    assert screens.summary(sc, main.formset, main.form, mode) == "Off, from the default"
    link = next(st for st in main.form.statements if st.prompt == "Sub")
    assert "opens this menu" in screens.detail(sc, main.formset, main.form, link)
    assert screens.target(sc, main.formset, link)[1].title == "Sub"


def test_a_setting_without_a_value(bios_file):
    b, _ = load(bios_file)
    b.stored, b.defaults = {}, {}
    sc = bios.Screens(b)
    main = screens.pages(sc)[0]
    mode = next(st for st in main.form.statements if st.prompt == "Mode")
    assert "Value: not known (the file has no Setup)" in screens.detail(sc, main.formset, main.form, mode)
    assert screens.summary(sc, main.formset, main.form, mode).startswith("Its value is not known")
