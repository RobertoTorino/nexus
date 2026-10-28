# SPDX-License-Identifier: GPL-3.0-or-later
"""The temperatures (temps.py): the header's text, and Windows' answer read for real on Windows."""

from __future__ import annotations

import sys

import pytest

from portable_test import temps


@pytest.mark.parametrize("cpu, gpu, text", [(47, 45, "CPU 47° GPU 45°"), (None, 45, "GPU 45°"), (None, None, "")])
def test_the_header_text(cpu, gpu, text):
    assert temps.text(cpu, gpu) == text


def test_nothing_to_read_off_windows(monkeypatch):
    monkeypatch.setattr(temps.sys, "platform", "linux")
    assert temps.Temperatures().read() == (None, None)


@pytest.mark.skipif(sys.platform != "win32", reason="AMD's ADL and Windows' D3DKMT")
def test_windows_answers():
    sensors = temps.Temperatures()                  # a CI runner has no AMD driver and a software adapter: None
    try:
        for value in sensors.read():
            assert value is None or 10 <= value <= 110
    finally:
        sensors.close()
