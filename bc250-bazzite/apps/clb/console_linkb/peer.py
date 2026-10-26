# SPDX-License-Identifier: GPL-3.0-or-later
# Ported from Greenlight (packages/player/src/client/lib/player.ts, sdp.ts and channel/), MIT, Copyright (c) 2019
# UnknownSKL (Jim Kroon); the MIT notice is in the README's License section.
"""The stream's WebRTC connection, with aiortc on an asyncio loop of its own thread.

As the reference sets it up: sound both ways (the board sends none), video received only, H.264 first, and four
data channels: chat, control, input and message. Once the message channel's handshake is acknowledged, the control
channel authorizes the client and announces the pad, the client sends its configuration, and the input channel
starts: its first report says the client has one touch point, then every 16 ms the pads' states go out, with the
times of the video frames shown (the metadata report the service uses to measure the stream).

The events (video and sound frames, the stream's end, a dialog, rumble) are called on the loop's thread: the
receiver hands them on to its own."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from . import channels, inputs

INPUT_MS = 16
METADATA_BATCH = 5                          # metadata alone waits for this many frames, as the reference's queue
CALL_TIMEOUT_S = 30
CHANNELS = (("chat", "chatV1"), ("control", "controlV1"), ("input", "1.0"), ("message", "messageV1"))


def stereo_sound(sdp: str) -> str:
    """The offer asking for stereo sound, as the reference asks it: "stereo=1" after Opus's "useinbandfec=1".
    aiortc writes no format line for Opus, so the browser's ("minptime=10;useinbandfec=1") is added first."""
    lines = sdp.split("\r\n")
    for at, line in enumerate(lines):
        if line.startswith("a=rtpmap:") and " opus/48000" in line.lower():
            payload = line[len("a=rtpmap:"):].split()[0]
            if not any(other.startswith(f"a=fmtp:{payload} ") for other in lines):
                lines.insert(at + 1, f"a=fmtp:{payload} minptime=10;useinbandfec=1")
            break
    return "\r\n".join(lines).replace("useinbandfec=1", "useinbandfec=1; stereo=1")


@dataclass
class Events:
    video: Callable[[object], None] = lambda frame: None             # an av.VideoFrame
    audio: Callable[[object], None] = lambda frame: None             # an av.AudioFrame
    ready: Callable[[], None] = lambda: None                         # the channels are up, input runs
    closed: Callable[[str], None] = lambda reason: None
    dialog: Callable[[channels.Dialog], None] = lambda dialog: None
    vibration: Callable[[inputs.Vibration], None] = lambda vibration: None
    log: Callable[[str], None] = lambda text: None


def codec_preferences(codecs: list) -> list:
    """The video codecs in the reference's order: H.264 Main, then Constrained Baseline, then Baseline, then the
    others the service may fall back to; rtx stays with them (aiortc needs it for retransmissions)."""
    def rank(codec) -> int:
        mime = codec.mimeType.lower()
        profile = str(codec.parameters.get("profile-level-id", "")).lower()
        if mime == "video/h264":
            return 0 if profile.startswith("4d") else 1 if profile.startswith("42e") else 2
        if mime == "video/rtx":
            return 3
        return 4 if mime in ("video/vp9", "video/vp8", "video/ulpfec", "video/flexfec-03") else 9
    return sorted((c for c in codecs if rank(c) < 9), key=rank)


class Peer:
    def __init__(self, events: Events, clock: Callable[[], float] = time.monotonic):
        self.events = events
        self.clock = clock
        self.started = clock()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, name="console-linkb-webrtc", daemon=True)
        self.pc = None
        self.channels: dict[str, object] = {}
        self.pending: dict[str, list] = {}  # sent before the channel opened
        self.lock = threading.Lock()
        self.pads: list[inputs.PadState] = []
        self.shown: list[inputs.FrameTimes] = []        # video frames shown since the last report
        self.sequence = 0
        self.tasks: list[asyncio.Task] = []
        self.ended = False

    def now_ms(self) -> float:
        return (self.clock() - self.started) * 1000

    # --- The loop's thread --------------------------------------------------------------------------------------

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _call(self, coroutine, timeout: float = CALL_TIMEOUT_S):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout)

    # --- From other threads -------------------------------------------------------------------------------------

    def offer(self) -> str:
        """The board's offer (SDP), with its candidates."""
        return self._call(self._offer())

    def answer(self, sdp: str) -> None:
        self._call(self._answer(sdp))

    def set_pads(self, pads: list[inputs.PadState]) -> None:
        with self.lock:
            self.pads = list(pads)

    def frame_shown(self, rtp_timestamp: int, arrived_ms: float) -> None:
        """A video frame is on the screen: its times go to the service with the next input report."""
        shown = self.now_ms()
        with self.lock:
            self.shown.append(inputs.FrameTimes(rtp_timestamp, arrived_ms, shown, shown))

    def answer_dialog(self, dialog: channels.Dialog, accepted: bool) -> None:
        self.loop.call_soon_threadsafe(self._send, "message", channels.dialog_answer(dialog, accepted))

    def request_keyframe(self) -> None:
        self.loop.call_soon_threadsafe(self._send, "control", channels.keyframe_request())

    def close(self) -> None:
        if self.loop.is_closed():
            return
        if self.thread.is_alive():
            try:
                self._call(self._close(), timeout=5)
            except Exception:  # noqa: BLE001  (closing never fails the app)
                pass
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(5)
        if not self.loop.is_running():
            self.loop.close()

    # --- Inside the loop ----------------------------------------------------------------------------------------

    async def _offer(self) -> str:
        from aiortc import RTCConfiguration, RTCPeerConnection, RTCRtpReceiver
        # No STUN server, as the reference (RTCPeerConnection({})): the board's own addresses only
        pc = self.pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        pc.addTransceiver("audio", direction="sendrecv")
        video = pc.addTransceiver("video", direction="recvonly")
        video.setCodecPreferences(codec_preferences(RTCRtpReceiver.getCapabilities("video").codecs))
        for name, protocol in CHANNELS:
            channel = pc.createDataChannel(name, ordered=True, protocol=protocol)
            self.channels[name] = channel
            channel.on("open", lambda name=name: self._opened(name))
            channel.on("message", lambda data, name=name: self._received(name, data))
        pc.on("track", self._track)
        pc.on("connectionstatechange", self._state_changed)
        await pc.setLocalDescription(await pc.createOffer())
        return stereo_sound(pc.localDescription.sdp)

    async def _answer(self, sdp: str) -> None:
        from aiortc import RTCSessionDescription
        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="answer"))

    async def _close(self) -> None:
        self.ended = True
        for task in self.tasks:
            task.cancel()
        if self.pc is not None:
            await self.pc.close()

    def _state_changed(self) -> None:
        state = self.pc.connectionState
        self.events.log(f"Connection: {state}")
        if state in ("failed", "closed") and not self.ended:
            self.ended = True
            self.events.closed("the connection to the stream was lost" if state == "failed" else
                               "the connection was closed")

    def _send(self, name: str, data: str | bytes) -> None:
        channel = self.channels.get(name)
        if channel is None:
            return
        if channel.readyState != "open":
            self.pending.setdefault(name, []).append(data)
            return
        channel.send(data)

    def _opened(self, name: str) -> None:
        for data in self.pending.pop(name, []):
            self.channels[name].send(data)
        if name == "message":
            self._send("message", channels.handshake())

    def _received(self, name: str, data: str | bytes) -> None:
        if name == "message":
            incoming = channels.handle(data if isinstance(data, str) else data.decode("utf-8", "replace"))
            for reply in incoming.replies:
                self._send("message", reply)
            if incoming.handshake_done:
                self._handshake_done()
            if incoming.dialog is not None:
                self.events.dialog(incoming.dialog)
            if incoming.disconnect and not self.ended:
                self.ended = True
                self.events.closed("the stream was ended by the Xbox or the streaming service")
        elif name == "input" and isinstance(data, bytes):
            report = inputs.parse(data)
            if isinstance(report, inputs.Vibration):
                self.events.vibration(report)
            elif isinstance(report, inputs.ServerSize):
                self.events.log(f"Server video: {report.width} × {report.height}")

    def _handshake_done(self) -> None:
        self._send("control", channels.authorization())
        self._send("control", channels.gamepad_changed(0, True))
        self._send("control", channels.gamepad_changed(0, False))
        self._send("control", channels.gamepad_changed(0, True))     # the pad, as the reference attaches it
        self._send("input", inputs.client_metadata(self._next(), self.now_ms()))
        for text in channels.configuration():
            self._send("message", text)
        self.tasks.append(asyncio.ensure_future(self._input_loop()))
        self.events.ready()

    def _next(self) -> int:
        self.sequence += 1
        return self.sequence

    async def _input_loop(self) -> None:
        while not self.ended:
            with self.lock:
                pads = self.pads
                frames = self.shown if (pads or len(self.shown) > METADATA_BATCH) else []
                if frames:
                    self.shown = []
            if pads or frames:
                self._send("input", inputs.report(self._next(), self.now_ms(), pads, frames))
            await asyncio.sleep(INPUT_MS / 1000)

    def _track(self, track) -> None:
        self.events.log(f"Track: {track.kind}")
        self.tasks.append(asyncio.ensure_future(self._receive(track)))

    async def _receive(self, track) -> None:
        from aiortc.mediastreams import MediaStreamError
        handler = self.events.video if track.kind == "video" else self.events.audio
        while not self.ended:
            try:
                frame = await track.recv()
            except MediaStreamError:
                return
            handler(frame)
