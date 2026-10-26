# SPDX-License-Identifier: GPL-3.0-or-later
"""The WebRTC side: the codec order, the offer, and a whole connection on this machine with a stand-in for the
streaming service (an aiortc peer that answers, acknowledges the handshake, sends video and sound, rumble and the
stream's end, and records what the board sends)."""

from __future__ import annotations

import asyncio
import json
import struct
import threading
import time
from dataclasses import dataclass, field

import pytest

from console_linkb import channels, ice, inputs
from console_linkb.peer import Events, Peer, codec_preferences, stereo_sound


@dataclass
class Codec:
    mimeType: str
    parameters: dict = field(default_factory=dict)


def test_codec_order_h264_main_first():
    codecs = [Codec("video/VP8"), Codec("video/rtx"), Codec("video/H264", {"profile-level-id": "42001f"}),
              Codec("video/H264", {"profile-level-id": "42e01f"}), Codec("video/H264", {"profile-level-id": "4d001f"}),
              Codec("video/AV1")]
    ordered = [(c.mimeType, c.parameters.get("profile-level-id")) for c in codec_preferences(codecs)]
    assert ordered == [("video/H264", "4d001f"), ("video/H264", "42e01f"), ("video/H264", "42001f"),
                       ("video/rtx", None), ("video/VP8", None)]


def test_stereo_sound():
    sdp = "m=audio 9 UDP 96 0\r\na=rtpmap:96 opus/48000/2\r\na=rtpmap:0 PCMU/8000\r\n"
    assert "a=rtpmap:96 opus/48000/2\r\na=fmtp:96 minptime=10;useinbandfec=1; stereo=1\r\n" in stereo_sound(sdp)
    with_fmtp = "a=rtpmap:111 opus/48000/2\r\na=fmtp:111 minptime=10;useinbandfec=1\r\n"
    assert stereo_sound(with_fmtp) == "a=rtpmap:111 opus/48000/2\r\na=fmtp:111 minptime=10;useinbandfec=1; stereo=1\r\n"


class Service:
    """The streaming service's side of the connection, on a loop of its own."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.received: dict[str, list] = {"control": [], "message": [], "input": [], "chat": []}
        self.channels: dict[str, object] = {}
        self.pc = None

    def call(self, coroutine, timeout=20):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout)

    def answer(self, offer: str) -> str:
        return self.call(self._answer(offer))

    async def _answer(self, offer: str) -> str:
        from aiortc import (AudioStreamTrack, RTCConfiguration, RTCPeerConnection, RTCRtpSender,
                            RTCSessionDescription, VideoStreamTrack)
        pc = self.pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))

        @pc.on("datachannel")
        def datachannel(channel):
            self.channels[channel.label] = channel

            @channel.on("message")
            def message(data):
                self.received.setdefault(channel.label, []).append(data)
                if channel.label == "message" and isinstance(data, str) and json.loads(data).get("type") == \
                        "Handshake":
                    channel.send(json.dumps({"type": "HandshakeAck"}))

        pc.addTrack(AudioStreamTrack())
        video = pc.addTransceiver(VideoStreamTrack(), direction="sendonly")
        # VP8, which every PyAV build can encode, for the stand-in's video
        video.setCodecPreferences([c for c in RTCRtpSender.getCapabilities("video").codecs
                                   if c.mimeType in ("video/VP8", "video/rtx")])
        await pc.setRemoteDescription(RTCSessionDescription(sdp=offer, type="offer"))
        await pc.setLocalDescription(await pc.createAnswer())
        return pc.localDescription.sdp

    def send(self, label: str, data) -> None:
        self.loop.call_soon_threadsafe(self.channels[label].send, data)

    def close(self) -> None:
        if self.pc is not None:
            self.call(self.pc.close())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)


def service_candidates(answer: str) -> list[dict]:
    """The stand-in's candidates as the service hands them out in the ice exchange."""
    return [{"candidate": f"a={c['candidate']}", "sdpMid": "0", "sdpMLineIndex": "0"}
            for c in ice.local_candidates(answer)]


def wait_for(condition, timeout=15.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_a_whole_connection_with_a_stand_in_service():
    pytest.importorskip("aiortc")
    got = {"video": [], "audio": [], "ready": 0, "closed": [], "vibration": [], "dialog": []}
    events = Events(video=got["video"].append, audio=got["audio"].append,
                    ready=lambda: got.__setitem__("ready", got["ready"] + 1), closed=got["closed"].append,
                    vibration=got["vibration"].append, dialog=got["dialog"].append)
    peer, service = Peer(events), Service()
    try:
        peer.start()
        offer = peer.offer()
        assert "a=fmtp:96 minptime=10;useinbandfec=1; stereo=1" in offer
        assert all(" typ host" in c["candidate"] for c in ice.local_candidates(offer))     # no STUN
        answer = service.answer(offer)
        # The service's candidates come through the exchange, the answer as the service gives it, without them
        bare = "\r\n".join(line for line in answer.split("\r\n") if not line.startswith("a=candidate:")
                           and line != "a=end-of-candidates")
        peer.answer(ice.with_candidates(bare, ice.remote_candidates(service_candidates(answer))))

        assert wait_for(lambda: got["ready"] == 1), "the handshake was not acknowledged"
        assert wait_for(lambda: len(service.received["control"]) >= 4)
        control = [json.loads(m) for m in service.received["control"]]
        assert control[0] == {"message": "authorizationRequest", "accessKey": channels.ACCESS_KEY}
        assert [m["wasAdded"] for m in control[1:4]] == [True, False, True]
        assert wait_for(lambda: len(service.received["message"]) >= 7)
        messages = [json.loads(m) for m in service.received["message"]]
        assert messages[0]["type"] == "Handshake"
        assert messages[-1]["target"] == "/streaming/characteristics/dimensionschanged"

        assert wait_for(lambda: service.received["input"])
        first = service.received["input"][0]
        assert len(first) == 15 and struct.unpack("<H", first[:2])[0] == inputs.CLIENT_METADATA
        peer.set_pads([inputs.PadState(0, frozenset({"a"}), left_x=0.5)])
        assert wait_for(lambda: any(struct.unpack("<H", r[:2])[0] & inputs.GAMEPAD
                                    for r in service.received["input"][1:]))
        report = next(r for r in service.received["input"][1:] if struct.unpack("<H", r[:2])[0] & inputs.GAMEPAD)
        assert struct.unpack("<BHh", report[15:20]) == (0, 16, 16384)

        assert wait_for(lambda: got["video"] and got["audio"]), "no video or sound came through"
        frame = got["video"][-1]
        assert frame.width > 0 and frame.height > 0
        peer.frame_shown(int(frame.pts or 0), 1.0)
        assert wait_for(lambda: any(struct.unpack("<H", r[:2])[0] & inputs.METADATA
                                    for r in service.received["input"]))

        service.send("input", bytes([128, 0, 0, 0, 80, 40, 0, 0]) + struct.pack("<HH", 300, 0) + bytes([0]))
        assert wait_for(lambda: got["vibration"])
        assert got["vibration"][0].left == 0.8 and got["vibration"][0].duration_ms == 300

        service.send("message", json.dumps({"type": "TransactionStart", "target": channels.DIALOG, "id": "D1",
                                            "content": json.dumps({"TitleText": "Quit?", "ContentText": "Sure?"})}))
        assert wait_for(lambda: got["dialog"])
        peer.answer_dialog(got["dialog"][0], True)
        assert wait_for(lambda: any('"D1"' in m for m in service.received["message"]))

        service.send("message", json.dumps({"type": "TransactionStart", "target": channels.DISCONNECT, "id": "T9",
                                            "content": "{}"}))
        assert wait_for(lambda: got["closed"])
        assert "ended by the Xbox" in got["closed"][0]
        assert wait_for(lambda: any('"T9"' in m for m in service.received["message"]))
    finally:
        peer.close()
        service.close()
    assert not peer.thread.is_alive()
