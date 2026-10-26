# SPDX-License-Identifier: GPL-3.0-or-later
"""The advice tests 15, 16 and 17 give on journal lines: LOG_ADVICE and explain_log_lines, run from the script."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "test-bazzite.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def explain(lines: list[str], scope: str = "-b") -> list[str]:
    """The HINT texts explain_log_lines writes for these journal lines."""
    text = SCRIPT.read_text(encoding="utf-8")
    table = re.search(r"^LOG_ADVICE=\(.*?^\)$", text, re.S | re.M).group(0)
    func = re.search(r"^explain_log_lines\(\) \{.*?^\}$", text, re.S | re.M).group(0)
    prog = f'log_result() {{ echo "$1"; }}\n{table}\n{func}\nexplain_log_lines "$1" "$2"\n'
    out = subprocess.run(["bash", "-c", prog, "bash", "\n".join(lines), scope],
                         capture_output=True, text=True, check=True).stdout
    return [line.removeprefix("HINT: ") for line in out.splitlines()]


def journal(ident: str, message: str) -> str:
    return f"Oct 11 12:00:00 bazzite {ident}[123]: {message}"


def test_table_is_pairs_of_a_pattern_and_a_sentence():
    text = SCRIPT.read_text(encoding="utf-8")
    table = re.search(r"^LOG_ADVICE=\(\n(.*?)^\)$", text, re.S | re.M).group(1)
    entries = [line.strip() for line in table.splitlines() if line.strip() and not line.strip().startswith("#")]
    assert len(entries) % 2 == 0
    for advice in entries[1::2]:
        # The GUI joins a HINT line that does not end a sentence with the next one.
        assert advice.endswith('."'), advice


def test_nothing_for_no_lines():
    assert explain([]) == []


def test_real_fault_is_explained_and_counted():
    hints = explain([journal("kernel", "amdgpu 0000:01:00.0: amdgpu: ring gfx_0.0.0 timeout, signaled seq=1"),
                     journal("kernel", "amdgpu 0000:01:00.0: amdgpu: GPU reset begin!")])
    assert len(hints) == 1
    assert hints[0].startswith("[2 lines] GPU hang or reset")


def test_a_line_counts_for_the_first_pattern_only():
    # A crash of a KDE program is a crash, not KDE noise.
    hints = explain([journal("systemd", "app-org.kde.dolphin@0.service: Failed with result 'core-dump'.")])
    assert len(hints) == 1 and hints[0].startswith("[1 line] A program crashed")


def test_failed_unit_gets_its_own_commands():
    hints = explain([journal("systemd", "Failed to start foo.service - Foo."),
                     journal("systemd", "foo.service: Failed with result 'exit-code'.")], "--since '7 days ago'")
    assert hints == ["[2 lines] foo.service failed. Read why with: journalctl --since '7 days ago' -u foo.service; "
                     "if you no longer use it: sudo systemctl disable foo.service."]


def test_unknown_lines_are_grouped_by_program():
    hints = explain([journal("someapp", "error: one"), journal("someapp", "error: two"), journal("other", "fail")])
    assert hints[0].startswith("[2 lines] from someapp, no known explanation. Read them with: journalctl -b -p "
                               "warning -t someapp;")
    assert hints[1].startswith("[1 line] from other,")
