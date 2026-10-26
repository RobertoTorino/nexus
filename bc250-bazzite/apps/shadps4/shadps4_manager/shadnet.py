# SPDX-License-Identifier: GPL-3.0-or-later
"""shadNet, shadPS4's online service (github.com/shadps4-emu/shadNet): creating an account on a shadNet server and
trying a sign-in, as shadPS4 0.20.0's own client speaks to it (src/shadnet/client.cpp, shadnet.proto at that tag).

shadPS4 signs in by itself when a game starts, with what its own files say (userdata.py): shadNet switched on, and
for the user an NPID (the account's name) and password. It has no way to create an account; this does.

The protocol, over plain TCP (no encryption: the password goes over the network as it is): the server first sends
ServerInfo (packet type 3, a u32 protocol version, 1). A request is a 15-byte header (packet type u8 0, command u16,
total size u32 with the header, packet number u64; little-endian), then a u32 size and a protobuf message. The reply
(packet type 1, same command and number) starts with an error code u8 (0: none). The messages used here have only
text fields, so they are encoded here; no protobuf library is needed.

Whether shadPS4 is signed in right now only shadPS4 knows; while it runs, its log says so (client.cpp: "Logged in
npid='...'", "Login rejected error code N", and a line when the connection drops)."""

from __future__ import annotations

import re
import socket
import struct
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SERVER = "srv.shadps4.net:31313"        # shadPS4 0.20.0's own default (emulator_settings.h)
PROTOCOL = 1
HEADER = struct.Struct("<BHIQ")                 # packet type, command, total size, packet number
REQUEST, REPLY, NOTIFICATION, SERVER_INFO = 0, 1, 2, 3
LOGIN, CREATE = 0, 2
TIMEOUT = 10                                    # seconds, as shadPS4's connect timeout
MAX_PACKET = 1 << 20
NPID = re.compile(r"^[A-Za-z0-9_-]{3,16}$")     # the server's rule (shadNet README): 3 to 16 of these

# The error codes of shadnet.proto's ErrorType that these two requests can get, as the person using the app needs
# to read them.
ERRORS = {
    1: "the server did not understand the request (another shadNet version?)",
    2: "the server refused the request as invalid",
    3: "the name, password or email is not accepted by the server",
    4: "too many attempts: wait a little and try again",
    5: "the sign-in failed on the server",
    6: "this account is signed in already, elsewhere (a running shadPS4?)",
    7: "there is no account with this name (names are case-sensitive)",
    8: "the password is wrong",
    9: "the server wants a validation token for this account",
    10: "the server could not create the account",
    11: "this name is taken: choose another",
    12: "the server does not accept email addresses of this provider",
    13: "an account with this email address exists already",
    23: "this server needs a registration key to create an account: ask whoever runs it",
    24: "the server's database failed: try again later",
}

Connect = Callable[[tuple[str, int], float], socket.socket]


class ShadNetError(Exception):
    pass


@dataclass(frozen=True)
class Server:
    host: str
    port: int

    def __str__(self) -> str:
        return f"{self.host}:{self.port}"


def parse_server(text: str) -> Server:
    """"host:port" (as shadPS4 keeps it); the port defaults to shadNet's 31313."""
    text = text.strip()
    host, _, port = text.rpartition(":") if ":" in text else (text, "", "31313")
    if not host or not port.isdigit() or not 0 < int(port) < 65536 or any(c.isspace() for c in host):
        raise ShadNetError(f"{text!r} is not a server address like {DEFAULT_SERVER}.")
    return Server(host, int(port))


def check_npid(npid: str) -> str:
    """"" when the server takes it as a name, else why not."""
    if not NPID.match(npid):
        return "A shadNet name has 3 to 16 letters, digits, - or _ (no spaces)."
    return ""


def _text_fields(fields: dict[int, str]) -> bytes:
    """A protobuf message with only text fields (wire type 2), the empty ones left out as protobuf does."""
    out = b""
    for number, value in fields.items():
        data = value.encode()
        if not data:
            continue
        out += _varint(number << 3 | 2) + _varint(len(data)) + data
    return out


def _varint(value: int) -> bytes:
    out = b""
    while True:
        byte, value = value & 0x7F, value >> 7
        if value:
            out += bytes([byte | 0x80])
        else:
            return out + bytes([byte])


def packet(command: int, number: int, message: bytes) -> bytes:
    payload = struct.pack("<I", len(message)) + message
    return HEADER.pack(REQUEST, command, HEADER.size + len(payload), number) + payload


def _receive(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ShadNetError("the server closed the connection.")
        data += chunk
    return data


def _read_packet(sock: socket.socket) -> tuple[int, int, int, bytes]:
    kind, command, total, number = HEADER.unpack(_receive(sock, HEADER.size))
    if not HEADER.size <= total <= MAX_PACKET:
        raise ShadNetError("the server sent something that is not shadNet.")
    return kind, command, number, _receive(sock, total - HEADER.size)


def _connect(address: tuple[str, int], timeout: float) -> socket.socket:
    return socket.create_connection(address, timeout=timeout)


def _greeting(sock: socket.socket, server: Server) -> None:
    """The server's ServerInfo, as shadPS4 checks it before anything else."""
    kind, _command, _number, info = _read_packet(sock)
    if kind != SERVER_INFO:
        raise ShadNetError(f"{server} is not a shadNet server.")
    if len(info) >= 4 and struct.unpack_from("<I", info)[0] != PROTOCOL:
        raise ShadNetError(f"{server} speaks another shadNet version than shadPS4 0.20.0 "
                           f"({struct.unpack_from('<I', info)[0]}, not {PROTOCOL}).")


@contextmanager
def _connection(server: Server, connect: Connect):
    """A connection that has the server's greeting; network errors as ShadNetError with the reason."""
    try:
        with connect((server.host, server.port), TIMEOUT) as sock:
            sock.settimeout(TIMEOUT)
            _greeting(sock, server)
            yield sock
    except socket.timeout as error:
        raise ShadNetError(f"{server} did not answer in {TIMEOUT} s.") from error
    except OSError as error:
        reason = getattr(error, "strerror", None) or str(error)
        raise ShadNetError(f"{server} could not be reached: {reason}.") from error


def server_answers(server: Server, connect: Connect = _connect) -> None:
    """Whether the server answers as shadNet 1, without signing in (shadPS4's own probe, server_probe.cpp).
    ShadNetError with the reason when it does not."""
    with _connection(server, connect):
        pass


def request(server: Server, command: int, message: bytes, connect: Connect = _connect) -> int:
    """Sends one request and returns the error code of its reply (0: none). Notifications the server sends in
    between are passed over. ShadNetError when the server cannot be reached or does not speak shadNet 1."""
    with _connection(server, connect) as sock:
        sock.sendall(packet(command, 1, message))
        while True:
            kind, answer, number, payload = _read_packet(sock)
            if kind == REPLY and answer == command and number == 1:
                if not payload:
                    raise ShadNetError("the server's answer was empty.")
                return payload[0]


def explain(error: int) -> str:
    return ERRORS.get(error, f"the server answered with error {error}")


def create_account(server: Server, npid: str, password: str, email: str, key: str = "",
                   connect: Connect = _connect) -> None:
    """A new account (RegistrationRequest: npid, password, avatar_url left to the server, email, secret_key).
    ShadNetError with the reason when the server refuses it."""
    message = _text_fields({1: npid, 2: password, 4: email, 5: key})
    error = request(server, CREATE, message, connect)
    if error:
        raise ShadNetError(f"The account was not created: {explain(error)}.")


def try_sign_in(server: Server, npid: str, password: str, connect: Connect = _connect) -> None:
    """Signs in (LoginRequest: npid, password) as shadPS4 would, and closes the connection, which signs out again.
    ShadNetError with the reason when it fails."""
    error = request(server, LOGIN, _text_fields({1: npid, 2: password}), connect)
    if error:
        raise ShadNetError(f"The sign-in failed: {explain(error)}.")


LOGGED_IN = re.compile(r"Logged in npid='([^']*)'")
REJECTED = re.compile(r"Login rejected error code (\d+)")
DROPPED = ("Reader header recv failed", "connect() timed out or failed")
LOG_TAIL = 4 << 20                      # the last 4 MB of a log: a session's sign-in is near its start


def session(log_folder: Path) -> tuple[str, str]:
    """What shadPS4's newest log says about its shadNet session: ("online", name), ("offline", why) or ("", "")
    when it has not signed in or tried yet."""
    try:
        newest = max((p for p in log_folder.glob("*.log") if p.is_file()), key=lambda p: p.stat().st_mtime)
        with newest.open("rb") as log:
            log.seek(max(0, newest.stat().st_size - LOG_TAIL))
            text = log.read().decode("utf-8", "replace")
    except (OSError, ValueError):
        return "", ""
    state = ("", "")
    for line in text.splitlines():
        if "ShadNet" not in line:
            continue
        if match := LOGGED_IN.search(line):
            state = ("online", match.group(1))
        elif match := REJECTED.search(line):
            state = ("offline", f"shadPS4's sign-in was refused: {explain(int(match.group(1)))}")
        elif any(text in line for text in DROPPED):
            state = ("offline", "shadPS4 lost the connection to the server")
    return state
