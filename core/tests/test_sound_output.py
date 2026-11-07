# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import sys

import pytest

from bc250_core import sound_output


def test_the_default_output_is_read_by_its_kind_never_its_name(monkeypatch):
    """Windows' own answer on Windows (a runner may have no sound output, None, or no sound service, an OSError that
    says so); elsewhere an OSError that says why (owner, 07-11-2026: the kind, PC speakers or Other screen, never a
    device's name)."""
    if sys.platform == "win32":
        try:
            kind = sound_output.default_kind()
        except OSError as exc:
            assert "Windows' sound outputs" in str(exc)
        else:
            assert kind in (*sound_output.FORM_FACTORS.values(), sound_output.OTHER, None)
    monkeypatch.setattr(sound_output.sys, "platform", "linux")
    with pytest.raises(OSError, match="Windows'"):
        sound_output.default_kind()


def test_each_kind_has_the_suites_name():
    assert sound_output.label(sound_output.SPEAKERS) == "PC speakers"
    assert sound_output.label(sound_output.SCREEN) == "Other screen"
    assert sound_output.label(sound_output.HEADPHONES) == "headphones"
    assert sound_output.label(None) == "no output"
    assert sound_output.label("something new") == "another output"
    assert sound_output.FORM_FACTORS[9] == sound_output.SCREEN          # a TV's or a monitor's HDMI or DisplayPort
