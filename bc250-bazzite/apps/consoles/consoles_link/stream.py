# SPDX-License-Identifier: AGPL-3.0-only
"""The stream connection, once the control connection has the session ID.

1. Takion on UDP 9296: the handshake (the native core, bc250_console_link_core.Takion).
2. BIG: the session ID, the launch spec (resolution, frame rate, bitrate, codec) and our ECDH public key, signed
   with a random handshake key. The console answers BANG with its public key; both sides derive the stream keys.
3. STREAMINFO: the console's video headers per resolution and its audio header. We acknowledge it, report the
   controller and announce the microphone; from then on video and audio flow, and a heartbeat goes every second.
   The native core sends the controller's state from then on, at least every 200 ms (idle until set_controller:
   without it a PS4 pauses the stream). The console sends the controller's rumble and pad info (the light bar's
   color, the player number, a request to reset the motion), which go to on_controller.
   The native core puts the video frames together (FEC rebuilds lost units), names the frames that never came or
   could not be rebuilt, which go to the console as CORRUPTFRAME, and sends the congestion reports. The frames go
   to the video decoder (FFmpeg in the native core): the resolution's header from STREAMINFO first, then each frame.
   It decodes with VA-API where the GPU has a video decoder, else in software (the BC-250 has none). The sound
   comes as Opus frames in order (10 ms each), decoded to 16-bit PCM with the audio header from STREAMINFO.
4. DISCONNECT from either side ends it.

The network test before this (Senkusha, senkusha.py) measures the MTU both ways and the round trip, which go into
the launch spec; without it, the values are the reference's for a failed test: 1454 bytes and 1 ms."""

from __future__ import annotations

import os
import sys
import time
from time import perf_counter
from dataclasses import dataclass, field
from typing import Callable

from . import launchspec, tkproto
from .rpcrypt import RPCrypt
from .target import Target
from .video import Picture

PORT = 9296
EXPECT_TIMEOUT = 5.0
HEARTBEAT_INTERVAL = 1.0
MTU = 1454                              # the reference's values when the network test fails
RTT_MS = 1
HANDSHAKE_KEY_SIZE = 16
CHANNEL = 1
CHANNEL_STREAMINFO_ACK = 9
CHANNEL_FRAME_REPORTS = 2
DATA_PROTOBUF = 0
DATA_RUMBLE = 7
DATA_PAD_INFO = 9
MTU_OVERHEAD = 50                       # the reference: the network's share of the MTU
DATA_OVERHEAD = 26                      # type byte, message header and DATA header; a continuation has one less


class StreamError(Exception):
    pass


def _core():
    try:
        import bc250_console_link_core
    except ImportError as error:
        raise StreamError("The stream needs the app's native core (bc250_console_link_core), which is not "
                          "installed: install Rust (rustup) and run install.sh again.") from error
    return bc250_console_link_core


@dataclass
class Profile:
    """What the launch spec asks for."""
    width: int = 1920
    height: int = 1080
    max_fps: int = 60
    bitrate: int = 15000                # kbit/s
    codec: str = "h264"


PLAYER_MODES = ("off", "announce", "marked", "packed")
RAW_NOTES = 40                          # the experiment's raw notes of what the console sends, at most


@dataclass(frozen=True)
class PlayerExperiment:
    """The several-players experiment (not for users): how a second controller goes to the console, to find out what
    the console accepts. announce: the console is told a second controller connected (CONTROLLERCONNECTION with
    controller_id), its input is not sent; marked: also its input, in packets of its own with *mark* in the first
    byte of each state and event; packed: also its state, in the first one's state packets (two states in one)."""
    mode: str = "off"
    controller_id: int = 1
    mark: int = 1

    @classmethod
    def parse(cls, text: str) -> PlayerExperiment:
        """MODE[:CONTROLLER_ID[:MARK]], as --player-experiment takes it."""
        mode, *numbers = text.split(":")
        if mode not in PLAYER_MODES or len(numbers) > 2:
            raise ValueError(f"MODE[:CONTROLLER_ID[:MARK]] with MODE one of {', '.join(PLAYER_MODES)}")
        values = [int(n) for n in numbers]
        if any(not 0 <= v <= 15 for v in values):
            raise ValueError("CONTROLLER_ID and MARK are 0 to 15")
        return cls(mode, *values)

    @property
    def on(self) -> bool:
        return self.mode != "off"


@dataclass
class StreamStats:
    frames: int = 0                     # whole video frames
    frame_bytes: int = 0
    fec_frames: int = 0                 # frames with units rebuilt by FEC
    frames_lost: int = 0
    audio_packets: int = 0
    haptics_packets: int = 0
    other_data: int = 0                 # trigger effects (a DualSense's adaptive triggers): not used yet
    rumble: int = 0
    pad_info: int = 0
    pad_info_unknown: int = 0           # in a layout not known yet (a PS4's 7 bytes)
    corrupt_sent: list[tuple[int, int]] = field(default_factory=list)       # frames reported to the console
    corrupt_reports: list[tuple[int, int]] = field(default_factory=list)
    decoded: int = 0                    # pictures out of the decoder
    audio_frames: int = 0               # 10 ms frames of sound, decoded
    audio_lost: int = 0                 # frames that never came, played as silence
    decode_errors: int = 0
    decode_seconds: float = 0.0
    decode_max: float = 0.0             # the longest decode since figures() last read it
    frame_gap_max: float = 0.0          # the longest wait between two frames since then


class StreamConnection:
    """One stream with a console whose control connection is running. connect() runs steps 1 to 3."""

    def __init__(self, host: str, target: Target, session_id: str, crypt: RPCrypt, profile: Profile | None = None,
                 dualsense: bool = False, port: int = PORT, timeout: float = EXPECT_TIMEOUT,
                 mtu_in: int | None = None, mtu_out: int | None = None, rtt_ms: int = RTT_MS,
                 random: Callable[[int], bytes] = os.urandom, core=None,
                 on_picture: Callable[[Picture], None] | None = None,
                 picture_wanted: Callable[[], bool] = lambda: True,
                 on_sound: Callable[[bytes, int, int], None] | None = None,
                 players: PlayerExperiment = PlayerExperiment(), low_latency: bool = False,
                 simulated_loss: float = 0.0):
        self.host, self.target, self.session_id, self.crypt = host, target, session_id, crypt
        self.profile = profile or Profile()
        self.dualsense, self.port, self.timeout, self.random = dualsense, port, timeout, random
        self.mtu_in, self.mtu_out, self.rtt_ms = mtu_in or MTU, mtu_out or MTU, rtt_ms
        self.core = core or _core()
        self.on_picture, self.picture_wanted = on_picture, picture_wanted
        self.on_sound = on_sound              # (16-bit PCM interleaved, rate, channels)
        self.players = players
        self.low_latency = low_latency          # the stream settings: the decoder's low-delay mode
        self.simulated_loss = simulated_loss    # for trying the recovery (not for users): % of video packets dropped
        self._raw_notes = 0
        self.on_controller: Callable[..., None] | None = None
        self.led: tuple[int, int, int] = (0, 0, 0)
        self.player_index = 0
        self.audio_decoder = None
        self.takion = None
        self.handshake_key = b""
        self.ecdh = None
        self.bang: tkproto.Bang | None = None
        self.info: tkproto.StreamInfo | None = None
        self.audio: tkproto.AudioHeader | None = None
        self.stats = StreamStats()
        self.remote_reason: str | None = None
        self.log: list[str] = []
        self._early_streaminfo: tkproto.Message | None = None
        self.decoder = None
        self.decode_error: str | None = None
        self._header = b""
        self._last_frame: float | None = None

    def __enter__(self) -> StreamConnection:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def note(self, text: str) -> None:
        self.log.append(text)
        if self.players.on or self.simulated_loss:     # the trials run from a terminal: what happens, as it happens
            print(f"[{time.strftime('%H:%M:%S')}] {text}", file=sys.stderr, flush=True)

    def _raw(self, what: str, data: bytes) -> None:
        """The experiment: what the console sends, raw, the first RAW_NOTES times."""
        if self.players.on and self._raw_notes < RAW_NOTES:
            self._raw_notes += 1
            self.note(f"Experiment: the console sent {what}: {data.hex(' ')}")

    @property
    def hevc(self) -> bool:
        return self.target.ps5 and self.profile.codec in ("h265", "h265_hdr")

    @property
    def version(self) -> int:
        return 12 if self.target.ps5 else 9

    # --- Sending --------------------------------------------------------------------------------------------

    def send(self, data: bytes, channel: int = CHANNEL) -> None:
        self.takion.send_data(data, channel=channel, flags=1)

    def send_big(self) -> None:
        """BIG, split over several DATA messages when it does not fit the MTU."""
        spec = launchspec.format_spec(self.target, self.profile.width, self.profile.height, self.profile.max_fps,
                                      self.profile.codec, self.profile.bitrate, self.mtu_in, self.rtt_ms,
                                      self.handshake_key)
        public_key, signature = self.ecdh.signed_public_key(self.handshake_key)
        data = tkproto.big(self.version, self.session_id, launchspec.encode_for_big(self.crypt, spec), public_key,
                           signature)
        mtu = min(self.mtu_in, self.mtu_out) - MTU_OVERHEAD
        first = True
        while mtu < len(data) + DATA_OVERHEAD or (mtu < len(data) + DATA_OVERHEAD - 1 and not first):
            size = mtu - DATA_OVERHEAD + (0 if first else 1)
            self.takion.send_data(data[:size], channel=CHANNEL, flags=0, cont=not first)
            data, first = data[size:], False
        if data:
            self.takion.send_data(data, channel=CHANNEL, flags=1, cont=not first)

    def heartbeat(self) -> None:
        self.send(tkproto.heartbeat())

    def request_idr(self) -> None:
        self.send(tkproto.idr_request(), CHANNEL_FRAME_REPORTS)

    def drive_controllers(self, output: Callable[..., None] | None) -> None:
        """From now on the console's rumble and pad info go to *output*: ("rumble", left, right) with 0 to 255,
        ("led", (r, g, b)), ("player", index) and ("motion_reset",). The light bar and the player number the console
        has set so far go to it at once."""
        self.on_controller = output
        if output is not None:
            if self.led != (0, 0, 0):
                output("led", self.led)
            if self.player_index:
                output("player", self.player_index)

    def _controller_output(self, *what) -> None:
        if self.on_controller is not None:
            self.on_controller(*what)

    def _on_rumble(self, data: bytes) -> None:
        if len(data) < 3:
            self.note(f"The console sent a rumble message of {len(data)} bytes (3 at least).")
            return
        self.stats.rumble += 1
        self._raw("rumble", data)
        self._controller_output("rumble", data[1], data[2])          # byte 0 is not known

    def _on_pad_info(self, data: bytes) -> None:
        """The reference's two layouts: 25 bytes (the sequence number of the feedback packet it answers, a
        timestamp, then the player number at 8, the color at 9 and the motion reset at 12) and 17 bytes (the player
        number, the color and the motion reset from the start). A PS4 also sends 7 bytes (00 00 00 40 01 00 00 on the
        owner's PS4 Pro, 13-10-2026) at the stream's start and when a PS press hands it a controller; their meaning is
        not known, so they are counted and noted once."""
        self._raw("pad info", data)
        if len(data) == 0x19:
            player, led, reset = data[8], tuple(data[9:12]), bool(data[12])
        elif len(data) == 0x11:
            player, led, reset = data[0], tuple(data[1:4]), bool(data[4])
        else:
            self.stats.pad_info_unknown += 1
            if self.stats.pad_info_unknown == 1:
                self.note(f"The console sent pad info of {len(data)} bytes, a layout not known yet "
                          f"({data.hex(' ')}); such messages are left aside.")
            return
        self.stats.pad_info += 1
        if reset:
            self._controller_output("motion_reset")
        if led != self.led:
            self.led = led
            self._controller_output("led", led)
        if player != self.player_index:
            self.player_index = player
            self._controller_output("player", player)

    def set_second_controller(self, **state) -> None:
        """The several-players experiment: the second controller, as set_controller."""
        self.takion.set_second_controller_state(**state)

    def set_controller(self, **state) -> None:
        """The controller as it is now (the native core's Takion.set_controller_state: buttons, l2, r2, left, right,
        touches, gyro, accel, orient); what is left out is idle."""
        self.takion.set_controller_state(**state)

    # --- Receiving ------------------------------------------------------------------------------------------

    def _count_av(self, header: dict) -> None:
        if header["video"]:
            return                                  # video before STREAMINFO: no frames to put it in yet
        if header["haptics"]:
            self.stats.haptics_packets += 1
        else:
            self.stats.audio_packets += 1

    def _decode(self, sample: bytes) -> None:
        if self.decoder is None:
            return
        sample, self._header = self._header + sample, b""
        started = perf_counter()
        try:
            frames = self.decoder.decode(sample)
            self.stats.decoded += len(frames)
            if frames and self.on_picture is not None and self.picture_wanted():
                self.on_picture(Picture.from_image(self.decoder.image()))
        except ValueError as error:
            self.stats.decode_errors += 1
            if self.decode_error is None:
                self.decode_error = str(error)
                self.note(f"The decoder refused a frame ({error}).")
        took = perf_counter() - started
        self.stats.decode_seconds += took
        self.stats.decode_max = max(self.stats.decode_max, took)

    def _on_frame(self, info: dict, data: bytes) -> None:
        now = perf_counter()
        if self._last_frame is not None:
            self.stats.frame_gap_max = max(self.stats.frame_gap_max, now - self._last_frame)
        self._last_frame = now
        self.stats.frames += 1
        self.stats.frame_bytes += len(data)
        self.stats.fec_frames += info["fec"]
        self.stats.frames_lost += info["frames_lost"]
        self._decode(data)

    def _on_audio(self, data: bytes | None) -> None:
        self.stats.audio_frames += 1
        self.stats.audio_lost += data is None
        if self.audio_decoder is None:
            return
        try:
            pcm = self.audio_decoder.decode(data)
        except ValueError as error:
            self.stats.decode_errors += 1
            if self.decode_error is None:
                self.decode_error = str(error)
                self.note(f"The sound decoder refused a frame ({error}).")
            return
        if self.on_sound is not None:
            self.on_sound(pcm, self.audio.rate, self.audio.channels)

    def _on_profile(self, index: int) -> None:
        resolutions = self.info.resolutions if self.info else []
        size = f"{resolutions[index].width}×{resolutions[index].height}" if index < len(resolutions) else "?"
        self.note(f"Video at {size} (resolution {index}).")
        if index < len(resolutions):
            # The reference sends the header as a sample of its own, which FFmpeg's H.264 decoder refuses (it has no
            # picture); here it goes in front of the next frame, one access unit for the decoder.
            self._header = resolutions[index].video_header

    def _open_decoder(self) -> None:
        if not getattr(self.core, "DECODER", False):
            self.note("This native core has no video decoder (built without FFmpeg): the frames are not decoded.")
            return
        codec = "hevc" if self.hevc else "h264"
        try:
            # low_delay only when asked: an older native core takes no such argument.
            self.decoder = self.core.Decoder(codec, hw=True, **({"low_delay": True} if self.low_latency else {}))
        except ValueError as error:
            self.note(f"The video decoder did not open ({error}).")
            return
        how = "VA-API" if self.decoder.hw else f"software (VA-API: {self.decoder.hw_error or 'not available'})"
        self.note(f"Video decoder: FFmpeg {self.core.FFMPEG_VERSION}, {codec.upper()}, {how}"
                  f"{', low delay' if self.low_latency else ''}.")
        try:
            self.audio_decoder = self.core.AudioDecoder(self.audio.rate, self.audio.channels, self.audio.frame_size)
        except (ValueError, AttributeError) as error:
            self.note(f"The sound decoder did not open ({error}).")

    def _on_corrupt(self, start: int, end: int) -> None:
        self.stats.corrupt_sent.append((start, end))
        self.send(tkproto.corrupt_frame(start, end), CHANNEL_FRAME_REPORTS)

    def poll(self, timeout: float) -> tkproto.Message | None:
        """The next protobuf message, or None after *timeout*. Frames and audio are counted, corrupt frames reported;
        a DISCONNECT from the console or a closed connection raises StreamError."""
        deadline = time.monotonic() + timeout
        while True:
            event = self.takion.next_event(max(0.0, deadline - time.monotonic()))
            if event is None:
                return None
            kind = event[0]
            if kind == "frame":
                self._on_frame(event[1], event[2])
            elif kind == "av":
                self._count_av(event[1])
            elif kind == "corrupt":
                self._on_corrupt(event[1], event[2])
            elif kind == "idr":
                self.request_idr()
            elif kind == "profile":
                self._on_profile(event[1])
            elif kind == "audio":
                self._on_audio(event[2])
            elif kind == "closed":
                raise StreamError(f"The stream connection closed: {event[1]}.")
            elif kind == "data":
                _kind, data_type, _channel, data = event
                if data_type == DATA_RUMBLE:
                    self._on_rumble(data)
                    continue
                if data_type == DATA_PAD_INFO:
                    self._on_pad_info(data)
                    continue
                if data_type != DATA_PROTOBUF:
                    self.stats.other_data += 1
                    self._raw(f"data type {data_type}", data)
                    continue
                try:
                    message = tkproto.parse(data)
                except tkproto.ProtoError as error:
                    self.note(f"The console sent a message that does not decode ({error}).")
                    continue
                reason = tkproto.disconnect_reason(message)
                if reason is not None:
                    self.remote_reason = reason
                    raise StreamError(f"The console ended the stream: {reason or 'no reason given'}.")
                corrupt = tkproto.corrupt_range(message)
                if corrupt is not None:
                    self.stats.corrupt_reports.append(corrupt)
                    continue
                return message
            if time.monotonic() >= deadline:
                return None

    def _expect(self, what: str, accept: Callable[[tkproto.Message], bool]) -> None:
        deadline = time.monotonic() + self.timeout
        while (remaining := deadline - time.monotonic()) > 0:
            message = self.poll(remaining)
            if message is not None and accept(message):
                return
        raise StreamError(f"The console sent no {what} within {self.timeout:g} seconds.")

    def _on_bang(self, message: tkproto.Message) -> bool:
        if message.type == tkproto.STREAMINFO and self._early_streaminfo is None:
            self._early_streaminfo = message                 # the reference keeps one that comes before BANG
            self.note("STREAMINFO came before BANG; kept for later.")
            return False
        bang = tkproto.bang(message)
        if bang is None:
            self.note(f"Expected BANG, got message type {message.type}.")
            return False
        self.bang = bang
        if not bang.version_accepted:
            raise StreamError(f"The console did not accept stream version {self.version} (it has "
                              f"{bang.server_version_string or bang.server_version}).")
        if not bang.encrypted_key_accepted:
            raise StreamError("The console did not accept the encrypted key in BIG.")
        if not bang.ecdh_public_key or not bang.ecdh_signature:
            raise StreamError("The console's BANG has no key for the stream crypto.")
        # The reference does not check this signature; this notes what the console does, without failing on it.
        signed = self.core.verify_signature(self.handshake_key, bang.ecdh_public_key, bang.ecdh_signature)
        self.note("The console's key signature " + ("checks out." if signed else "does not match (not required)."))
        try:
            secret = self.ecdh.derive_secret(bang.ecdh_public_key)
        except ValueError as error:
            raise StreamError("The console's public key for the stream is invalid.") from error
        self.takion.set_crypt(self.handshake_key, secret)
        self.note(f"BANG received (server version {bang.server_version}); the stream is encrypted.")
        return True

    def _on_streaminfo(self, message: tkproto.Message) -> bool:
        info = tkproto.streaminfo(message)
        if info is None:
            self.note(f"Expected STREAMINFO, got message type {message.type}.")
            return False
        try:
            self.audio = tkproto.AudioHeader.load(info.audio_header)
        except tkproto.ProtoError as error:
            raise StreamError(f"The console's STREAMINFO is invalid: {error}.") from error
        self.info = info
        self._open_decoder()
        if self.players.on:
            self.takion.set_player_experiment("off" if self.players.mode == "announce" else self.players.mode,
                                              self.players.mark)
        self.takion.start_stream([r.video_header for r in info.resolutions], hevc=self.hevc)
        if self.simulated_loss:
            self.takion.set_simulated_loss(self.simulated_loss)
            self.note(f"Trying the recovery: {self.simulated_loss:g}% of the video packets are dropped on purpose.")
        self.send(tkproto.streaminfo_ack(), CHANNEL_STREAMINFO_ACK)
        self.send(tkproto.controller_connection(self.dualsense))
        if self.players.on:
            self.send(tkproto.controller_connection(self.dualsense, self.players.controller_id))
            self.note(f"Experiment {self.players.mode}: a second controller announced (controller_id "
                      f"{self.players.controller_id}, mark {self.players.mark}).")
        self.send(tkproto.microphone(tkproto.MICROPHONE.save()))
        sizes = ", ".join(f"{r.width}×{r.height}" for r in info.resolutions) or "no resolution"
        self.note(f"STREAMINFO received ({sizes}; audio {self.audio.channels} channels at {self.audio.rate} Hz).")
        return True

    # --- The connection -------------------------------------------------------------------------------------

    def connect(self) -> tkproto.StreamInfo:
        try:
            self.takion = self.core.Takion(self.host, self.port, self.version, self.timeout)
        except TimeoutError as error:
            raise StreamError(f"The console did not answer on the stream port {self.port}: {error}.") from error
        except OSError as error:                         # ConnectionError included
            raise StreamError(f"The stream connection to {self.host} failed: {error}.") from error
        self.note(f"Stream connection open (Takion version {self.version}).")
        self.handshake_key = self.random(HANDSHAKE_KEY_SIZE)
        self.ecdh = self.core.Ecdh()
        self.send_big()
        self._expect("BANG", self._on_bang)
        early, self._early_streaminfo = self._early_streaminfo, None
        if early is None or not self._on_streaminfo(early):
            self._expect("STREAMINFO", self._on_streaminfo)
        return self.info

    def run(self, seconds: float, stop: Callable[[], bool] = lambda: False) -> None:
        """Keep the stream for *seconds*: heartbeats every second, everything that comes in counted."""
        deadline = time.monotonic() + seconds
        next_beat = time.monotonic()
        while (now := time.monotonic()) < deadline and not stop():
            if now >= next_beat:
                self.heartbeat()
                next_beat = now + HEARTBEAT_INTERVAL
            message = self.poll(min(next_beat, deadline) - now)
            if message is not None and message.type not in (tkproto.STREAMINFOACK, tkproto.CONNECTIONQUALITY,
                                                             tkproto.HEARTBEAT):
                self.note(f"Message type {message.type} received.")
                if self.players.on:
                    self.note(f"Experiment: message type {message.type}: {message.payloads}")

    def figures(self) -> dict:
        """For the statistics file (stream_stats.py), from its thread: the counters, and the maxima since the last
        call, which start again."""
        stats = self.stats
        figures = {"frames": stats.frames, "frame_bytes": stats.frame_bytes, "frames_lost": stats.frames_lost,
                   "fec_frames": stats.fec_frames, "decoded": stats.decoded, "decode_seconds": stats.decode_seconds,
                   "decode_max": stats.decode_max, "frame_gap_max": stats.frame_gap_max,
                   "audio_frames": stats.audio_frames, "audio_lost": stats.audio_lost}
        stats.decode_max = stats.frame_gap_max = 0.0
        video = self.takion.video_stats() if self.takion else None
        if video is not None:
            figures.update(fec_failed=video["fec_failed"], idr_requests=video["idr_requests"],
                           frames_skipped=video["frames_skipped"], missing_reference=video["missing_reference"])
        return figures

    def video_summary(self) -> str:
        """The native core's view of the video and the congestion reports, for the log."""
        video = self.takion.video_stats() if self.takion else None
        if video is None:
            return "No video stream."
        stats = self.takion.stats()
        summary = (f"Video: {video['frames']} frames, {video['fec_recovered']} rebuilt with FEC, {video['fec_failed']} "
                   f"beyond repair, {video['frames_lost']} lost; {video['bad_units'] + video['old_packets']} units "
                   f"refused; {stats['congestion_reports']} congestion reports sent. Recovery: "
                   f"{video['idr_requests']} key frames asked for, {video['frames_skipped']} frames skipped waiting "
                   f"for one, {video['missing_reference']} without their reference"
                   + (f", {video['references_changed']} pointed at an older one" if video["references_changed"] else "")
                   + ("; the frames' headers were not read as expected, so frames were not checked for a lost "
                      "reference" if video.get("references_untrusted") else "")
                   + f"; {stats['video_skipped']} video packets never came, {stats['video_late']} came late"
                   + (f"; {stats['video_simulated_lost']} video packets dropped on purpose"
                      if stats["video_simulated_lost"] else "") + ". Controller: "
                   f"{stats['feedback_states']} states and {stats['feedback_history']} button packets sent.")
        audio = self.takion.audio_stats()
        if audio is not None:
            summary += (f" Sound: {audio['frames']} frames of 10 ms, {audio['lost']} lost, {audio['refused']} "
                        "packets refused.")
        if self.decoder is not None:
            calls = self.stats.frames + 1
            summary += (f" Decoded {self.stats.decoded} pictures, {self.stats.decode_errors} errors, "
                        f"{self.stats.decode_seconds / calls * 1000:.1f} ms per frame.")
        return summary

    def close(self) -> None:
        if self.takion is None:
            return
        try:
            self.note(self.video_summary())
            audio = self.takion.audio_stats()
            if audio is not None:                       # the stream's audio packets, counted by the native core
                self.stats.audio_packets += audio["packets"]
                self.stats.haptics_packets += audio["haptics"]
            if self.remote_reason is None:
                self.send(tkproto.disconnect())
        except OSError:
            pass
        finally:
            self.takion.close()
            self.takion = None
