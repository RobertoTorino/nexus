# SPDX-License-Identifier: GPL-3.0-or-later
from hdmi_cec import cec
from conftest import ACK, EDID, INFO, NACK, POWER_ON, TOPOLOGY, TOPOLOGY_TV, UNCONFIGURED


def test_parse_info_of_the_board():
    a = cec.parse_info("/dev/cec0", INFO)
    assert (a.driver, a.name, a.physical_address) == ("amdgpu", "DP-1", "1.0.0.0")
    assert a.logical_addresses == ("4 (Playback Device 1)",)
    assert a.osd_name == "Playback" and a.connector == "card 1, connector 87"
    assert "Needs HPD" in a.capabilities and "Transmit" in a.capabilities
    assert a.has_display and a.configured


def test_unconfigured_and_without_display():
    a = cec.parse_info("/dev/cec0", UNCONFIGURED.replace("1.0.0.0", "f.f.f.f"))
    assert not a.configured and not a.has_display


def test_devices_in_number_order(tmp_path):
    for name in ("cec10", "cec2", "cec0", "cecx"):
        (tmp_path / name).touch()
    assert cec.devices(tmp_path) == [str(tmp_path / n) for n in ("cec0", "cec2", "cec10")]
    assert cec.devices(tmp_path / "missing") == []


def test_topology():
    assert cec.parse_topology(TOPOLOGY) == [("1.0.0.0", "Playback Device 1")]
    assert cec.parse_topology(TOPOLOGY_TV) == [("0.0.0.0", "TV"), ("1.0.0.0", "Playback Device 1")]
    assert cec.parse_topology(INFO) == []


def test_answers():
    assert not cec.acked(NACK) and cec.power_status(NACK) == ""
    assert cec.acked(ACK) and cec.acked(POWER_ON)
    assert cec.power_status(POWER_ON) == "on"
    assert cec.power_status("\tpwr-state: in transition standby to on (0x02)") == "in transition standby to on"
    assert not cec.acked("") and not cec.acked("Error: no such device")
    # The owner's TV (CEC 1.4) on 11-10-2026: it took the message and answered that it does not support it.
    abort = ("GIVE_FEATURES (0xa5)\n    Received from TV (0):\n    FEATURE_ABORT (0x00):\n"
             "\tSequence: 140 Tx Timestamp: 1.0s Rx Timestamp: 1.1s\n\tTx, OK, Rx, OK, Feature Abort\n")
    assert cec.acked(abort) and cec.acked("\tSequence: 141 Tx Timestamp: 2.0s\n\tTx, OK, Rx, Timeout\n")


def test_messages():
    assert cec.image_view_on("/dev/cec0") == ["-d", "/dev/cec0", "-s", "--to", "0", "--image-view-on"]
    assert cec.active_source("/dev/cec0", "1.0.0.0")[-3:] == ["15", "--active-source", "phys-addr=1.0.0.0"]
    assert cec.standby("/dev/cec0")[-3:] == ["--to", "0", "--standby"]
    assert cec.key_press("/dev/cec0", 5, "mute")[-3:] == ["5", "--user-control-pressed", "ui-cmd=mute"]
    assert cec.configure("/dev/cec0") == ["-d", "/dev/cec0", "--playback", "--osd-name", "BC-250"]


def test_ui_command_names():
    assert cec.ui_command_name(0x41) == "volume-up" and cec.ui_command_name(0x00) == "select"
    assert cec.ui_command_name(0xEE) == "0xee"


def test_display_name(sys_root):
    assert cec.edid_name(bytes(EDID)) == "Mi TV"
    assert cec.edid_name(b"short") == ""
    assert cec.display_name("DP-1", sys_root) == "Mi TV"
    assert cec.display_name("DP-2", sys_root) == "" and cec.display_name("", sys_root) == ""


def test_pick_prefers_the_adapter_with_a_display():
    dark = cec.parse_info("/dev/cec0", INFO.replace("1.0.0.0", "f.f.f.f"))
    lit = cec.parse_info("/dev/cec1", INFO)
    assert cec.pick([dark, lit]) is lit
    assert cec.pick([dark]) is dark and cec.pick([]) is None
