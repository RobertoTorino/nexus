# SPDX-License-Identifier: GPL-3.0-or-later
"""The back buttons (back_buttons.py): the ASUS channel's reports as the owner's Ally X sent them (28-10-2026), and the
channel found for real on Windows."""

from __future__ import annotations

import sys

import pytest

from portable_test import back_buttons


@pytest.mark.parametrize("report, held", [
    (bytes.fromhex("5aa500000000"), True),          # M1 or M2 down
    (bytes.fromhex("5a0000000000"), False),         # let go
    (bytes.fromhex("5aa000000000"), None),          # M1 held with A: Armoury Crate's screenshot
    (bytes.fromhex("5aec00000000"), None),          # seen now and then beside A5
    (bytes.fromhex("5d00"), None), (b"", None)])
def test_the_reports(report, held):
    assert back_buttons.parse(report) is held


def test_nothing_to_find_off_windows(monkeypatch):
    monkeypatch.setattr(back_buttons.sys, "platform", "linux")
    assert back_buttons.find() is None and back_buttons.Reader().start() is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' setupapi and hid.dll")
def test_windows_answers():
    found = back_buttons.find()                     # a CI runner has no ASUS controller: None
    assert found is None or (found[0] and found[1] > 1)
