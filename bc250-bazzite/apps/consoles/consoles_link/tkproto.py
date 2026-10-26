# SPDX-License-Identifier: AGPL-3.0-only
"""The protobuf messages of the stream connection, written and read
by hand: the few messages the stream needs, encoded field by field as nanopb does in the reference's
streamconnection.c (required fields always, optional ones only when set, in field order).

Every message is a TakionMessage: field 1 is its type, and the payload sits in the field of that type."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

# TakionMessage.PayloadType
BIG, BANG, INFO, HEARTBEAT, PACKETLOSS, CORRUPTFRAME = 0, 1, 2, 3, 4, 5
DISCONNECT, SENKUSHA, STREAMINFO, STREAMINFOACK = 8, 12, 13, 14
CONNECTIONQUALITY, CONTROLLERCONNECTION, IDRREQUEST = 16, 21, 25
TAKIONPROTOCOLREQUEST, TAKIONPROTOCOLREQUESTACK = 31, 32

# The TakionMessage field of each payload.
F_TYPE, F_BIG, F_BANG = 1, 2, 3
F_CORRUPT, F_DISCONNECT, F_SENKUSHA, F_STREAM_INFO, F_CONTROLLER_CONNECTION = 6, 10, 14, 15, 22
F_PROTOCOL_REQUEST, F_PROTOCOL_REQUEST_ACK = 31, 32

# SenkushaPayload.Command, and the payload field of each
ECHO_COMMAND, MTU_COMMAND, CLIENT_MTU_COMMAND = 0, 1, 4
F_ECHO, F_MTU, F_CLIENT_MTU = 2, 3, 5

# ControllerConnectionPayload.ControllerType
DUALSHOCK4, DUALSENSE = 2, 6

VARINT, FIXED64, LENGTH, FIXED32 = 0, 1, 2, 5


class ProtoError(ValueError):
    pass


# --- Writing --------------------------------------------------------------------------------------------------

def _varint(value: int) -> bytes:
    if value < 0:
        value += 1 << 64                       # int32/int64 negatives: ten bytes, as protobuf does
    out = bytearray()
    while True:
        byte = value & 0x7f
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _key(number: int, wire: int) -> bytes:
    return _varint(number << 3 | wire)


def uint(number: int, value: int) -> bytes:
    return _key(number, VARINT) + _varint(int(value))


def blob(number: int, data: bytes | str) -> bytes:
    if isinstance(data, str):
        data = data.encode()
    return _key(number, LENGTH) + _varint(len(data)) + data


def message(msg_type: int, payload_field: int | None = None, payload: bytes = b"") -> bytes:
    out = uint(F_TYPE, msg_type)
    if payload_field is not None:
        out += blob(payload_field, payload)
    return out


def heartbeat() -> bytes:
    return message(HEARTBEAT)


def streaminfo_ack() -> bytes:
    return message(STREAMINFOACK)


def idr_request() -> bytes:
    return message(IDRREQUEST)


def disconnect(reason: str = "Client Disconnecting") -> bytes:
    return message(DISCONNECT, F_DISCONNECT, blob(1, reason))


def corrupt_frame(start: int, end: int) -> bytes:
    return message(CORRUPTFRAME, F_CORRUPT, uint(1, start) + uint(2, end))


def controller_connection(dualsense: bool, controller_id: int | None = None) -> bytes:
    """The controller is connected; the reference sends no controller ID. With one: the several-players
    experiment's second controller."""
    ident = uint(1, controller_id) if controller_id is not None else b""
    return message(CONTROLLERCONNECTION, F_CONTROLLER_CONNECTION,
                   ident + uint(2, 1) + uint(3, DUALSENSE if dualsense else DUALSHOCK4))


def microphone(audio_header: bytes) -> bytes:
    """A STREAMINFO from our side: the microphone's audio header."""
    return message(STREAMINFO, F_STREAM_INFO, blob(2, audio_header))


def big(client_version: int, session_key: str, launch_spec: str, ecdh_public_key: bytes,
        ecdh_signature: bytes) -> bytes:
    """BIG, the client's opening message: the session ID from the control connection, the launch spec and the
    public key for the stream's key exchange. The encrypted key is four zero bytes, as in the reference."""
    payload = (uint(1, client_version) + blob(2, session_key) + blob(3, launch_spec) + blob(4, bytes(4))
               + blob(5, ecdh_public_key) + blob(6, ecdh_signature))
    return message(BIG, F_BIG, payload)


# --- The network test (Senkusha), as the reference's senkusha.c builds them ------------------------------------------

def protocol_request(versions: list[int]) -> bytes:
    """The Takion versions we speak; a repeated field, one entry per version (not packed)."""
    return message(TAKIONPROTOCOLREQUEST, F_PROTOCOL_REQUEST, b"".join(uint(1, v) for v in versions))


def senkusha_big() -> bytes:
    """The network test's BIG: version 9 and empty strings, no key."""
    return message(BIG, F_BIG, uint(1, 9) + blob(2, "") + blob(3, "") + blob(4, b""))


def _senkusha(command: int, number: int, payload: bytes) -> bytes:
    return message(SENKUSHA, F_SENKUSHA, uint(1, command) + blob(number, payload))


def echo_command(state: bool) -> bytes:
    return _senkusha(ECHO_COMMAND, F_ECHO, uint(1, state))


def mtu_command(request_id: int, mtu: int) -> bytes:
    """Asks the console for a video packet of *mtu* bytes (IP and UDP included). The reference sets num = 1 without
    its has-flag, so num is not sent; neither is it here."""
    return _senkusha(MTU_COMMAND, F_MTU, uint(1, request_id) + uint(2, mtu))


def client_mtu_command(request_id: int, state: bool, mtu: int, mtu_down: int) -> bytes:
    return _senkusha(CLIENT_MTU_COMMAND, F_CLIENT_MTU,
                     uint(1, request_id) + uint(2, mtu) + uint(3, state) + uint(4, mtu_down))


# --- Reading --------------------------------------------------------------------------------------------------

def _read_varint(data: bytes, at: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if at >= len(data) or shift > 63:
            raise ProtoError("truncated varint")
        byte = data[at]
        at += 1
        value |= (byte & 0x7f) << shift
        shift += 7
        if not byte & 0x80:
            return value & ((1 << 64) - 1), at


def fields(data: bytes) -> dict[int, list[int | bytes]]:
    """Every field of one message: varints as int, length-delimited fields as bytes, fixed fields as their bytes."""
    out: dict[int, list[int | bytes]] = {}
    at = 0
    while at < len(data):
        key, at = _read_varint(data, at)
        number, wire = key >> 3, key & 7
        if number == 0:
            raise ProtoError("field number 0")
        if wire == VARINT:
            value, at = _read_varint(data, at)
        elif wire == LENGTH:
            size, at = _read_varint(data, at)
            if at + size > len(data):
                raise ProtoError("truncated field")
            value, at = data[at:at + size], at + size
        elif wire in (FIXED64, FIXED32):
            size = 8 if wire == FIXED64 else 4
            if at + size > len(data):
                raise ProtoError("truncated field")
            value, at = data[at:at + size], at + size
        else:
            raise ProtoError(f"wire type {wire}")
        out.setdefault(number, []).append(value)
    return out


def _one(found: dict, number: int, kind: type, default=None):
    values = found.get(number)
    if not values:
        return default
    value = values[-1]                          # protobuf: the last one wins
    if not isinstance(value, kind):
        raise ProtoError(f"field {number} has the wrong type")
    return value


@dataclass
class Message:
    type: int
    payloads: dict[int, list[int | bytes]]

    def payload(self, number: int) -> dict[int, list[int | bytes]] | None:
        raw = _one(self.payloads, number, bytes)
        return None if raw is None else fields(raw)


def parse(data: bytes) -> Message:
    found = fields(data)
    msg_type = _one(found, F_TYPE, int)
    if msg_type is None:
        raise ProtoError("no message type")
    return Message(msg_type, found)


@dataclass
class Bang:
    server_version: int
    token: int
    encrypted_key_accepted: bool
    version_accepted: bool
    session_key: str
    ecdh_public_key: bytes = b""
    ecdh_signature: bytes = b""
    server_version_string: str = ""


def bang(msg: Message) -> Bang | None:
    p = msg.payload(F_BANG)
    if msg.type != BANG or p is None:
        return None
    return Bang(_one(p, 1, int, 0), _one(p, 2, int, 0), bool(_one(p, 3, int, 0)), bool(_one(p, 4, int, 0)),
                _one(p, 5, bytes, b"").decode(errors="replace"), _one(p, 8, bytes, b""), _one(p, 9, bytes, b""),
                _one(p, 7, bytes, b"").decode(errors="replace"))


@dataclass
class Resolution:
    width: int
    height: int
    video_header: bytes


@dataclass
class StreamInfo:
    resolutions: list[Resolution] = field(default_factory=list)
    audio_header: bytes = b""
    start_timeout: int | None = None
    afk_timeout: int | None = None
    afk_timeout_disconnect: int | None = None
    congestion_control_interval: int | None = None


def streaminfo(msg: Message) -> StreamInfo | None:
    p = msg.payload(F_STREAM_INFO)
    if msg.type != STREAMINFO or p is None:
        return None
    info = StreamInfo(audio_header=_one(p, 2, bytes, b""), start_timeout=_one(p, 3, int),
                      afk_timeout=_one(p, 4, int), afk_timeout_disconnect=_one(p, 5, int),
                      congestion_control_interval=_one(p, 6, int))
    for raw in p.get(1, []):
        if not isinstance(raw, bytes):
            raise ProtoError("resolution is not a message")
        r = fields(raw)
        info.resolutions.append(Resolution(_one(r, 1, int, 0), _one(r, 2, int, 0), _one(r, 3, bytes, b"")))
    return info


def disconnect_reason(msg: Message) -> str | None:
    p = msg.payload(F_DISCONNECT)
    if msg.type != DISCONNECT:
        return None
    return "" if p is None else _one(p, 1, bytes, b"").decode(errors="replace")


def protocol_ack(msg: Message) -> int | None:
    """The Takion version the console chose; None when this is no TAKIONPROTOCOLREQUESTACK (0 when it names none)."""
    p = msg.payload(F_PROTOCOL_REQUEST_ACK)
    if msg.type != TAKIONPROTOCOLREQUESTACK or p is None:
        return None
    return _one(p, 1, int, 0)


def senkusha_client_mtu(msg: Message) -> int | None:
    """The request ID of the console's CLIENT_MTU_COMMAND; None for anything else."""
    p = msg.payload(F_SENKUSHA)
    if msg.type != SENKUSHA or p is None or _one(p, 1, int) != CLIENT_MTU_COMMAND:
        return None
    command = _one(p, F_CLIENT_MTU, bytes)
    return None if command is None else _one(fields(command), 1, int, 0)


def corrupt_range(msg: Message) -> tuple[int, int] | None:
    p = msg.payload(F_CORRUPT)
    if msg.type != CORRUPTFRAME or p is None:
        return None
    return _one(p, 1, int, 0), _one(p, 2, int, 0)


# --- The audio header ---------------------------------------------------------------------

AUDIO_HEADER_SIZE = 14


@dataclass
class AudioHeader:
    channels: int
    bits: int
    rate: int
    frame_size: int
    unknown: int = 1

    @classmethod
    def load(cls, data: bytes) -> AudioHeader:
        if len(data) != AUDIO_HEADER_SIZE:
            raise ProtoError(f"the audio header has {len(data)} bytes, not {AUDIO_HEADER_SIZE}")
        rate, frame_size, unknown = struct.unpack(">III", data[2:])
        return cls(data[0], data[1], rate, frame_size, unknown)

    def save(self) -> bytes:
        return bytes([self.channels, self.bits]) + struct.pack(">III", self.rate, self.frame_size, self.unknown)


# What the reference announces for the microphone: mono, 16 bits, 48 kHz, 480 samples (10 ms) per frame. Its
# header save writes bits and channels the other way round from load, and calls set(16, 1, ...), so the
# bytes say one channel of 16 bits in load's order.
MICROPHONE = AudioHeader(channels=1, bits=16, rate=48000, frame_size=480)
