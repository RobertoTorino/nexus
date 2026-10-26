# SPDX-License-Identifier: GPL-3.0-or-later
import json
import struct

import pytest

from vram_manager import cmos
from dumps import BOARD_1, BOARD_2, FakePort, bank

BLOCK = slice(0x90, 0xAC)


@pytest.mark.parametrize("text", [BOARD_1, BOARD_2])
def test_owner_boards_decode(text):
    block = cmos.Bank(FakePort(bank(text))).read_block()
    assert block.signature == cmos.SIG_ABL and block.signature_name == "ABL"
    assert block.checksum == block.computed_checksum == 0x0410
    assert block.uma_mb == 6144
    assert block.fields() == {"ClockSpeed": 1750, "tCL": 24, "tRAS": 52, "tRCDRD": 27, "tRCDWR": 19, "tRCAb": 78,
                              "tRCPb": 0, "tRPAb": 26, "tRPPb": 0, "tRRDS": 8, "tRRDL": 8, "tRTP": 2, "tFAW": 32,
                              "tREF": 9975, "RFCPb": 210, "tRFC": 280}
    assert block.problems() == []


def test_boards_share_the_block_only():
    one, two = bank(BOARD_1), bank(BOARD_2)
    assert one[BLOCK] == two[BLOCK]
    assert one != two                           # the noise around it differs


def test_set_uma_writes_like_bc250_memcfg():
    data = bank(BOARD_1)
    original = bytes(data)
    port = FakePort(data)
    result = cmos.do_set_uma(cmos.Bank(port), 512)
    after = cmos.Block(bytes(data[BLOCK]))
    assert after.signature == cmos.SIG_LINUX_TOOL
    assert after.uma_mb == 512
    assert after.checksum == after.computed_checksum
    assert after.fields() == cmos.Block(original[BLOCK]).fields()     # the timings are untouched
    assert data[:0x90] == original[:0x90] and data[0xAC:] == original[0xAC:]
    # the whole block, from 0x90 upwards, like the original tool
    offsets = [v for p, v in port.writes if p == 0x72][-2 * 28:-28]
    assert offsets == list(range(0x90, 0xAC))
    assert result["before"]["uma_mb"] == 6144 and result["after"]["uma_mb"] == 512


def test_never_writes_outside_the_block():
    bank2 = cmos.Bank(FakePort(bank(BOARD_1)))
    with pytest.raises(cmos.CmosError, match="outside the memory block"):
        bank2.write(0x8F, 0)
    with pytest.raises(cmos.CmosError):
        bank2.write(0xAC, 0)


@pytest.mark.parametrize("mb, message", [(500, "multiple of 16"), (256, "outside"), (10256, "outside")])
def test_rejects_odd_splits(mb, message):
    port = FakePort(bank(BOARD_1))
    with pytest.raises(cmos.CmosError, match=message):
        cmos.do_set_uma(cmos.Bank(port), mb)
    assert all(p != 0x73 for p, _ in port.writes)


def corrupt(offset, value):
    data = bank(BOARD_1)
    data[offset] = value
    return data


@pytest.mark.parametrize("data, message", [
    (corrupt(0x90, 0x00), "signature"),
    (corrupt(0x94, 0x11), "checksum"),
    (corrupt(0x98, 0x40), "tCL = 64"),               # out of range (checksum also wrong, both are reported)
])
def test_refuses_an_untrusted_block(data, message):
    original = bytes(data)
    port = FakePort(data)
    with pytest.raises(cmos.CmosError, match=message):
        cmos.do_set_uma(cmos.Bank(port), 4096)
    assert bytes(data) == original
    assert all(p != 0x73 for p, _ in port.writes)


def test_linux_tool_signature_is_trusted():
    data = bank(BOARD_1)
    struct.pack_into("<I", data, 0x90, cmos.SIG_LINUX_TOOL)
    assert cmos.Block(bytes(data[BLOCK])).problems() == []


def test_write_that_does_not_stick():
    port = FakePort(bank(BOARD_1), stuck={0xAB})
    with pytest.raises(cmos.CmosError, match="did not stick"):
        cmos.do_set_uma(cmos.Bank(port), 4096)


def test_board_checks(sys_root):
    assert cmos.board_problem(sys_root) == ""
    (sys_root / "kernel/security/lockdown").write_text("none [integrity] confidentiality\n")
    assert "lockdown (integrity)" in cmos.board_problem(sys_root)
    (sys_root / "class/dmi/id/board_name").write_text("Other Board\n")
    assert "not a BC-250" in cmos.board_problem(sys_root)


def test_main_read_and_set(sys_root, capsys):
    data = bank(BOARD_2)
    port = FakePort(data)
    assert cmos.main(["--read"], sys_root, lambda: port) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["block"]["uma_mb"] == 6144 and bytes.fromhex(out["bank"]) == bytes(bank(BOARD_2))
    assert port.closed
    assert cmos.main(["--set-uma", "8192"], sys_root, lambda: FakePort(data)) == 0
    assert json.loads(capsys.readouterr().out)["after"]["uma_mb"] == 8192


def test_main_refuses_other_boards(sys_root, capsys):
    (sys_root / "class/dmi/id/board_name").write_text("Other Board\n")
    opened = []
    assert cmos.main(["--read"], sys_root, lambda: opened.append(1)) == 1
    assert not opened                                           # the port is never opened
    assert "not a BC-250" in json.loads(capsys.readouterr().out)["error"]
