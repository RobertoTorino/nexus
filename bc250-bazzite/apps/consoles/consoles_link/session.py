# SPDX-License-Identifier: AGPL-3.0-only
"""Starting a Remote Play session, on the local network.

1. Session request: GET .../sess/init on TCP 9295 with the registration key; the console answers with a nonce, or
   with the Remote Play version it wants (the request is then repeated with that version).
2. Control connection: GET .../sess/ctrl on TCP 9295 with RP-Auth, RP-Did and the client's OS, each encrypted with
   the session crypto (from the nonce and RP-Key). The console answers with its type and keeps the connection open.
3. Ctrl messages: an 8-byte header (payload size, type) and an encrypted payload, one counter per direction. The
   console sends the session ID, asks for heartbeats and, when the PSN account has one, for its login passcode.

This module ends where the stream (Takion over UDP 9296: video, audio, controller) starts."""

from __future__ import annotations

import base64
import os
import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Callable

from .httpmsg import ProtocolError, parse_response, recv_exactly, recv_header
from .rpcrypt import KEY_SIZE, RPCrypt
from .target import REASON_RP_VERSION, REASON_UNKNOWN, Target, parse_rp_version, reason_text, rp_version

PORT = 9295
TIMEOUT = 5.0
SESSION_ID_TIMEOUT = 10.0
STOP_CHECK = 0.25                       # how often keep_alive looks at its stop condition
MAX_MESSAGE = 0x10000                   # the reference's buffer is smaller; anything larger is not a ctrl message
OS_TYPE = "Win10.0.0"
DID_PREFIX = bytes([0x00, 0x18, 0x00, 0x00, 0x00, 0x07, 0x00, 0x40, 0x00, 0x80])
DID_SUFFIX = bytes(6)
DID_SIZE = 32
SERVER_TYPES = {0: "PS4", 1: "PS4 Pro", 2: "PS5"}
STREAMING_TYPES = {"h264": 1, "h265": 2, "h265_hdr": 3}

# Ctrl message types.
SESSION_ID = 0x33
INVALID_SESSION_ID = b"InvalidSessionId"     # what a PS4 Pro sent instead of an ID (owner's board, 12-10-2026)
HEARTBEAT_REQ = 0xfe
HEARTBEAT_REP = 0x1fe
LOGIN_PIN_REQ = 0x4
LOGIN_PIN_REP = 0x8004
LOGIN = 0x5
GOTO_BED = 0x50
MIC_TOGGLE = 0x36
DISPLAY_DEVICES = 0x910


class SessionError(Exception):
    """The session did not start; the text says why, for the window."""


class VersionMismatch(SessionError):
    def __init__(self, server: Target):
        super().__init__(f"The console wants Remote Play version {rp_version(server) or 'unknown'}.")
        self.server = server


def _paths(target: Target) -> tuple[str, str]:
    if target in (Target.PS4_8, Target.PS4_9):
        return "/sce/rp/session", "/sce/rp/session/ctrl"
    if target.ps5:
        return "/sie/ps5/rp/sess/init", "/sie/ps5/rp/sess/ctrl"
    return "/sie/ps4/rp/sess/init", "/sie/ps4/rp/sess/ctrl"


def regist_key_hex(regist_key: bytes) -> str:
    return regist_key.split(b"\0", 1)[0].hex()


def frame(msg_type: int, payload: bytes) -> bytes:
    return struct.pack(">IHH", len(payload), msg_type, 0) + payload


def new_did(random: Callable[[int], bytes] = os.urandom) -> bytes:
    return DID_PREFIX + random(DID_SIZE - len(DID_PREFIX) - len(DID_SUFFIX)) + DID_SUFFIX


@dataclass
class SessionInfo:
    target: Target
    server_type: str = ""
    session_id: str = ""
    network: str = ""                   # the network test before a stream, for the window ("" without one)
    log: list[str] = field(default_factory=list)


class Session:
    """One session with a registered console. Use as a context manager; closing it ends the session."""

    def __init__(self, host: str, target: Target, regist_key: bytes, rp_key: bytes, login_pin: str = "",
                 port: int = PORT, timeout: float = TIMEOUT, codec: str = "h264",
                 random: Callable[[int], bytes] = os.urandom):
        if len(rp_key) != KEY_SIZE:
            raise ValueError("RP-Key has 16 bytes")
        self.host, self.port, self.timeout = host, port, timeout
        self.regist_key, self.rp_key, self.login_pin, self.codec = regist_key, rp_key, login_pin, codec
        self.random = random
        self.info = SessionInfo(target)
        self.crypt: RPCrypt | None = None
        self.sock: socket.socket | None = None
        self.counter_local = 0
        self.counter_remote = 0
        self.buffer = b""
        self.login_pin_sent = False

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def note(self, text: str) -> None:
        self.info.log.append(text)

    # --- 1. Session request ---------------------------------------------------------------------------------

    def _request_once(self, target: Target) -> bytes:
        version = rp_version(target)
        if version is None:
            raise SessionError("The console's Remote Play version is unknown; register the board again.")
        init_path, _ctrl = _paths(target)
        request = (f"GET {init_path} HTTP/1.1\r\nHost: {self.host}:{self.port}\r\nUser-Agent: remoteplay Windows\r\n"
                   f"Connection: close\r\nContent-Length: 0\r\nRP-Registkey: {regist_key_hex(self.regist_key)}\r\n"
                   f"Rp-Version: {version}\r\n\r\n").encode()
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.sendall(request)
            header, _rest = recv_header(sock, self.timeout)
        response = parse_response(header)
        nonce_text = response.get("RP-Nonce")
        if response.code == 200 and nonce_text:
            try:
                nonce = base64.b64decode(nonce_text, validate=True)
            except ValueError:
                nonce = b""
            if len(nonce) != KEY_SIZE:
                raise SessionError("The console sent an invalid nonce.")
            return nonce
        try:
            reason = int(response.get("RP-Application-Reason") or "0", 16)
        except ValueError:
            reason = 0
        server_version = response.get("RP-Version", ignore_case=True)
        if reason in (REASON_RP_VERSION, REASON_UNKNOWN) and server_version and server_version != version:
            server = parse_rp_version(server_version, target.ps5)
            if server.unknown and server_version == "5.0":
                server = Target.PS4_9          # the reference: a PS4 that says 5.0 means 9.0
            raise VersionMismatch(server)
        if reason == REASON_RP_VERSION:
            raise VersionMismatch(Target.PS5_UNKNOWN if target.ps5 else Target.PS4_UNKNOWN)
        raise SessionError(f"The console refused the session: {reason_text(reason) if reason else f'HTTP {response.code}'}.")

    def request(self) -> bytes:
        """Ask the console for a session; switches to the console's Remote Play version when it asks for another."""
        target = self.info.target
        for _attempt in range(3):
            try:
                nonce = self._request_once(target)
            except VersionMismatch as mismatch:
                if mismatch.server.unknown or mismatch.server == target:
                    raise
                self.note(f"The console wants Remote Play {rp_version(mismatch.server)}; asking again with it.")
                target = mismatch.server
                continue
            except (OSError, ProtocolError) as error:
                raise SessionError(f"No session with {self.host}: {error}. Is the console on (not in rest mode)?") \
                    from error
            self.info.target = target
            self.note(f"Session request accepted (Remote Play {rp_version(target)}).")
            return nonce
        raise SessionError("The console kept asking for another Remote Play version.")

    # --- 2. Control connection ------------------------------------------------------------------------------

    def _encrypt_b64(self, data: bytes) -> str:
        encrypted = self.crypt.encrypt(self.counter_local, data)
        self.counter_local += 1
        return base64.b64encode(encrypted).decode()

    def open_ctrl(self, nonce: bytes) -> None:
        target = self.info.target
        self.crypt = RPCrypt.for_session(target, nonce, self.rp_key)
        self.counter_local = self.counter_remote = 0
        time.sleep(0.01)                                # the reference: the PS4 does not always react right away
        auth = self._encrypt_b64(self.regist_key.ljust(KEY_SIZE, b"\0")[:KEY_SIZE])
        did = self._encrypt_b64(new_did(self.random))
        os_type = self._encrypt_b64(OS_TYPE.encode() + b"\0")
        extra = ""
        if target >= Target.PS4_10:
            extra += f"RP-StartBitrate: {self._encrypt_b64(bytes(4))}\r\n"
        if target.ps5:
            extra += f"RP-StreamingType: {self._encrypt_b64(STREAMING_TYPES[self.codec].to_bytes(4, 'little'))}\r\n"
        _init, ctrl_path = _paths(target)
        request = (f"GET {ctrl_path} HTTP/1.1\r\nHost: {self.host}:{self.port}\r\nUser-Agent: remoteplay Windows\r\n"
                   f"Connection: keep-alive\r\nContent-Length: 0\r\nRP-Auth: {auth}\r\n"
                   f"RP-Version: {rp_version(target) or ''}\r\nRP-Did: {did}\r\nRP-ControllerType: 3\r\n"
                   f"RP-ClientType: 11\r\nRP-OSType: {os_type}\r\nRP-ConPath: 1\r\n{extra}\r\n").encode()
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            self.sock.sendall(request)
            header, rest = recv_header(self.sock, self.timeout)
            response = parse_response(header)
        except (OSError, ProtocolError) as error:
            self.close()
            raise SessionError(f"The control connection to {self.host} failed: {error}.") from error
        if response.code != 200:
            self.close()
            raise SessionError(f"The console refused the control connection (HTTP {response.code}).")
        server_type = response.get("RP-Server-Type")
        if server_type:
            try:
                raw = base64.b64decode(server_type)
            except ValueError:
                raw = b""
            if len(raw) == KEY_SIZE:
                decrypted = self.crypt.decrypt(self.counter_remote, raw)
                self.counter_remote += 1
                self.info.server_type = SERVER_TYPES.get(decrypted[0], f"type {decrypted[0]}")
        if response.get("RP-Prohibit") == "1":
            self.note("The console says the current screen may not be streamed.")
        self.buffer = rest
        self.note(f"Control connection open ({self.info.server_type or 'console type not reported'}).")

    # --- 3. Ctrl messages -----------------------------------------------------------------------------------

    def send(self, msg_type: int, payload: bytes = b"") -> None:
        if payload:
            payload = self.crypt.encrypt(self.counter_local, payload)
            self.counter_local += 1
        self.sock.sendall(frame(msg_type, payload))

    def receive(self, timeout: float) -> tuple[int, bytes] | None:
        """The next ctrl message, decrypted; None when nothing came within *timeout*."""
        deadline = time.monotonic() + timeout
        while len(self.buffer) < 8 or len(self.buffer) < 8 + struct.unpack(">I", self.buffer[:4])[0]:
            if len(self.buffer) >= 8 and struct.unpack(">I", self.buffer[:4])[0] > MAX_MESSAGE:
                raise SessionError("The console sent a control message that is too large.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self.sock.settimeout(remaining)
            try:
                chunk = self.sock.recv(4096)
            except TimeoutError:
                return None
            if not chunk:
                raise SessionError("The console closed the control connection.")
            self.buffer += chunk
        size, msg_type, _zero = struct.unpack(">IHH", self.buffer[:8])
        payload, self.buffer = self.buffer[8:8 + size], self.buffer[8 + size:]
        if payload:
            payload = self.crypt.decrypt(self.counter_remote, payload)
            self.counter_remote += 1
        return msg_type, payload

    def handle(self, msg_type: int, payload: bytes) -> None:
        if msg_type == HEARTBEAT_REQ:
            self.send(HEARTBEAT_REP)
        elif msg_type == SESSION_ID:
            # The first byte is the ID's length (a normal one has 74 characters, 0x4a); the reference skips it.
            text = payload[1:]
            if payload[:1] and payload[0] != len(text):
                self.note(f"The session ID message says {payload[0]} characters but has {len(text)}.")
            if 24 <= len(text) < 79 and text.isascii() and text.isalnum():
                self.info.session_id = text.decode()
            else:                                       # the reference then makes one up: time and random bytes
                self.info.session_id = f"{int(time.monotonic())}{base64.b64encode(self.random(48)).decode()}"
                if text == INVALID_SESSION_ID:
                    self.note("The console sent no session ID (\"InvalidSessionId\"); using a made-up one, which "
                              "the console accepts for the stream.")
                else:
                    self.note(f"The console sent an unusual session ID ({len(payload)} bytes: "
                              f"{payload[:48].hex(' ')}{' …' if len(payload) > 48 else ''}); using a made-up one.")
            self.enable_features()
        elif msg_type == LOGIN_PIN_REQ:
            if not self.login_pin:
                raise SessionError("The console asks for the PSN account's login passcode. Enter it in the "
                                   "console's settings in this app and try again.")
            if self.login_pin_sent:
                raise SessionError("The console did not accept the login passcode.")
            self.send(LOGIN_PIN_REP, self.login_pin.encode())
            self.login_pin_sent = True
            self.note("The console asked for the login passcode; sent.")
        elif msg_type == LOGIN and payload[:1] == b"\x01":
            raise SessionError("The console did not accept the login passcode.")

    def enable_features(self) -> None:
        """What the reference sends once the session ID is there: the microphone off (twice, as it does) and no
        extra display devices."""
        self.send(MIC_TOGGLE, bytes([0, 1, 1, 89]))
        self.send(MIC_TOGGLE, bytes([0, 1, 1, 89]))
        self.send(DISPLAY_DEVICES, bytes(4))

    def wait_session_id(self, timeout: float = SESSION_ID_TIMEOUT) -> str:
        deadline = time.monotonic() + timeout
        while not self.info.session_id:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SessionError("The console opened the control connection but sent no session ID.")
            message = self.receive(remaining)
            if message is not None:
                self.handle(*message)
        self.note("Session ID received: the session is running.")
        return self.info.session_id

    def keep_alive(self, seconds: float, stop: Callable[[], bool] = lambda: False) -> None:
        """Answer the console's heartbeats for *seconds*, as a running session does, or until *stop* says so."""
        deadline = time.monotonic() + seconds
        while (remaining := deadline - time.monotonic()) > 0 and not stop():
            message = self.receive(min(remaining, STOP_CHECK))
            if message is not None:
                self.handle(*message)

    def goto_bed(self) -> None:
        self.send(GOTO_BED)
        self.note("Asked the console to go to rest mode.")

    def start(self) -> SessionInfo:
        self.open_ctrl(self.request())
        self.wait_session_id()
        return self.info

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None
