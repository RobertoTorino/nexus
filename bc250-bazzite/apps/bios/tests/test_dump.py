# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

from bios_reader import dump


def test_read_command_only_reads(tmp_path):
    fr = dump.Flashrom(Path("/home/u/flashrom/usr/bin/flashrom"), Path("/home/u/flashrom/usr/lib64"))
    cmd = dump.read_command(fr, tmp_path / "a.bin", tmp_path / "b.bin", "1000:1000")
    assert cmd[:3] == ["pkexec", "env", "LD_LIBRARY_PATH=/home/u/flashrom/usr/lib64"]
    script = cmd[cmd.index("-c") + 1]
    assert "-r" in script and not any(flag in script for flag in (" -w", " -E", " -v", "--write", "--erase"))
    assert cmd[-5:] == [str(fr.binary), str(tmp_path / "a.bin"), str(tmp_path / "b.bin"), "1000:1000", dump.CHIP]


def test_read_command_without_libdir(tmp_path):
    cmd = dump.read_command(dump.Flashrom(Path("/usr/sbin/flashrom"), None), tmp_path / "a", tmp_path / "b", "1:1")
    assert cmd[:3] == ["pkexec", "env", "sh"]


def test_two_identical_reads(tmp_path):
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    data = bytes(range(256)) * (dump.CHIP_SIZE // 256)
    a.write_bytes(data)
    b.write_bytes(data)
    assert dump.check_reads(a, b) == ""
    assert a.exists() and not b.exists()


def test_reads_that_differ(tmp_path):
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(bytes(dump.CHIP_SIZE))
    b.write_bytes(bytes(dump.CHIP_SIZE - 1) + b"\1")
    assert "differ" in dump.check_reads(a, b)


def test_short_or_missing_read(tmp_path):
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(b"x")
    assert "missing" in dump.check_reads(a, b)
    b.write_bytes(b"x")
    assert "bytes instead of" in dump.check_reads(a, b)


def test_dump_names(tmp_path):
    first, second = dump.dump_paths(tmp_path, now=0)
    assert first.parent == tmp_path and first.name.startswith("bios-") and second.name.endswith(".check.bin")


def test_unpacked_flashrom_comes_first(tmp_path, monkeypatch):
    binary = tmp_path / "flashrom/usr/bin/flashrom"
    binary.parent.mkdir(parents=True)
    binary.write_text("")
    monkeypatch.setattr(dump.shutil, "which", lambda _: None)
    found = dump.candidates(tmp_path)
    assert found[0] == dump.Flashrom(binary, tmp_path / "flashrom/usr/lib64")


def test_flashrom_without_internal_programmer(tmp_path):
    script = tmp_path / "flashrom"
    script.write_text("#!/bin/sh\necho 'Valid choices are: dummy, ch341a_spi'\n")
    script.chmod(0o755)
    assert not dump.has_internal(dump.Flashrom(script, None))
    script.write_text("#!/bin/sh\necho 'Valid choices are: internal, dummy'\n")
    assert dump.has_internal(dump.Flashrom(script, None))
