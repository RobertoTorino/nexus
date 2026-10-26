# SPDX-License-Identifier: MIT
"""bc250-acpi-override.sh against a fake board: install, uninstall, the warnings that ask first, and --status."""

from __future__ import annotations

import platform

from conftest import APP, GRUB_LINE, give_override_cpu, needs_bash

pytestmark = needs_bash


def grub_lines(board) -> list[str]:
    return board.grub.read_text().splitlines()


def test_install_copies_the_tables_and_adds_the_grub_line(board):
    r = board.run("--install")
    assert r.returncode == 0, r.stdout + r.stderr
    assert board.cpio.read_bytes() == (APP / "tables" / "acpi_override.cpio").read_bytes()
    assert grub_lines(board) == ["GRUB_TIMEOUT=5", 'GRUB_CMDLINE_LINUX="rhgb quiet"', GRUB_LINE]
    assert board.grub_runs == 1
    assert "Reboot" in r.stdout


def test_install_twice_keeps_one_grub_line(board):
    assert board.run("--install").returncode == 0
    assert board.run("--install").returncode == 0
    assert grub_lines(board).count(GRUB_LINE) == 1


def test_install_replaces_another_early_initrd_line(board):
    board.grub.write_text('GRUB_TIMEOUT=5\nGRUB_EARLY_INITRD_LINUX_CUSTOM="other.cpio"\n')
    assert board.run("--install").returncode == 0
    assert grub_lines(board) == ["GRUB_TIMEOUT=5", GRUB_LINE]


def test_uninstall_reverses_install(board):
    assert board.run("--install").returncode == 0
    r = board.run("--uninstall")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not board.cpio.exists()
    assert grub_lines(board) == ["GRUB_TIMEOUT=5", 'GRUB_CMDLINE_LINUX="rhgb quiet"']
    assert board.grub_runs == 2


def test_needs_root(board):
    for action in ("--install", "--uninstall"):
        r = board.run(action, uid=1000)
        assert r.returncode == 1 and "Run as root" in r.stderr
    assert not board.cpio.exists() and board.grub_runs == 0


def test_no_bc250_gpu_asks_first_and_yes_continues(board):
    board.env["FAKE_LSPCI"] = ""
    r = board.run("--install")
    assert r.returncode == 3                                                 # no terminal: stop and ask
    assert "No BC-250 GPU" in r.stdout and "--yes" in r.stdout
    assert not board.cpio.exists() and GRUB_LINE not in grub_lines(board) and board.grub_runs == 0
    assert board.run("--install", "--yes").returncode == 0
    assert board.cpio.exists()


def test_modded_bios_asks_first(board):
    (board.root / "sys/class/dmi/id/bios_version").write_text("P3.00 MeiMeiDXE v3\n")
    r = board.run("--install")
    assert r.returncode == 3 and "looks modded" in r.stdout
    assert not board.cpio.exists()


def test_kernel_without_table_upgrade_is_refused(board):
    (board.root / "boot" / f"config-{platform.release()}").write_text("# CONFIG_ACPI_TABLE_UPGRADE is not set\n")
    r = board.run("--install", "--yes")
    assert r.returncode == 1 and "CONFIG_ACPI_TABLE_UPGRADE" in r.stderr
    assert not board.cpio.exists()


def test_status_stock_board(board):
    r = board.run("--status", uid=1000)
    assert r.returncode == 0
    lines = r.stdout.splitlines()
    assert lines[0] == "Override: not installed"
    assert lines[1].startswith("Frequency steps: none listed")
    assert lines[2].startswith("Idle states: POLL ")
    assert lines[3] == "Kernel log: run with sudo to also check this."


def test_status_with_the_override_loaded(board):
    assert board.run("--install").returncode == 0
    give_override_cpu(board)
    board.env["FAKE_KLOG"] = "ACPI: Table Upgrade: install [SSDT-CPU]"
    lines = board.run("--status").stdout.splitlines()
    assert lines[0].startswith("Override: installed")
    assert lines[1].startswith("Frequency steps: 8 (800-3200 MHz;")
    assert lines[2].startswith("Idle states: POLL,C1,C2 ")
    assert lines[3] == "Kernel log: override tables loaded this boot"


def test_status_incomplete(board):
    assert board.run("--install").returncode == 0
    board.grub.write_text("GRUB_TIMEOUT=5\n")
    line = board.run("--status", uid=1000).stdout.splitlines()[0]
    assert line.startswith("Override: incomplete (GRUB line missing)")


def test_bad_arguments(board):
    assert board.run().returncode == 2
    r = board.run("--install", "--uninstall")
    assert r.returncode == 1 and "one of" in r.stderr
    assert board.run("--bogus").returncode == 1
