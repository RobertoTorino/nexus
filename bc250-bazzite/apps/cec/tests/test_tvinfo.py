# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path

from hdmi_cec import tvinfo

TV_ANSWERS = json.loads((Path(__file__).parent / "tv_answers.json").read_text())  # the owner's TV, 11-10-2026, CEC 1.4


def reply(message: str, *fields: str) -> str:
    """cec-ctl's output for a question the TV answered, in the layout of the recorded answers. The CEC 2.0 ones are
    made up from cec-ctl's names for the fields (cec-ctl --help-all): no CEC 2.0 TV was recorded yet."""
    lines = "".join(f"\t{f}\n" for f in fields)
    return (f"\nTransmit from Playback Device 1 to TV (4 to 0):\nQUESTION (0x00)\n    Received from TV (0):\n"
            f"    {message}:\n{lines}\tSequence: 1 Tx Timestamp: 1.0s Rx Timestamp: 1.1s\n")


def owner_tv(**changes: str) -> dict[str, tvinfo.Reply]:
    """The owner's TV's answers, with some questions answered otherwise."""
    keys = {"version": "--get-cec-version", "power": "--give-device-power-status", "name": "--give-osd-name",
            "address": "--give-physical-addr", "vendor": "--give-device-vendor-id",
            "language": "--get-menu-language", "features": "--give-features", "audio": "--give-audio-status"}
    replies = {key: tvinfo.parse_reply(changes.get(key) or TV_ANSWERS[f"--to 0 {option}"])
               for key, option in keys.items()}
    replies["latency"] = tvinfo.parse_reply(changes.get("latency") or
                                            TV_ANSWERS["--to 15 --request-current-latency phys-addr=0.0.0.0"])
    replies["receiver"] = tvinfo.parse_reply(TV_ANSWERS["--poll --to 5"])
    return replies


def test_a_cec_1_4_tv():
    rows = dict(tvinfo.rows(owner_tv()))
    assert rows["CEC 2.0 feature list"] == "not supported"
    assert rows["Volume and mute status"] == "not supported (it does not report its volume)"
    assert rows["Lip-sync delay"] == "no answer (a CEC 2.0 feature)"


def test_a_cec_2_0_tv_shows_what_it_reports():
    rows = dict(tvinfo.rows(owner_tv(
        version=reply("CEC_VERSION (0x9e)", "cec-version: version-2-0 (0x06)"),
        features=reply("REPORT_FEATURES (0xa6)", "cec-version: version-2-0 (0x06)", "all-device-types: tv (0x80)",
                       "rc-profile: tv-profile-1 (0x02)", "dev-features: sink-has-arc-tx (0x04)",
                       "dev-features: has-set-audio-volume-level (0x01)"),
        audio=reply("REPORT_AUDIO_STATUS (0x7a)", "aud-mute-status: off (0x00)", "aud-vol-status: 23 (0x17)"),
        latency=reply("REPORT_CURRENT_LATENCY (0xa8)", "phys-addr: 0.0.0.0", "video-latency: 11 (0x0b)",
                      "low-latency-mode: on (0x01)", "audio-out-compensated: partial-delay (0x03)",
                      "audio-out-delay: 21 (0x15)"),
    )))
    assert rows["CEC version"] == "2.0"
    assert rows["CEC 2.0 feature list"] == ("supported: CEC 2.0; TV; remote profile 1; sends its sound to a "
                                            "receiver (ARC); takes an exact volume")
    assert rows["Volume and mute status"] == "volume 23, not muted"
    assert rows["Lip-sync delay"] == "picture 20 ms, low-latency mode on, sound 40 ms"


def test_unknown_volume_and_flags_on_one_line():
    assert tvinfo.audio(tvinfo.parse_reply(reply("REPORT_AUDIO_STATUS (0x7a)", "aud-mute-status: on (0x01)",
                                                 "aud-vol-status: 127 (0x7f)"))) == "volume unknown, muted"
    features = tvinfo.parse_reply(reply("REPORT_FEATURES (0xa6)", "all-device-types: tv, audiosystem (0x88)",
                                        "dev-features: sink-has-arc-tx, has-set-osd-string (0x24)"))
    assert tvinfo.features(features) == "TV, audio system; sends its sound to a receiver (ARC); shows messages " \
                                        "from devices"


def test_a_receiver_with_its_name_and_volume():
    replies = owner_tv()
    replies["receiver"] = tvinfo.Reply("no reply")                     # the poll went through
    assert dict(tvinfo.rows(replies))["AV receiver or soundbar"] == "connected"
    replies["receiver name"] = tvinfo.parse_reply(reply("SET_OSD_NAME (0x47)", "name: Soundbar"))
    replies["receiver audio"] = tvinfo.parse_reply(reply("REPORT_AUDIO_STATUS (0x7a)", "aud-mute-status: off (0x00)",
                                                         "aud-vol-status: 30 (0x1e)"))
    assert dict(tvinfo.rows(replies))["AV receiver or soundbar"] == 'connected: "Soundbar", volume 30, not muted'
