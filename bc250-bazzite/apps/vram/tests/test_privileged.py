# SPDX-License-Identifier: GPL-3.0-or-later
import json
import struct

from vram_manager import cmos, privileged
from dumps import BOARD_1, FakePort, bank


def test_command_runs_the_helper_isolated():
    cmd = privileged.command(["--read"])
    assert cmd[0] == "pkexec" and cmd[2] == "-I"
    assert privileged.run_command(["no-such-command-bc250"])[0] == privileged.NOT_INSTALLED
    assert cmd[3].endswith("vram_manager/cmos.py") and cmd[4:] == ["--read"]


def test_parse():
    assert privileged.parse(126, "").error.startswith("Not authorized")
    ok = privileged.parse(0, 'noise\n{"ok": true, "block": {}}\n')
    assert ok.ok and ok.data == {"ok": True, "block": {}}
    bad = privileged.parse(1, '{"ok": false, "error": "no"}')
    assert not bad.ok and bad.error == "no"
    assert "exit code 2" in privileged.parse(2, "Traceback").error


def test_report(sys_root):
    data = cmos.do_read(cmos.Bank(FakePort(bank(BOARD_1))))
    text = privileged.report(json.loads(json.dumps(data)), sys_root, now=0)
    assert "signature  0x4C424124 (ABL)" in text
    assert "checksum   0x0410 stored, 0x0410 computed (match)" in text
    assert "UMA_SIZE   6144 MB" in text and "tCL        24" in text and "note " not in text
    data = bank(BOARD_1)
    struct.pack_into("<I", data, 0x90, 0x46544457)
    noted = json.loads(json.dumps(cmos.do_read(cmos.Bank(FakePort(data)))))
    assert "note       signature 0x46544457 (WATCH_DOG_TIMER_FIRED)" in privileged.report(noted, sys_root, now=0)
    assert "090  24 41 42 4C 10 04 D6 06 18 34 1B 13 4E 00 1A 00" in text
    assert "bios       American Megatrends Inc. P5.00 05/03/2022" in text
