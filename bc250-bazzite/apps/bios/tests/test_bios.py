# SPDX-License-Identifier: GPL-3.0-or-later
import fake_bios
import pytest

from bios_reader import bios, table


def screens(dump_file, sys_root) -> tuple[bios.Screens, object]:
    b = bios.load_dump(dump_file, sys_root)
    return bios.Screens(b), b.formsets[0]


def item(fs, prompt):
    return next(st for form in fs.forms for st in form.statements if st.prompt == prompt)


def test_load_dump(dump_file, sys_root):
    b = bios.load_dump(dump_file, sys_root)
    assert (b.source, b.version, b.date, b.vendor) == ("dump", "P9.99", "01/02/2023", "Vendor Inc.")
    assert len(b.dump_sha256) == 64
    assert [fs.title for fs in b.formsets] == ["Setup"]


def test_values_and_defaults(dump_file, sys_root):
    sc, fs = screens(dump_file, sys_root)
    assert sc.raw_value(fs, item(fs, "Mode")) == 1
    assert sc.default_value(fs, item(fs, "Mode")) == 0
    assert sc.raw_value(fs, item(fs, "Level")) == 0x1234
    assert bios.value_text(item(fs, "Level"), 0x1234) == "0x1234"
    assert bios.value_text(item(fs, "Mode"), 1) == "On"
    assert bios.value_text(item(fs, "Mode"), 7) == "0x7 (not one of the options)"
    assert bios.value_text(item(fs, "Feature"), 0) == "Disabled"
    assert sc.store_label(fs, item(fs, "Level")) == "Setup + 0x2"


def test_item_states(dump_file, sys_root):
    sc, fs = screens(dump_file, sys_root)
    assert not sc.item_state(fs, item(fs, "Detail")).hidden      # Mode is 1, so Detail shows
    hidden_tab = sc.item_state(fs, item(fs, "Hidden tab"))
    assert hidden_tab.hidden and hidden_tab.always
    assert not sc.item_state(fs, item(fs, "Deep")).grayed       # Feature is 0


def test_condition_follows_the_values(tmp_path, sys_root):
    path = tmp_path / "b.bin"
    path.write_bytes(fake_bios.image(setup_now=bytes([0, 1, 0, 0, 0, 0, 0, 0])))
    sc, fs = screens(path, sys_root)
    detail = sc.item_state(fs, item(fs, "Detail"))
    assert detail.hidden and not detail.always
    assert sc.item_state(fs, item(fs, "Deep")).grayed


def test_unreadable_value_makes_a_condition_unknown(sys_root, tables_dir):
    b = bios.load_running(sys_root, tables_dir)                  # no Setup variable while running
    sc = bios.Screens(b)
    fs = b.formsets[0]
    assert sc.raw_value(fs, item(fs, "Mode")) is None
    assert sc.default_value(fs, item(fs, "Mode")) == 0
    assert sc.item_state(fs, item(fs, "Detail")).unknown


def test_forms_behind_hidden_links(dump_file, sys_root):
    sc, fs = screens(dump_file, sys_root)
    assert sc.form_state(fs, 2) == ""
    assert sc.form_state(fs, 4) == ""
    assert "Hidden tab" in sc.form_state(fs, 3)
    assert sc.form_state(fs, 5) == "not linked from any menu"
    assert [f.title for _, f in sc.unlinked_forms()] == ["Orphan"]
    assert sorted(f.title for _, f, _ in sc.hidden_forms()) == ["Hidden tab", "Orphan"]


@pytest.mark.parametrize("expr, result", [
    ([("true",), ("not",)], False),
    ([("eq_id_val", 1, 1), ("eq_id_val", 2, 0), ("and",)], True),
    ([("eq_id_val", 1, 0), ("eq_id_val", 99, 0), ("or",)], None),      # question 99 does not exist
    ([("eq_id_val", 1, 0), ("eq_id_val", 99, 0), ("and",)], False),    # one side false is enough
    ([("question_ref1", 3), ("const", 0x1000), ("greater_than",)], True),
    ([("eq_id_list", 1, (0, 1))], True),
    ([("map",)], None),
    ([("not",)], None),
])
def test_evaluate(dump_file, sys_root, expr, result):
    sc, fs = screens(dump_file, sys_root)
    assert sc.evaluate(fs, expr) is result


def test_efivars_and_dmi(sys_root):
    values = bios.read_efivars(sys_root)
    assert values[("3A997502-647A-4C82-998E-52EF9486A247", "AmdSetup")] == bytes(16)
    assert bios.read_dmi(sys_root) == bios.Dmi("Vendor Inc.", "P9.99", "01/02/2023")
    assert bios.read_efivars(sys_root / "nowhere") == {}


def test_running_without_a_table(sys_root, tmp_path):
    b = bios.load_running(sys_root, tmp_path / "empty")
    assert b.formsets == [] and "no built-in table" in b.note


def test_table_round_trip(dump_file, tables_dir):
    version, date, formsets, defaults = table.load_table(tables_dir / "P9.99.json.gz")
    assert (version, date) == ("P9.99", "01/02/2023")
    assert formsets == bios.load_dump(dump_file).formsets
    assert defaults[(str(fake_bios.SETUP_GUID).upper(), "Setup")] == bytes([0, 1, 0, 0, 0, 0, 0, 0])


# --- Stock or modded ---------------------------------------------------------------------------------------

def test_dump_of_a_stock_release(dump_file, sys_root, stock):
    v = bios.verdict(bios.load_dump(dump_file, sys_root))
    assert (v.kind, v.title, v.certain) == ("stock", "Stock BIOS P9.99", True)


def test_dump_with_changed_screens(tmp_path, sys_root, tables_dir, stock):
    # The same BIOS with the SuppressIf TRUE around "Hidden tab" turned into FALSE: a typical menu unlock.
    module = fake_bios.setup_module().replace(fake_bios.TRUE + fake_bios.ref("Hidden tab", 101, 3),
                                              fake_bios.op(0x47) + fake_bios.ref("Hidden tab", 101, 3))
    path = tmp_path / "modded.bin"
    path.write_bytes(fake_bios.image(module=module))
    modded = bios.load_dump(path, sys_root)
    version, date, formsets, defaults = table.load_table(tables_dir / "P9.99.json.gz")
    stock_screens = bios.Screens(bios.Bios(formsets, modded.values, defaults, "table", version, date))
    v = bios.verdict(modded, stock_screens)
    assert (v.kind, v.certain) == ("modded", True)
    assert "Setup" in v.reasons[0]
    assert any("Hidden tab" in r for r in v.reasons)


def test_dump_of_an_unknown_release(dump_file, sys_root):
    v = bios.verdict(bios.load_dump(dump_file, sys_root))
    assert v.kind == "unknown"


def test_running_stock(sys_root, tables_dir, stock):
    v = bios.verdict(bios.load_running(sys_root, tables_dir))
    assert (v.kind, v.certain) == ("stock", False)
    assert "read the BIOS chip" in v.reasons[-1]


def test_running_with_other_cbs_layout(sys_root, tables_dir, stock):
    (sys_root / f"firmware/efi/efivars/AmdSetup-{'3a997502-647a-4c82-998e-52ef9486a247'}").write_bytes(
        b"\x07\0\0\0" + bytes(20))
    v = bios.verdict(bios.load_running(sys_root, tables_dir))
    assert v.kind == "modded" and "20 bytes" in v.reasons[0]


@pytest.mark.parametrize("version, kind", [("P5.00 meimei", "modded"), ("3.00", "stock"), ("X1", "unknown")])
def test_running_version_strings(sys_root, tmp_path, version, kind):
    (sys_root / "class/dmi/id/bios_version").write_text(version)
    assert bios.verdict(bios.load_running(sys_root, tmp_path)).kind == kind


def test_smbios_bios_info():
    data = b"junk" + fake_bios.smbios_type0("AMI", "P5.00", "05/03/2022") + b"more"
    assert bios.smbios_bios(data) == bios.Dmi("AMI", "P5.00", "05/03/2022")
    assert bios.smbios_bios(b"\0\x18" + bytes(40)) == bios.Dmi()
