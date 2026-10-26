# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path

from hdmi_cec import display
from hdmi_cec.runner import Result

KSCREEN = (Path(__file__).parent / "kscreen.json").read_text()      # the owner's board, 11-10-2026


def board(**changes):
    data = json.loads(KSCREEN)
    data["outputs"][0].update(changes)
    return display.parse(json.dumps(data))["DP-1"]


def test_parse_the_board():
    out = board()
    assert (out.name, out.enabled, out.max_bpc, out.hdr) == ("DP-1", True, 0, False)
    assert out.mode == display.Mode("21", 1920, 1080, 120.0)
    assert len(out.modes) == 56
    assert display.parse("not json") == {} and display.parse("[]") == {}


def test_other_rate_keeps_the_size():
    assert display.other_rate(board()) == display.Mode("23", 1920, 1080, 60.0)              # 120 Hz -> 60 Hz
    assert display.other_rate(board(currentModeId="22")).id == "23"                         # 119.88 Hz -> 60 Hz
    assert display.other_rate(board(currentModeId="23")).rate == 50.0                       # 60 Hz -> 50 Hz
    assert display.other_rate(board(currentModeId="1")) == display.Mode("14", 3840, 2160, 50.0)  # 4K60 -> 4K50
    assert display.other_rate(board(currentModeId="99")) is None


def test_commands():
    assert display.set_max_bpc("DP-1", 8) == ["kscreen-doctor", "output.DP-1.maxbpc.8"]
    assert display.set_max_bpc("DP-1", 0) == ["kscreen-doctor", "output.DP-1.maxbpc.automatic"]
    assert display.set_mode("DP-1", "23") == ["kscreen-doctor", "output.DP-1.mode.23"]


def test_read_without_kscreen():
    assert display.read(lambda argv: Result(127, "not found")) == {}


def test_handshake_depends_on_the_mode():
    assert round(display.clock_mhz(display.Mode("21", 1920, 1080, 120.0))) == 296           # CTA: 297 MHz
    assert display.handshake(display.Mode("21", 1920, 1080, 120.0)) == "above 8 bits"      # 8 bits helps
    assert display.handshake(display.Mode("23", 1920, 1080, 60.0)) == "never"
    assert display.handshake(display.Mode("1", 3840, 2160, 60.0)) == "always"              # 8 bits does not
    assert display.handshake(display.Mode("x", 2560, 1440, 120.0)) == "always"
    assert display.describe(display.Mode("22", 1920, 1080, 119.88)) == "1920 × 1080 at 119.88 Hz"
