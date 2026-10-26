# SPDX-License-Identifier: AGPL-3.0-or-later
"""The console's side of the stream connection on localhost, for the tests: the Takion handshake, BIG (it decrypts
the launch spec to find the handshake key, as a console must), BANG with its own ECDH key, STREAMINFO, then a few
video frames (split into units with FEC units, as a console does) and audio packets, encrypted and signed. The
video is a real clip (video_vectors.json) in the codec the launch spec asked for: its parameter sets as STREAMINFO's
header, its access units as the frames. The sound is a real Opus clip (audio_vectors.json): each packet a new 10 ms
frame and an FEC copy of the one before. It speaks Takion through the native core's packet functions and
records what the board sent."""

from __future__ import annotations

import base64
import json
import re
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import bc250_console_link_core as core

from consoles_link import tkproto
from consoles_link.rpcrypt import RPCrypt
from consoles_link.target import Target

TAG = 0x5eed1e55
CLIPS = json.loads((Path(__file__).parent / "video_vectors.json").read_text(encoding="utf-8"))["clips"]
SOUND = json.loads((Path(__file__).parent / "audio_vectors.json").read_text(encoding="utf-8"))
OPUS = [base64.b64decode(frame) for frame in SOUND["frames"]]
CODEC_OPUS = 5
PARAMETER_SETS = {"h264": {7, 8, 9}, "hevc": {32, 33, 34, 35}}       # with the access unit delimiter
AUDIO_HEADER = tkproto.AudioHeader(2, 16, 48000, 480).save()
UNIT_SIZE = 1000
FEC_UNITS = 2


def clip(codec: str) -> tuple[bytes, list[bytes]]:
    """A clip's header (the first sample's parameter sets) and frames (the samples, the first without them)."""
    samples = [base64.b64decode(sample) for sample in CLIPS[codec]["samples"]]
    first = samples[0]
    for match in re.finditer(rb"\x00\x00\x01", first):
        byte = first[match.end()]
        nal_type = byte & 0x1f if codec == "h264" else (byte >> 1) & 0x3f
        if nal_type not in PARAMETER_SETS[codec]:
            return first[:match.start()], [first[match.start():], *samples[1:]]
    raise ValueError("no slice in the first sample")


def frame_data(frame: int, codec: str = "h264") -> bytes:
    """Frame 1 and on: the clip's frames, again from the start after its end."""
    frames = clip(codec)[1]
    return frames[(frame - 1) % len(frames)]


def video_units(frame: bytes, unit_size: int = UNIT_SIZE, fec_units: int = FEC_UNITS) -> list[bytes]:
    """A frame as the console sends it: source units of its padding size (two bytes) and data, the last one shorter,
    then the FEC units over them padded to the unit size."""
    chunk = unit_size - 2
    parts = [frame[i:i + chunk] for i in range(0, len(frame), chunk)]
    source = b"".join(struct.pack(">H", chunk - len(p)) + p.ljust(chunk, b"\0") for p in parts)
    coded = core.fec_encode(source, unit_size, len(parts), fec_units)
    units = [coded[i * unit_size:(i + 1) * unit_size] for i in range(len(parts) + fec_units)]
    return [unit[:2 + len(part)] for unit, part in zip(units, parts)] + units[len(parts):]


@dataclass
class StreamConsole:
    """target and the session crypto's nonce and RP-Key, to read the launch spec. Behavior switches: silent (no
    INIT_ACK), refuse_version, early_streaminfo (sent before BANG), wrong_signature (BANG's key signed with another
    key), disconnect_after (heartbeats before it sends DISCONNECT). Frames are numbered from 1; lose_units
    (frame, unit) and lose_frames stand in for the network, late_units (frame, unit) for packets that come late."""
    target: Target
    nonce: bytes
    rp_key: bytes
    silent: bool = False
    refuse_version: bool = False
    early_streaminfo: bool = False
    wrong_signature: bool = False
    disconnect_after: int | None = None
    frames: int = 3
    lose_units: set[tuple[int, int]] = field(default_factory=set)
    lose_frames: set[int] = field(default_factory=set)
    late_units: set[tuple[int, int]] = field(default_factory=set)      # sent after the rest of their frame
    big: dict = field(default_factory=dict)
    spec: dict = field(default_factory=dict)
    client_signature_ok: bool | None = None
    received: list[int] = field(default_factory=list)      # message types from the board, in order
    big_fragments: int = 0
    heartbeats: int = 0
    congestion_reports: list[tuple[int, int]] = field(default_factory=list)     # (received, lost)
    feedback_states: list[tuple[int, bytes]] = field(default_factory=list)      # (sequence number, payload)
    feedback_history: list[tuple[int, int, bytes]] = field(default_factory=list)    # (seq. number, events, payload)
    controller_connections: list[dict] = field(default_factory=list)   # CONTROLLERCONNECTION payloads, decoded
    disconnect_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.peer = None
        self.tag_client = 0
        self.seq_num = TAG
        self.key_pos = 0
        self.send_crypt = None
        self.recv_crypt = None
        self.key_state = core.KeyState()
        self.pending = b""
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    @property
    def version(self) -> int:
        return 12 if self.target.ps5 else 9

    def wait_until(self, condition, timeout: float = 2.0) -> bool:
        """For the tests: the console's thread handles what arrives a moment after the board sent it."""
        deadline = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > deadline:
                return False
            time.sleep(0.01)
        return True

    def close(self) -> None:
        self.stopping.set()
        self.thread.join(timeout=5)
        self.sock.close()

    # --- Sending --------------------------------------------------------------------------------------------

    def _send(self, packet: bytes) -> None:
        self.sock.sendto(packet, self.peer)

    def _advance(self, size: int) -> int:
        if self.send_crypt is None:
            return 0
        key_pos = self.key_pos
        self.key_pos += core.key_pos_advance(size)
        return key_pos

    def send_message(self, data: bytes) -> None:
        key_pos = self._advance(len(data))
        packet = core.data_packet(self.tag_client, key_pos, 1, self.seq_num, 1, data)
        self.seq_num += 1
        packet, _mac, _old = core.packet_mac(self.send_crypt, packet, key_pos)
        self._send(packet)

    def send_data(self, data_type: int, data: bytes) -> None:
        """A DATA message of another type than protobuf: 7 rumble, 9 pad info."""
        key_pos = self._advance(len(data))
        packet = bytearray(core.data_packet(self.tag_client, key_pos, 1, self.seq_num, 1, data))
        packet[25] = data_type                      # after the message header, sequence number, channel and 0, 0
        self.seq_num += 1
        packet, _mac, _old = core.packet_mac(self.send_crypt, bytes(packet), key_pos)
        self._send(packet)

    def _ack(self, seq_num: int) -> None:
        key_pos = self._advance(29)
        packet = core.data_ack_packet(self.tag_client, key_pos, seq_num, core.A_RWND)
        self._send(core.packet_mac(self.send_crypt, packet, key_pos)[0])

    def send_av(self, video: bool, packet_index: int, frame_index: int, unit: int, units: int, data: bytes,
                haptics: bool = False, fec: int = 0, codec: int = 0) -> None:
        """For audio, fec is the units field: unit size << 8 | FEC units << 4 | source units."""
        header = bytearray(0x20 if video else 0x18)
        header[0] = core.PACKET_VIDEO if video else core.PACKET_AUDIO
        struct.pack_into(">HHI", header, 1, packet_index, frame_index,
                         (unit << 21 | (units - 1) << 10 | fec) if video else (unit << 24 | (units - 1) << 16 | fec))
        header[9] = codec
        key_pos = self.key_pos
        self.key_pos += core.key_pos_advance(len(data))
        struct.pack_into(">I", header, 0xe, key_pos & 0xffffffff)
        offset = core.parse_av(self.version, bytes(header) + bytes(64), core.KeyState())["data_offset"]
        if haptics and self.version == 12 and not video:
            header[offset - 1] = 0x02
        packet = bytes(header[:offset]) + self.send_crypt.crypt(key_pos + 16, data)
        self._send(core.packet_mac(self.send_crypt, packet, key_pos)[0])

    @property
    def codec(self) -> str:
        return "hevc" if self.spec.get("videoCodec") == "hevc" else "h264"

    def send_audio(self, index: int) -> None:
        """Audio frame *index* (from 1) and an FEC copy of the one before it."""
        new, before = OPUS[(index - 1) % len(OPUS)], OPUS[(index - 2) % len(OPUS)]
        self.send_av(False, index, index, 0, 2, new + before, fec=len(new) << 8 | 1 << 4 | 1, codec=CODEC_OPUS)

    def send_streaminfo(self) -> None:
        resolution = tkproto.uint(1, 1920) + tkproto.uint(2, 1080) + tkproto.blob(3, clip(self.codec)[0])
        payload = tkproto.blob(1, resolution) + tkproto.blob(2, AUDIO_HEADER) + tkproto.uint(3, 100)
        self.send_message(tkproto.message(tkproto.STREAMINFO, tkproto.F_STREAM_INFO, payload))

    # --- Receiving ------------------------------------------------------------------------------------------

    def _recv(self) -> bytes | None:
        try:
            packet, self.peer = self.sock.recvfrom(2048)
        except (TimeoutError, OSError):
            return None
        return packet

    def _handshake(self) -> bool:
        while not self.stopping.is_set():
            packet = self._recv()
            if packet is None:
                continue
            tag = struct.unpack(">I", packet[1:5])[0]       # INIT goes to tag 0, COOKIE to ours
            try:
                if tag not in (0, TAG):
                    raise ValueError("TagMismatch")
                message = core.parse_message(packet[1:], tag, core.KeyState())
            except ValueError as error:
                self.errors.append(f"handshake: {error}")
                continue
            if message["chunk_type"] == core.CHUNK_INIT:
                self.tag_client = struct.unpack(">I", message["payload"][:4])[0]
                if self.silent:
                    continue
                payload = struct.pack(">IIHHI", TAG, core.A_RWND, 0x64, 0x64, TAG) + b"\xc0" * 32
                self._send(core.message_packet(self.tag_client, 0, core.CHUNK_INIT_ACK, 0, payload))
            elif message["chunk_type"] == core.CHUNK_COOKIE:
                self._send(core.message_packet(self.tag_client, 0, core.CHUNK_COOKIE_ACK, 0, b""))
                return True
        return False

    def _read_big(self, data: bytes) -> None:
        found = tkproto.fields(data)
        p = tkproto.fields(found[tkproto.F_BIG][0])
        self.big = {"version": p[1][0], "session_key": p[2][0].decode(), "encrypted_key": p[4][0],
                    "public_key": p[5][0], "signature": p[6][0]}
        # As a console does: the launch spec is the session crypto's key stream XORed with the JSON.
        raw = base64.b64decode(p[3][0])
        stream = RPCrypt.for_session(self.target, self.nonce, self.rp_key).encrypt(0, bytes(len(raw)))
        plain = bytes(a ^ b for a, b in zip(stream, raw))
        self.spec = json.loads(plain.rstrip(b"\0"))
        handshake_key = base64.b64decode(self.spec["handshakeKey"])
        self.client_signature_ok = core.verify_signature(handshake_key, self.big["public_key"], self.big["signature"])

        ecdh = core.Ecdh()
        public_key, signature = ecdh.signed_public_key(bytes(16) if self.wrong_signature else handshake_key)
        accepted = not self.refuse_version
        bang = (tkproto.uint(1, self.version) + tkproto.uint(2, 0) + tkproto.uint(3, 1) + tkproto.uint(4, accepted)
                + tkproto.blob(5, "console") + tkproto.blob(8, public_key) + tkproto.blob(9, signature))
        if self.early_streaminfo:
            self.send_streaminfo()
        self.send_message(tkproto.message(tkproto.BANG, tkproto.F_BANG, bang))
        if not accepted:
            return
        secret = ecdh.derive_secret(self.big["public_key"])
        self.send_crypt = core.GkCrypt(3, handshake_key, secret)
        self.recv_crypt = core.GkCrypt(2, handshake_key, secret)
        if not self.early_streaminfo:
            self.send_streaminfo()

    def _stream(self) -> None:
        packet_index = 0
        for frame in range(1, self.frames + 1):
            units = video_units(frame_data(frame, self.codec))
            late = []
            for unit, data in enumerate(units):
                if (frame, unit) in self.late_units:
                    late.append((packet_index, unit, data))
                elif frame not in self.lose_frames and (frame, unit) not in self.lose_units:
                    self.send_av(True, packet_index, frame, unit, len(units), data, fec=FEC_UNITS)
                packet_index += 1
            for index, unit, data in late:                  # after the frame's others: late, not lost
                time.sleep(0.003)
                self.send_av(True, index, frame, unit, len(units), data, fec=FEC_UNITS)
            self.send_audio(frame)
        if self.version == 12:
            self.send_av(False, self.frames, self.frames, 0, 1, b"haptics", haptics=True)

    def _feedback(self, packet: bytes) -> None:
        """A controller packet: signed with its key position in place, the payload encrypted 16 bytes after it."""
        key_pos = struct.unpack(">I", packet[4:8])[0]
        unsigned = packet[:8] + bytes(4) + packet[12:]
        if self.recv_crypt is None or self.recv_crypt.gmac(key_pos, unsigned) != packet[8:12]:
            self.errors.append("MAC: a controller packet")
            return
        seq_num, count = struct.unpack(">HB", packet[1:4])
        payload = self.recv_crypt.crypt(key_pos + 16, packet[12:])
        if packet[0] == core.PACKET_FEEDBACK_STATE:
            self.feedback_states.append((seq_num, payload))
        else:
            self.feedback_history.append((seq_num, count, payload))

    def _handle(self, packet: bytes) -> None:
        if packet[0] in (core.PACKET_FEEDBACK_STATE, core.PACKET_FEEDBACK_HISTORY):
            self._feedback(packet)
            return
        try:
            core.verify_packet(self.recv_crypt, self.key_state, packet)
        except ValueError as error:
            self.errors.append(f"MAC: {error}")
            return
        if packet[0] == core.PACKET_CONGESTION:
            self.congestion_reports.append(struct.unpack(">HH", packet[3:7]))
            return
        message = core.parse_message(packet[1:], TAG, self.key_state)
        if message["chunk_type"] == core.CHUNK_DATA_ACK:
            return
        payload = message["payload"]
        seq_num = struct.unpack(">I", payload[:4])[0]
        continuing = bool(self.pending)
        data = payload[8:] if continuing else payload[9:]
        self._ack(seq_num)
        if message["chunk_flags"] == 0:                   # more of this message follows
            self.pending += data
            self.big_fragments += 1
            return
        data, self.pending = self.pending + data, b""
        if continuing:
            self.big_fragments += 1
        msg = tkproto.parse(data)
        self.received.append(msg.type)
        if msg.type == tkproto.BIG:
            self._read_big(data)
        elif msg.type == tkproto.CONTROLLERCONNECTION:
            self.controller_connections.append(msg.payload(tkproto.F_CONTROLLER_CONNECTION))
            if len(self.controller_connections) == 1:      # the stream starts with the first controller
                self._stream()
        elif msg.type == tkproto.HEARTBEAT:
            self.heartbeats += 1
            if self.disconnect_after is not None and self.heartbeats >= self.disconnect_after:
                self.send_message(tkproto.disconnect("Server shutting down"))
        elif msg.type == tkproto.DISCONNECT:
            self.disconnect_reason = tkproto.disconnect_reason(msg)

    def _serve(self) -> None:
        if not self._handshake():
            return
        while not self.stopping.is_set():
            packet = self._recv()
            if packet is not None:
                try:
                    self._handle(packet)
                except (ValueError, KeyError, IndexError) as error:
                    self.errors.append(repr(error))


@dataclass
class SenkushaConsole(StreamConsole):
    """The console's side of the network test (Takion version 7, no crypto): it answers the protocol request and
    BIG, echoes pings back as pongs while echo is on and during the MTU out test, sends a video packet of the size
    asked for by an MTU command, and answers the client MTU command. mtu_in_limit and mtu_out_limit stand in for
    the network: larger packets do not arrive. answer_pings and answer_client_mtu switch those answers off."""
    mtu_in_limit: int = 1454
    mtu_out_limit: int = 1454
    answer_pings: bool = True
    answer_client_mtu: bool = True
    echo: bool = False
    pings: int = 0
    mtu_requests: list[int] = field(default_factory=list)
    client_mtu: list[tuple[int, bool, int, int]] = field(default_factory=list)   # id, state, mtu, mtu_down
    video_index: int = 100

    @property
    def version(self) -> int:
        return 7

    def _handle(self, packet: bytes) -> None:
        if packet[0] & 0xf == core.PACKET_AUDIO:                # a ping
            self.pings += 1
            if self.answer_pings and len(packet) + 0x1c <= self.mtu_out_limit:
                self._send(packet)                            # the pong: same frame, unit and tag
            return
        message = core.parse_message(packet[1:], TAG, self.key_state)
        if message["chunk_type"] != core.CHUNK_DATA:
            return
        payload = message["payload"]
        self._ack(struct.unpack(">I", payload[:4])[0])
        msg = tkproto.parse(payload[9:])
        self.received.append(msg.type)
        if msg.type == tkproto.TAKIONPROTOCOLREQUEST:
            self.send_message(tkproto.message(tkproto.TAKIONPROTOCOLREQUESTACK, tkproto.F_PROTOCOL_REQUEST_ACK,
                                              tkproto.uint(1, 9)))
        elif msg.type == tkproto.BIG:
            bang = (tkproto.uint(1, 9) + tkproto.uint(2, 0) + tkproto.uint(3, 1) + tkproto.uint(4, 1)
                    + tkproto.blob(5, ""))
            self.send_message(tkproto.message(tkproto.BANG, tkproto.F_BANG, bang))
        elif msg.type == tkproto.SENKUSHA:
            p = tkproto.fields(msg.payloads[tkproto.F_SENKUSHA][0])
            command = p[1][0]
            if command == tkproto.ECHO_COMMAND:
                self.echo = bool(tkproto.fields(p[tkproto.F_ECHO][0])[1][0])
            elif command == tkproto.MTU_COMMAND:
                c = tkproto.fields(p[tkproto.F_MTU][0])
                request_id, mtu = c[1][0], c[2][0]
                self.mtu_requests.append(mtu)
                if mtu <= self.mtu_in_limit:
                    header = core.v7_av_header(video=True, packet_index=self.video_index, frame_index=request_id)
                    self.video_index += 1
                    self._send(header.ljust(mtu - 0x1c, b"\xaa"))
            elif command == tkproto.CLIENT_MTU_COMMAND:
                c = tkproto.fields(p[tkproto.F_CLIENT_MTU][0])
                values = (c[1][0], bool(c[3][0]), c[2][0], c[4][0])
                self.client_mtu.append(values)
                if values[0] == 1 and self.answer_client_mtu:
                    self.send_message(tkproto.client_mtu_command(*values[:3], values[3]))
        elif msg.type == tkproto.DISCONNECT:
            self.disconnect_reason = tkproto.disconnect_reason(msg)
