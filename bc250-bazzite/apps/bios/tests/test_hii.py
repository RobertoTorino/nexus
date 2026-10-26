# SPDX-License-Identifier: GPL-3.0-or-later
import struct

import fake_bios

from bios_reader import hii


def formset() -> hii.FormSet:
    sets = hii.read_module(fake_bios.setup_module(), "Setup")
    assert len(sets) == 1
    return sets[0]


def statements(fs: hii.FormSet, form_id: int) -> dict[str, hii.Statement]:
    return {st.prompt: st for st in fs.form(form_id).statements}


def test_packages_are_found_among_other_bytes():
    module = fake_bios.setup_module()
    assert hii.find_form_packages(module) == [fake_bios.form_package()]
    assert hii.find_string_packages(module) == [fake_bios.string_package()]


def test_form_set_header_and_varstore():
    fs = formset()
    assert fs.guid == str(fake_bios.FORMSET).upper()
    assert (fs.title, fs.help, fs.module) == ("Setup", "Setup help", "Setup")
    store = fs.varstores[1]
    assert (store.name, store.size, store.guid) == ("Setup", 8, str(fake_bios.SETUP_GUID).upper())
    assert [f.title for f in fs.forms] == ["Setup", "Main", "Hidden tab", "Sub", "Orphan"]


def test_questions():
    main = statements(formset(), 2)
    mode = main["Mode"]
    assert (mode.kind, mode.question_id, mode.offset, mode.size, mode.help) == ("oneof", 1, 0, 1, "Pick a mode")
    assert [(o.text, o.value, o.default) for o in mode.options] == [("Off", 0, True), ("On", 1, False)]
    assert mode.default == 0
    assert (main["Feature"].kind, main["Feature"].default) == ("checkbox", 1)
    level = main["Level"]
    assert (level.size, level.maximum, level.hex_display) == (2, 0x1FF, True)
    assert main["BIOS Vendor"].text == "N/A"
    assert main["Sub"].kind == "ref" and main["Sub"].target_form == 4


def test_conditions_are_kept_in_postfix_order():
    fs = formset()
    detail = statements(fs, 2)["Detail"]
    assert [(c.kind, c.expr) for c in detail.conditions] == [("suppress", [("eq_id_val", 1, 1), ("not",)])]
    hidden = statements(fs, 1)["Hidden tab"]
    assert hidden.conditions[0].expr == [("true",)]
    deep = statements(fs, 4)["Deep"]
    assert deep.conditions[0].kind == "grayout"
    assert statements(fs, 2)["Mode"].conditions == []           # the condition's scope ended before it


def test_string_blocks():
    lang = b"en-US\0"
    blocks = (b"\x14" + "One".encode("utf-16-le") + b"\0\0" +
              b"\x22\x02" +                                        # skip ids 2 and 3
              b"\x16" + struct.pack("<H", 2) + "Four".encode("utf-16-le") + b"\0\0" + "Five".encode("utf-16-le")
              + b"\0\0" + b"\x20" + struct.pack("<H", 1) +         # 6 duplicates 1
              b"\x10" + b"Seven\0" + b"\x00")
    body = struct.pack("<II", 52, 52) + bytes(34) + lang + blocks
    pkg = (len(body) + 4).to_bytes(3, "little") + b"\x04" + body
    assert hii.parse_strings(pkg) == {1: "One", 4: "Four", 5: "Five", 6: "One", 7: "Seven"}


def test_module_without_forms():
    assert hii.read_module(b"MZ" + bytes(100)) == []
