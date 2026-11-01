# SPDX-License-Identifier: GPL-3.0-or-later
"""A BIOS file (bios.py): read as it is or from its zip, its version, its setup screens, and which value a setting
shows (the device's, else the file's, else the default) with the conditions following it."""

from __future__ import annotations

import zipfile

import fake_bios
import pytest
from conftest import ASUS_MARKER

from bios_reader import bios, firmware


def item(fs, prompt):
    return next(st for form in fs.forms for st in form.statements if st.prompt == prompt)


def test_a_flash_image(bios_file):
    b = bios.load_file(bios_file)
    assert b.name == "bios.bin" and len(b.sha256) == 64
    assert (b.identity.vendor, b.identity.version, b.identity.date) == ("Vendor Inc.", "P9.99", "01/02/2023")
    assert [fs.title for fs in b.formsets] == ["Setup"]
    assert b.stores() == [(str(fake_bios.SETUP_GUID).upper(), "Setup")]


def test_a_makers_update_in_its_zip(update_zip):
    """The largest file in the zip is the image; ASUS's marker names the version, not the SMBIOS template."""
    b = bios.load_file(update_zip)
    assert b.name == "RC00XAAS.123"
    assert b.identity.version == "RC00XA.123" and b.identity.vendor == "Vendor Inc."


def test_amis_template_is_no_version(tmp_path, monkeypatch):
    """A file's SMBIOS table is AMI's template until the BIOS boots: its "5.35" of 12/12/2012 is not the version.
    (The fake's table is dated 01/02/2023, inside its packed volume: that date stands for the template's here.)"""
    monkeypatch.setattr(bios, "TEMPLATE_DATE", "01/02/2023")
    path = tmp_path / "x.cap"
    path.write_bytes(fake_bios.image(version="5.35"))
    found = bios.load_file(path).identity
    assert found.version == "" and found.vendor == "Vendor Inc."


def test_what_is_not_a_bios_file(tmp_path, monkeypatch):
    empty = tmp_path / "empty.zip"
    zipfile.ZipFile(empty, "w").close()
    with pytest.raises(bios.BiosError, match="empty"):
        bios.load_file(empty)
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"PK not a zip")
    with pytest.raises(bios.BiosError, match="not a zip"):
        bios.load_file(broken)
    other = tmp_path / "ec.bin"
    other.write_bytes(b"\xff" * 4096)
    with pytest.raises(firmware.FirmwareError):
        bios.load_file(other)
    no_screens = tmp_path / "noscreens.bin"
    no_screens.write_bytes(fake_bios.image(module=b"MZ" + bytes(200)))
    with pytest.raises(bios.BiosError, match="no setup screens"):
        bios.load_file(no_screens)
    monkeypatch.setattr(bios, "MAX_SIZE", 100)
    with pytest.raises(bios.BiosError, match="larger"):
        bios.load_file(no_screens)
    with pytest.raises(bios.BiosError, match="could not be read"):
        bios.load_file(tmp_path / "gone.bin")


def test_the_browser_finds_asus_numbered_files():
    assert "RC73XAAS.319".lower().endswith(bios.SUFFIXES)
    assert "x.CAP".lower().endswith(bios.SUFFIXES) and "x.zip".endswith(bios.SUFFIXES)
    assert not "notes.txt".endswith(bios.SUFFIXES)


def test_which_value_a_setting_shows(bios_file):
    """The device's variable, else the file's stored one, else the default."""
    b = bios.load_file(bios_file)
    sc = bios.Screens(b)
    fs = b.formsets[0]
    mode = item(fs, "Mode")
    assert sc.raw_value(fs, mode) == 1 and sc.source(fs, mode) == bios.FILE
    assert sc.default_value(fs, mode) == 0
    b.stored = {}
    sc = bios.Screens(b)
    assert sc.raw_value(fs, mode) == 0 and sc.source(fs, mode) == bios.DEFAULT
    b.device = {b.stores()[0]: bytes([1, 1, 0, 0, 0, 0, 0, 0])}
    sc = bios.Screens(b)
    assert sc.raw_value(fs, mode) == 1 and sc.source(fs, mode) == bios.DEVICE


def test_conditions_follow_the_values(bios_file):
    b = bios.load_file(bios_file)
    fs = b.formsets[0]
    assert not bios.Screens(b).item_state(fs, item(fs, "Detail")).hidden      # Mode On: Detail shows
    b.device = {b.stores()[0]: bytes([0, 1, 0, 0, 0, 0, 0, 0])}
    sc = bios.Screens(b)
    detail = sc.item_state(fs, item(fs, "Detail"))
    assert detail.hidden and not detail.always
    assert sc.item_state(fs, item(fs, "Deep")).grayed                          # Feature on: Deep is locked
    assert sc.item_state(fs, item(fs, "Hidden tab")).always


def test_a_value_without_a_variable_makes_a_condition_unknown(bios_file):
    b = bios.load_file(bios_file)
    b.stored, b.defaults = {}, {}
    sc = bios.Screens(b)
    fs = b.formsets[0]
    assert sc.raw_value(fs, item(fs, "Mode")) is None and sc.source(fs, item(fs, "Mode")) == ""
    assert sc.default_value(fs, item(fs, "Mode")) == 0            # the form's own default
    assert sc.item_state(fs, item(fs, "Detail")).unknown


def test_hidden_and_unlinked_forms(bios_file):
    sc = bios.Screens(bios.load_file(bios_file))
    hidden = {form.title: reason for _, form, reason in sc.hidden_forms()}
    assert hidden == {"Hidden tab": 'its link "Hidden tab" is hidden', "Orphan": "not linked from any menu"}
    assert [form.title for _, form in sc.unlinked_forms()] == ["Orphan"]


def test_value_text(bios_file):
    fs = bios.load_file(bios_file).formsets[0]
    assert bios.value_text(item(fs, "Level"), 0x1234) == "0x1234"
    assert bios.value_text(item(fs, "Mode"), 1) == "On"
    assert bios.value_text(item(fs, "Mode"), 7) == "0x7 (not one of the options)"
    assert bios.value_text(item(fs, "Feature"), 0) == "Disabled"
    assert bios.value_text(item(fs, "Feature"), None) == "?"


def test_the_marker_is_found_in_the_image():
    assert bios.ASUS_VERSION.search(b"xx" + ASUS_MARKER)[1] == b"RC00XA.123"
