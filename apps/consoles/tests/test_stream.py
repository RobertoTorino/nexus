# SPDX-License-Identifier: AGPL-3.0-or-later
"""The stream connection: the protobuf messages and the launch spec against vectors from the reference's own code
(launchspec.c, rpcrypt.c, and the messages encoded with nanopb as streamconnection.c builds them, at commit
c8bea2642d0e: tests/stream_vectors.json; the controller's packets from feedback.c: tests/feedback_vectors.json),
then the whole connection against a fake console on localhost (fake_stream.py). The connection tests need the native
core and are skipped without it."""

from __future__ import annotations

import json
import re
import threading
import sys
from pathlib import Path

import pytest

from consoles_link import launchspec, stream, tkproto
from consoles_link.rpcrypt import RPCrypt
from consoles_link.target import Target

VECTORS = json.loads((Path(__file__).parent / "stream_vectors.json").read_text(encoding="utf-8"))
FEEDBACK = json.loads((Path(__file__).parent / "feedback_vectors.json").read_text(encoding="utf-8"))
MESSAGES = VECTORS["messages"]
h = bytes.fromhex
NONCE = bytes(range(100, 116))
RP_KEY = bytes(range(0x40, 0x50))
SESSION_ID = "Ab1" * 10


# --- Messages and launch spec -----------------------------------------------------------------------------------

@pytest.mark.parametrize("name, built", [
    ("heartbeat", tkproto.heartbeat()),
    ("streaminfo_ack", tkproto.streaminfo_ack()),
    ("idr_request", tkproto.idr_request()),
    ("disconnect", tkproto.disconnect()),
    ("corrupt_frame", tkproto.corrupt_frame(300, 65535)),
    ("controller_dualshock4", tkproto.controller_connection(False)),
    ("controller_dualsense", tkproto.controller_connection(True)),
    ("microphone", tkproto.microphone(tkproto.MICROPHONE.save())),
])
def test_messages_match_reference(name, built):
    assert built == h(MESSAGES[name])


def test_console_messages_decode():
    bang = tkproto.bang(tkproto.parse(h(MESSAGES["bang"])))
    assert (bang.server_version, bang.token, bang.session_key) == (12, 0xdeadbeef, "consolesessionkey")
    assert bang.version_accepted and bang.encrypted_key_accepted
    assert (bang.ecdh_public_key, bang.ecdh_signature) == (h(MESSAGES["bang_pub"]), h(MESSAGES["bang_sig"]))
    refused = tkproto.bang(tkproto.parse(h(MESSAGES["bang_refused"])))
    assert not refused.version_accepted and refused.ecdh_public_key == b""

    info = tkproto.streaminfo(tkproto.parse(h(MESSAGES["streaminfo"])))
    assert [(r.width, r.height, r.video_header) for r in info.resolutions] == [
        (1920, 1080, h(MESSAGES["streaminfo_header_0"])), (1280, 720, h(MESSAGES["streaminfo_header_1"]))]
    assert info.audio_header == h(MESSAGES["streaminfo_audio_header"])
    assert (info.start_timeout, info.afk_timeout, info.afk_timeout_disconnect, info.congestion_control_interval) \
        == (100, 300000, None, 200)
    assert tkproto.AudioHeader.load(info.audio_header) == tkproto.AudioHeader(2, 16, 48000, 480)

    reason = tkproto.disconnect_reason(tkproto.parse(h(MESSAGES["disconnect_server"])))
    assert reason == "Server shutting down"
    assert tkproto.corrupt_range(tkproto.parse(h(MESSAGES["corrupt_frame"]))) == (300, 65535)
    assert tkproto.bang(tkproto.parse(h(MESSAGES["heartbeat"]))) is None


def test_bad_protobuf_is_refused():
    for data in (b"\x08", b"\x08\x03\x12\x05ab", b"\x0b", b"\x00\x01", b"\x12\x00"):   # cut, cut, group, 0, no type
        with pytest.raises(tkproto.ProtoError):
            tkproto.parse(data)
    with pytest.raises(tkproto.ProtoError):
        tkproto.AudioHeader.load(bytes(13))
    # Unknown fields, fixed-size ones included, are skipped.
    message = tkproto.parse(tkproto.uint(1, 3) + b"\x29" + bytes(8) + b"\x35" + bytes(4) + tkproto.uint(99, 7))
    assert message.type == tkproto.HEARTBEAT


@pytest.mark.parametrize("name", ["ps5_1080p_hevc", "ps5_720p_avc_hdr", "ps4_720p"])
def test_launch_spec_and_big_match_reference(name):
    v = VECTORS["launchspec"][name]
    target = Target(v["target"])
    codec = {0: "h264", 1: "h265", 2: "h265_hdr"}[v["codec"]]
    spec = launchspec.format_spec(target, v["width"], v["height"], v["max_fps"], codec, v["kbps"], 1454, 1,
                                  h(v["handshake_key"]))
    assert spec == v["json"]
    encoded = launchspec.encode_for_big(RPCrypt.for_session(target, h(v["nonce"]), h(v["morning"])), spec)
    assert encoded == v["b64"]
    big = VECTORS["launchspec"][f"big_{name}"]
    built = tkproto.big(12 if target.ps5 else 9, "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAsessionid", encoded,
                        h(VECTORS["launchspec"][f"big_{name}_pub"]), h(VECTORS["launchspec"][f"big_{name}_sig"]))
    assert built == h(big)


def test_missing_native_core_says_what_to_do(monkeypatch):
    monkeypatch.setitem(sys.modules, "bc250_console_link_core", None)
    with pytest.raises(stream.StreamError, match="native core"):
        stream.StreamConnection("127.0.0.1", Target.PS5_1, SESSION_ID, None)


# --- The connection against a fake console ------------------------------------------------------------------------

def test_a_core_without_decoder_is_noted():
    class Core:                                         # a native core built without FFmpeg
        DECODER = False
    connection = stream.StreamConnection("127.0.0.1", Target.PS4_10, SESSION_ID, None, core=Core())
    connection._open_decoder()
    connection._on_frame({"fec": False, "frames_lost": 0}, b"frame")
    assert connection.decoder is None and connection.stats.decoded == 0 and connection.stats.frames == 1
    assert "This native core has no video decoder" in connection.log[0]


@pytest.fixture
def console_factory():
    pytest.importorskip("bc250_console_link_core", reason="the native core is not built: see native/pyproject.toml")
    from fake_stream import StreamConsole
    made = []

    def make(target=Target.PS5_1, **behaviour):
        console = StreamConsole(target, NONCE, RP_KEY, **behaviour)
        made.append(console)
        return console
    yield make
    for console in made:
        console.close()


def _frame_bytes(console, *frames: int) -> int:
    from fake_stream import frame_data
    return sum(len(frame_data(frame, console.codec)) for frame in frames)


def _connection(console, timeout=2.0, **kwargs) -> stream.StreamConnection:
    crypt = RPCrypt.for_session(console.target, NONCE, RP_KEY)
    return stream.StreamConnection("127.0.0.1", console.target, SESSION_ID, crypt, port=console.port, timeout=timeout,
                                   **kwargs)


@pytest.mark.parametrize("target", [Target.PS5_1, Target.PS4_10])
def test_stream_connects_runs_and_closes(console_factory, target):
    console = console_factory(target)
    profile = stream.Profile(1280, 720, 30, 10000, "h265")
    with _connection(console, profile=profile, dualsense=target.ps5) as connection:
        info = connection.connect()
        assert [(r.width, r.height) for r in info.resolutions] == [(1920, 1080)]
        assert connection.audio == tkproto.AudioHeader(2, 16, 48000, 480)
        connection.run(1.2)
    version = 12 if target.ps5 else 9
    # What reached the console: BIG with our session ID and a launch spec it could decrypt, signed correctly.
    assert console.big["version"] == version and console.big["session_key"] == SESSION_ID
    assert console.big["encrypted_key"] == bytes(4) and console.client_signature_ok
    resolution = console.spec["streamResolutions"][0]
    assert (resolution["resolution"], resolution["maxFps"]) == ({"width": 1280, "height": 720}, 30)
    assert console.spec["network"] == {"bwKbpsSent": 10000, "bwLoss": 0.001, "mtu": 1454, "rtt": 1, "ports": [53, 2053]}
    assert console.spec.get("videoCodec") == ("hevc" if target.ps5 else None)
    # Then the acknowledgement, the controller, the microphone, heartbeats and the goodbye; every packet signed.
    assert console.received[:4] == [tkproto.BIG, tkproto.STREAMINFOACK, tkproto.CONTROLLERCONNECTION,
                                    tkproto.STREAMINFO]
    assert console.heartbeats >= 2 and console.wait_until(lambda: console.disconnect_reason == "Client Disconnecting")
    assert console.errors == []
    # Video came through as whole frames, audio as packets; the core sent congestion reports.
    assert connection.stats.frames == 3 and connection.stats.fec_frames == 0
    assert connection.stats.frame_bytes == _frame_bytes(console, 1, 2, 3)
    assert connection.stats.corrupt_sent == [] and "Video at 1920×1080 (resolution 0)." in connection.log
    assert any(line.startswith("Video: 3 frames, 0 rebuilt with FEC") for line in connection.log)
    # The frames decode: the clip's header from STREAMINFO, then its frames.
    if connection.core.DECODER:
        assert console.codec == ("hevc" if target.ps5 else "h264")
        assert (connection.stats.decoded, connection.stats.decode_errors) == (3, 0)
        assert any(line.startswith(f"Video decoder: FFmpeg") and console.codec.upper() in line
                   for line in connection.log)
    else:
        assert connection.decoder is None and connection.stats.decoded == 0
    # Every 200 ms; frames 1 and 2 (5 units each) are counted once the next frame starts.
    reports = console.congestion_reports
    assert len(reports) >= 2 and sum(r for r, _ in reports) >= 10 and all(lost == 0 for _, lost in reports)
    assert connection.stats.audio_packets == 3
    assert (connection.stats.audio_frames, connection.stats.audio_lost) == (3, 0)      # after the prefill of 3
    assert connection.stats.haptics_packets == (1 if target.ps5 else 0)
    assert "The console's key signature checks out." in connection.log
    # The controller, idle, every 200 ms from STREAMINFO on: the state the reference formats, no button events.
    idle = h(FEEDBACK["state"][0]["v12" if target.ps5 else "v9"])
    states = console.feedback_states
    assert len(states) >= 4 and [seq for seq, _ in states] == list(range(len(states)))
    assert all(payload == idle for _, payload in states) and console.feedback_history == []
    # The summary is written just before the core stops, so one more state may follow it.
    sent = [int(m[1]) for line in connection.log if (m := re.search(r"Controller: (\d+) states and 0 button", line))]
    assert len(sent) == 1 and len(states) - 1 <= sent[0] <= len(states)


def test_controller_buttons_reach_the_console(console_factory):
    console = console_factory(Target.PS4_10)
    with _connection(console) as connection:
        connection.connect()
        connection.set_controller(buttons=1, left=(1000, -1000))             # cross, and the left stick
        connection.run(0.05)
        connection.set_controller()                                          # all released
        connection.run(0.35)
    # The press and the release in packets of their own, each repeated after 20, 50, 100 and 200 ms until the next
    # comes: the press (held 50 ms) once or twice, the release four times.
    press, release = (1, "8088ff"), (2, "8088008088ff")
    assert console.wait_until(lambda: [p.hex() for _, _, p in console.feedback_history].count(release[1]) == 5)
    assert [seq for seq, _, _ in console.feedback_history] == list(range(len(console.feedback_history)))
    packets = [(count, payload.hex()) for _, count, payload in console.feedback_history]
    assert packets[0] == press and packets.count(press) <= 3 and packets[packets.count(press):] == [release] * 5
    # The stick at once, then back to the center at once (well before the next 200 ms).
    payloads = [payload for _, payload in console.feedback_states]
    moved = [i for i, payload in enumerate(payloads) if payload[0x11:0x15] == h("03e8fc18")]
    assert len(moved) == 1 and payloads[moved[0] + 1] == h(FEEDBACK["state"][0]["v9"])
    assert console.errors == []


def test_shoulders_right_stick_and_touchpad_reach_the_console(console_factory):
    console = console_factory(Target.PS4_10)
    with _connection(console) as connection:
        connection.connect()
        connection.set_controller(buttons=1 << 8, right=(-32768, 32767), touches=[(0, 960, 471)])
        connection.run(0.05)
        connection.set_controller(buttons=(1 << 9) | (1 << 14), right=(-32768, 32767), touches=[(0, 1000, 500)])
        connection.run(0.05)
    assert console.wait_until(lambda: len(console.feedback_history) >= 5)
    events = b"".join(payload for _, _, payload in console.feedback_history)
    # L1 down, the finger down, then L1 up, the finger moved, R1 and the touchpad click down (feedback.c's codes).
    for event in ("8084ff", "d0003c01d7", "808400", "d0003e81f4", "8085ff", "80b1"):
        assert h(event) in events, event
    # The right stick in the state: bytes 0x15 to 0x18, big-endian.
    assert any(payload[0x15:0x19] == h("80007fff") for _, payload in console.feedback_states)


@pytest.mark.parametrize("text, expected", [
    ("announce", ("announce", 1, 1)), ("marked:2", ("marked", 2, 1)), ("packed:1:3", ("packed", 1, 3)),
])
def test_player_experiment_options(text, expected):
    players = stream.PlayerExperiment.parse(text)
    assert (players.mode, players.controller_id, players.mark) == expected and players.on
    assert not stream.PlayerExperiment().on
    for bad in ("two", "marked:16", "marked:1:2:3", "marked:x"):
        with pytest.raises(ValueError):
            stream.PlayerExperiment.parse(bad)


def test_player_experiment_marked_sends_the_second_controller_apart(console_factory, capsys):
    console = console_factory(Target.PS4_10)
    with _connection(console, players=stream.PlayerExperiment("marked", 1, 1)) as connection:
        connection.connect()
        connection.set_controller(left=(1000, 0))
        connection.set_second_controller(buttons=1, left=(-1000, 0))        # cross on the second controller
        connection.run(0.1)
    # Announced twice: the first controller as the reference does, the second with its controller_id.
    assert console.wait_until(lambda: len(console.controller_connections) == 2)
    first, second = console.controller_connections
    assert 1 not in first and second[1] == [1] and second[2] == [1]
    assert console.wait_until(lambda: any(p[:2] == h("8188") for _, _, p in console.feedback_history))
    marks = {payload[0] for _, payload in console.feedback_states}
    assert marks == {0xa0, 0xa1}                                            # each controller's states, marked
    assert not any(p[:2] == h("8088") for _, _, p in console.feedback_history)   # the first pressed nothing
    assert "Experiment marked: a second controller announced" in capsys.readouterr().err
    assert console.errors == []


def test_player_experiment_packed_sends_two_states_in_one_packet(console_factory):
    console = console_factory(Target.PS4_10)
    with _connection(console, players=stream.PlayerExperiment("packed")) as connection:
        connection.connect()
        connection.set_second_controller(right=(0, 1234))
        connection.run(0.1)
    assert console.wait_until(lambda: any(len(p) == 2 * 0x19 for _, p in console.feedback_states))
    pair = next(p for _, p in console.feedback_states if len(p) == 2 * 0x19)
    assert pair[0] == pair[0x19] == 0xa0 and pair[0x19 + 0x17:0x19 + 0x19] == h("04d2")
    assert console.errors == []


def test_low_latency_opens_the_decoder_in_low_delay_mode(console_factory):
    if not getattr(__import__("bc250_console_link_core"), "DECODER", False):
        pytest.skip("this native core has no decoder")
    console = console_factory(Target.PS4_10, frames=3)
    pictures = []
    with _connection(console, low_latency=True, on_picture=pictures.append) as connection:
        connection.connect()
        connection.run(0.5)
    assert any(line.startswith("Video decoder: FFmpeg") and line.endswith(", low delay.") for line in connection.log)
    assert pictures and console.errors == []


def test_rumble_and_pad_info_go_to_the_controllers(console_factory):
    console = console_factory(Target.PS4_10)
    outputs = []
    with _connection(console) as connection:
        connection.connect()
        # Before anyone drives the controllers: the light bar and player number are kept for later.
        console.send_data(stream.DATA_PAD_INFO, bytes([1, 0x10, 0x20, 0x30, 0]) + bytes(12))             # 17 bytes
        connection.run(0.1)
        connection.drive_controllers(lambda *what: outputs.append(what))
        assert outputs == [("led", (0x10, 0x20, 0x30)), ("player", 1)]
        console.send_data(stream.DATA_RUMBLE, bytes([0, 0x80, 0xff]))
        # 25 bytes: the feedback packet it answers and a timestamp first; a motion reset and a new color, the same
        # player.
        console.send_data(stream.DATA_PAD_INFO, bytes(8) + bytes([1, 0, 0, 0xff, 1]) + bytes(12))
        console.send_data(stream.DATA_RUMBLE, bytes([0, 0]))                    # too short: noted, nothing sent
        seven = bytes.fromhex("00000040010000")                                 # a PS4's 7 bytes (owner's PS4 Pro)
        console.send_data(stream.DATA_PAD_INFO, seven)                          # neither layout: noted once
        console.send_data(stream.DATA_PAD_INFO, seven)
        console.send_data(11, bytes(25))                                        # trigger effects: not used yet
        connection.run(0.2)
    assert outputs[2:] == [("rumble", 0x80, 0xff), ("motion_reset",), ("led", (0, 0, 0xff))]
    assert (connection.stats.rumble, connection.stats.pad_info, connection.stats.other_data) == (1, 2, 1)
    assert "The console sent a rumble message of 2 bytes (3 at least)." in connection.log
    unknown = [line for line in connection.log if "pad info of 7 bytes" in line]
    assert unknown == ["The console sent pad info of 7 bytes, a layout not known yet (00 00 00 40 01 00 00); such "
                       "messages are left aside."] and connection.stats.pad_info_unknown == 2


def test_motion_reaches_the_console(console_factory):
    console = console_factory(Target.PS4_10)
    moving = FEEDBACK["state"][2]                       # gyro, accelerometer and orientation from the reference
    with _connection(console) as connection:
        connection.connect()
        connection.set_controller(gyro=tuple(moving["state"]["gyro"]), accel=tuple(moving["state"]["accel"]),
                                  orient=tuple(moving["state"]["orient"]))
        connection.run(0.05)
    assert console.wait_until(lambda: any(p == h(moving["v9"]) for _, p in console.feedback_states))


def test_lost_units_come_from_fec(console_factory):
    console = console_factory(lose_units={(2, 0), (2, 3)})
    with _connection(console) as connection:
        connection.connect()
        connection.run(0.5)
        assert connection.stats.frames == 3 and connection.stats.fec_frames == 1
        assert connection.stats.frame_bytes == _frame_bytes(console, 1, 2, 3)
        assert connection.stats.corrupt_sent == []


def test_lost_frames_are_reported_to_the_console_and_a_key_frame_asked_for(console_factory):
    # The clip has a key frame every 6: frames 1 and 7 here.
    console = console_factory(frames=8, lose_frames={2}, lose_units={(3, 0), (3, 1), (3, 2)})
    with _connection(console) as connection:
        connection.connect()
        connection.run(0.5)
        video = connection.takion.video_stats()
        # Frame 2 never came; frame 3 had too few units: the console is told, and asked for a key frame. Frames 4 to
        # 6 depend on the lost ones and are skipped; 7 is the key frame, 8 follows it.
        assert connection.stats.frames == 3 and connection.stats.frames_lost == 2
        assert (video["idr_requests"], video["frames_skipped"], video["fec_failed"]) == (1, 3, 1)
        # Each frame's start reports the frames since the last one handed out again, as the reference does.
        assert connection.stats.corrupt_sent[:3] == [(2, 2), (2, 3), (2, 3)]
    assert console.wait_until(lambda: console.received.count(tkproto.IDRREQUEST) == 1)


def test_late_and_lost_video_packets_are_counted_apart(console_factory):
    console = console_factory(frames=4, late_units={(2, 0)}, lose_units={(3, 1)})
    with _connection(console) as connection:
        connection.connect()
        connection.run(0.5)
        stats = connection.takion.stats()
        # The late unit was waited for and came; the lost one was waited for and skipped, FEC rebuilt its frame.
        assert stats["video_late"] == 1 and stats["video_skipped"] == 1
        assert connection.stats.frames == 4 and connection.stats.fec_frames == 1
        assert "1 video packets never came, 1 came late" in connection.video_summary()


def test_simulated_loss_drops_video_packets_on_purpose(console_factory, capsys):
    console = console_factory(frames=6)
    with _connection(console, simulated_loss=100.0) as connection:
        connection.connect()
        connection.run(0.5)
        assert connection.takion.stats()["video_simulated_lost"] > 0 and connection.stats.frames == 0
        assert "dropped on purpose" in connection.video_summary()
    assert "Trying the recovery: 100% of the video packets are dropped on purpose." in capsys.readouterr().err


def test_streaminfo_before_bang_is_kept(console_factory):
    console = console_factory(early_streaminfo=True)
    with _connection(console) as connection:
        connection.connect()
        assert "STREAMINFO came before BANG; kept for later." in connection.log
    assert console.received[:2] == [tkproto.BIG, tkproto.STREAMINFOACK]


def test_wrong_signature_is_only_noted(console_factory):
    console = console_factory(wrong_signature=True)
    with _connection(console) as connection:
        connection.connect()
    assert "The console's key signature does not match (not required)." in connection.log


def test_big_split_over_packets(console_factory):
    console = console_factory()
    with _connection(console, mtu_in=1454, mtu_out=300, rtt_ms=3) as connection:
        connection.connect()
    assert console.big_fragments >= 4 and console.big["session_key"] == SESSION_ID
    assert (console.spec["network"]["mtu"], console.spec["network"]["rtt"]) == (1454, 3)     # mtu in for the spec


def test_console_refuses_the_version(console_factory):
    console = console_factory(refuse_version=True)
    with _connection(console) as connection, pytest.raises(stream.StreamError, match="did not accept stream version"):
        connection.connect()


def test_console_ends_the_stream(console_factory):
    console = console_factory(disconnect_after=1)
    with _connection(console) as connection:
        connection.connect()
        with pytest.raises(stream.StreamError, match="Server shutting down"):
            connection.run(3.0)
        assert connection.remote_reason == "Server shutting down"
    assert console.disconnect_reason is None             # no goodbye after the console's own


def test_no_answer_on_the_stream_port(console_factory):
    console = console_factory(silent=True)
    connection = _connection(console, timeout=0.2)
    with pytest.raises(stream.StreamError, match="did not answer on the stream port"):
        connection.connect()


def test_stream_job_runs_session_and_stream(console_factory, tmp_path):
    """jobs.test_stream end to end: the control connection (fake_console.py) and the stream (fake_stream.py)."""
    from fake_console import REGIST_KEY, SessionConsole
    from fake_stream import SenkushaConsole

    from consoles_link import jobs
    from consoles_link.consoles import RegisteredConsole

    registered = RegisteredConsole("X", "PS5", "127.0.0.1", Target.PS5_1, REGIST_KEY, RP_KEY)
    ctrl = SessionConsole()
    console = console_factory()
    network = SenkushaConsole(Target.PS5_1, b"", b"", mtu_in_limit=1300)
    try:
        outcome = jobs.test_stream(registered, seconds=0.5, stream_port=console.port, senkusha_port=network.port,
                                   port=ctrl.port, timeout=2.0)
    finally:
        ctrl.close()
        network.close()
    assert outcome.ok, outcome.message
    assert "1920×1080" in outcome.message and "3 frames (0 rebuilt with FEC, 0 lost; " in outcome.message
    assert "Mbit/s of video, 3 audio packets" in outcome.message
    assert "Session ID received: the session is running." in outcome.log
    assert any(line.startswith("STREAMINFO received") for line in outcome.log)
    # MTU out starts its search at MTU in (1300); the reference's search then stops one short of its upper bound.
    assert "Network test: MTU 1300 in, 1453 out." in outcome.log
    assert console.spec["streamResolutions"][0]["resolution"] == {"width": 1920, "height": 1080}
    assert console.spec["videoCodec"] == "avc"                    # H.264 from a PS5 too (owner, 13-10-2026)
    assert console.spec["network"]["mtu"] == 1300 and console.spec["network"]["rtt"] == 0
    assert console.wait_until(lambda: console.disconnect_reason == "Client Disconnecting") and console.errors == []

    # A PS4 Pro gets 1080p as a PS5 does, a PS4 720p.
    ps4 = RegisteredConsole("Y", "PS4", "127.0.0.1", Target.PS4_10, REGIST_KEY, RP_KEY)
    assert (jobs.stream_profile(ps4).width, jobs.stream_profile(ps4, "PS4").height) == (1280, 720)
    assert (jobs.stream_profile(ps4, "PS4 Pro").height, jobs.stream_profile(ps4, "PS4 Pro").bitrate) == (1080, 15000)
    for server_type, height in ((1, 1080), (0, 720)):              # SERVER_TYPES: 1 PS4 Pro, 0 PS4
        console = console_factory(Target.PS4_10)
        network = SenkushaConsole(Target.PS4_10, b"", b"")
        ctrl = SessionConsole(target=Target.PS4_10, server_type=server_type)
        try:
            ran = jobs.test_stream(ps4, seconds=0.3, stream_port=console.port, senkusha_port=network.port,
                                   port=ctrl.port, timeout=2.0)
        finally:
            ctrl.close()
            network.close()
        assert ran.ok, ran.message
        assert console.spec["streamResolutions"][0]["resolution"]["height"] == height

    # Stream: the pictures go to the window until it closes (here: once it has two); a controller holds cross.
    from fake_gamepad import FakePad, FakeSdl
    from consoles_link.gamepad import Reading, SOUTH
    pad = FakeSdl({0: FakePad("PS5 Controller", Reading(buttons=frozenset({SOUTH})))})
    console = console_factory(frames=6)
    network = SenkushaConsole(Target.PS5_1, b"", b"")
    ctrl = SessionConsole()
    pictures, sound, stop = [], [], threading.Event()

    def deliver(picture):
        pictures.append(picture)
        if len(pictures) == 2:
            stop.set()
    try:
        watched = jobs.watch_stream(registered, deliver, lambda: True, stop, lambda *pcm: sound.append(pcm), pad,
                                    stream_port=console.port, senkusha_port=network.port, port=ctrl.port, timeout=2.0,
                                    figures=lambda: {"shown": 1}, stats_dir=tmp_path / "streams")
    finally:
        ctrl.close()
        network.close()
    assert watched.ok, watched.message
    assert watched.message.startswith("Stream with PS5 ended after ") and "rebuilt with FEC" in watched.message
    assert watched.value.network.startswith("round trip ") and " bytes in and " in watched.value.network
    if getattr(__import__("bc250_console_link_core"), "DECODER", False):
        assert len(pictures) >= 2                   # the stop is looked at between heartbeats, at most 1 s later
        assert (pictures[0].format, pictures[0].width, pictures[0].height) == ("yuv420p", 160, 96)
        assert len(pictures[0].planes()) == 3
        # The sound: after the 3 frames of prefill, every frame in order, 10 ms of 48 kHz stereo each.
        assert len(sound) >= 3 and all((len(pcm), rate, channels) == (1920, 48000, 2) for pcm, rate, channels in sound)
    assert console.wait_until(lambda: console.disconnect_reason == "Client Disconnecting")
    assert "Controller: PS5 Controller." in watched.log and pad.quit_called
    assert console.feedback_history[0][1:] == (1, bytes.fromhex("8088ff"))
    # The statistics file: its header (the address masked), and a line for the stream's last part at least.
    [stats] = (tmp_path / "streams").glob("stream-*.txt")
    text = stats.read_text()
    assert f"Statistics of this stream, a line per second: {stats}" in watched.log
    assert text.startswith("# Console Link ") and "# Asked for: 1920x1080, 60 fps" in text
    assert registered.address not in text
    assert any(" s | in " in line and "shown 0" in line and "controller " in line for line in text.splitlines())

    # No network test: the stream goes on with the reference's values for that case.
    console = console_factory()
    silent_network = SenkushaConsole(Target.PS5_1, b"", b"", silent=True)
    ctrl = SessionConsole()
    try:
        fallback = jobs.test_stream(registered, seconds=0.3, stream_port=console.port, stream_timeout=0.2,
                                    senkusha_port=silent_network.port, port=ctrl.port, timeout=2.0)
    finally:
        ctrl.close()
        silent_network.close()
    assert fallback.ok, fallback.message
    assert any("The stream uses safe values instead: MTU 1454, 1 ms." in line for line in fallback.log)
    assert console.spec["network"]["mtu"] == 1454 and console.spec["network"]["rtt"] == 1

    # No stream port: the session works, the stream does not.
    silent = console_factory(silent=True)
    ctrl = SessionConsole()
    try:
        failed = jobs.test_stream(registered, seconds=0.5, stream_port=silent.port, stream_timeout=0.2,
                                  senkusha_port=silent.port, port=ctrl.port, timeout=2.0)
    finally:
        ctrl.close()
    assert not failed.ok and "did not answer on the stream port" in failed.message
