# SPDX-License-Identifier: GPL-3.0-or-later
import uuid

import fake_bios
import pytest

from bios_reader import firmware


def test_volumes_and_nested_files(image):
    fw = firmware.parse_image(image)
    assert [v.offset for v in fw.volumes] == [0, 0x2000]
    names = [f.name for f in fw.files()]
    assert "Setup" in names                                     # inside the LZMA-packed volume


def test_setup_module_is_unpacked(image):
    fw = firmware.parse_image(image)
    setup = fw.file_named("Setup")
    assert setup is not None
    assert setup.section(firmware.SEC_PE32) == fake_bios.setup_module()


def test_variable_takes_the_last_entry_of_its_chain(image):
    fw = firmware.parse_image(image)
    setup = fw.variable("Setup")
    assert setup.data == bytes([1, 0, 0x34, 0x12, 0, 0, 0, 0])
    assert setup.guid == fake_bios.SETUP_GUID
    assert setup.runtime


def test_defaults_come_from_std_defaults(image):
    fw = firmware.parse_image(image)
    assert fw.default("Setup").data == bytes([0, 1, 0, 0, 0, 0, 0, 0])
    assert fw.default("Setup", fake_bios.SETUP_GUID) is not None
    assert fw.default("Setup", uuid.uuid4()) is None


def test_guid_store_index(image):
    store = fake_bios.nvram(bytes(8), bytes(8), bytes(8), amd=bytes(4))
    variables = firmware.parse_nvar_store(store)
    keys = {name: guid for guid, name in variables}
    assert keys["AmdSetup"] == uuid.UUID("3a997502-647a-4c82-998e-52ef9486a247")
    assert keys["StdDefaults"] == uuid.UUID("4599d26f-1a11-49b8-b91f-858745cff824")


def test_invalid_entries_are_skipped():
    entry = fake_bios.nvar("Old", 0, b"x", attrs=0x02)          # no VALID bit: a deleted variable
    variables = firmware.parse_nvar_store(fake_bios.store([entry], [fake_bios.SETUP_GUID], size=0x40))
    assert variables == {}


def test_a_chain_that_loops_ends():
    head = fake_bios.nvar("Setup", 0, b"a")
    head = head[:6] + (0).to_bytes(3, "little") + head[9:]      # next: itself
    variables = firmware.parse_nvar_store(fake_bios.store([head], [fake_bios.SETUP_GUID], size=0x40))
    assert variables[(fake_bios.SETUP_GUID, "Setup")].data == b"a"


def test_not_a_bios_image():
    with pytest.raises(firmware.FirmwareError):
        firmware.parse_image(b"\0" * 4096)
