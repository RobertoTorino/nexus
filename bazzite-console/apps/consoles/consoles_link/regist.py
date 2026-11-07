# SPDX-License-Identifier: AGPL-3.0-only
"""Registering the board with a console, on the local network.

The console shows an 8-digit PIN: a PS5 under Settings > System > Remote Play > Link Device, a PS4 under
Settings > Remote Play Connection Settings > Add Device. The board says "SRC2"/"SRC3"
on UDP port 9295 until the console answers "RES2"/"RES3", then POSTs a 0x1e0-byte block with the crypto seeds and
the PSN account ID, encrypted with a key mixed from a table and the PIN. The console answers with the keys the
board keeps: the registration key (for sessions and wake-ups) and RP-Key (the "morning" of the session crypto)."""

from __future__ import annotations

import base64
import os
import socket
import time
from dataclasses import dataclass
from typing import Callable

from .httpmsg import ProtocolError, parse_headers, parse_response, recv_exactly, recv_header
from .rpcrypt import KEY_SIZE, RPCrypt, aeropause
from .target import Target, reason_text, rp_version

PORT = 9295
TIMEOUT = 3.0
SEARCH_PAUSE = 0.1                      # the reference: the PS4 does not take the request right after answering
CLIENT_TYPE = "dabfa2ec873de5839bee8d3f4c0239c4282c07c25c6077a2931afcf0adc0d34f"
INNER_OFFSET = 0x1e0
LOCAL_ADDRESS = "10.0.2.15"             # the reference sends this fixed address in the Host header on the local network


class RegistError(Exception):
    """Registration did not succeed; the text says why, for the window."""


@dataclass(frozen=True)
class Registration:
    """What the console hands out on registration; the board needs regist_key and rp_key for every session."""
    target: Target
    nickname: str
    mac: bytes
    regist_key: bytes                   # up to 16 bytes, as the console sent it (8 hex digits as text)
    rp_key: bytes                       # 16 bytes
    rp_key_type: int = 0


def path(target: Target) -> str:
    if target.ps5:
        return "/sie/ps5/rp/sess/rgst"
    if target in (Target.PS4_8, Target.PS4_9):
        return "/sce/rp/regist"
    return "/sie/ps4/rp/sess/rgst"


def build_payload(target: Target, ambassador: bytes, account_id: bytes, pin: int) -> tuple[bytes, RPCrypt]:
    """The request body and the crypto that also decrypts the answer. The first 0x1e0 bytes may be anything
    (the reference: 'A'); the seeds sit at fixed places in it and two of its bytes choose the table rows."""
    if len(account_id) != 8:
        raise ValueError("the PSN account ID has 8 bytes")
    buf = bytearray(b"A" * INNER_OFFSET)
    if target.pre10:
        crypt = RPCrypt.for_regist(target, ambassador, 0, pin)
        buf[0x11c:0x11c + KEY_SIZE] = aeropause(target, 0, crypt.ambassador)
        client_type = "Windows"
    else:
        key_0_off = buf[0x18d] & 0x1f
        key_1_off = buf[0] >> 3
        crypt = RPCrypt.for_regist(target, ambassador, key_0_off, pin)
        seed = aeropause(target, key_1_off, crypt.ambassador)
        buf[0xc7:0xc7 + 8] = seed[8:]
        buf[0x191:0x191 + 8] = seed[:8]
        client_type = CLIENT_TYPE
    inner = f"Client-Type: {client_type}\r\nNp-AccountId: {base64.b64encode(account_id).decode()}\r\n".encode()
    return bytes(buf) + crypt.encrypt(0, inner), crypt


def request_header(target: Target, payload_size: int, local_address: str = LOCAL_ADDRESS) -> bytes:
    # The doubled " HTTP/1.1" is in the reference's request and the consoles accept it; kept as sent there.
    header = (f"POST {path(target)} HTTP/1.1\r\n HTTP/1.1\r\nHOST: {local_address}\r\n"
              f"User-Agent: remoteplay Windows\r\nConnection: close\r\nContent-Length: {payload_size}\r\n")
    if target >= Target.PS4_9 and rp_version(target):
        header += f"RP-Version: {rp_version(target)}\r\n"
    return (header + "\r\n").encode()


def parse_answer(target: Target, body: bytes) -> Registration:
    headers = dict(parse_headers(body.split(b"\0", 1)[0].decode("utf-8", errors="replace")))
    prefix = "PS5" if target.ps5 else "PS4"

    def hex_field(key: str, size: int, exact: bool) -> bytes:
        try:
            value = bytes.fromhex(headers.get(key, ""))
        except ValueError:
            value = b""
        if not value or len(value) > size or (exact and len(value) != size):
            raise RegistError(f"The console's answer has no valid {key}.")
        return value

    regist_key = hex_field(f"{prefix}-RegistKey", 16, exact=False)
    rp_key = hex_field("RP-Key", 16, exact=True)
    mac = hex_field(f"{prefix}-Mac", 6, exact=True)
    try:
        key_type = int(headers.get("RP-KeyType", "0"), 0)
    except ValueError:
        key_type = 0
    return Registration(target=target, nickname=headers.get(f"{prefix}-Nickname", ""), mac=mac,
                        regist_key=regist_key, rp_key=rp_key, rp_key_type=key_type)


def _search(host: str, target: Target, port: int, timeout: float) -> str:
    """SRC2/SRC3 until the console answers RES2/RES3; returns the address that answered."""
    ask, answer = (b"SRC3", b"RES3") if target.ps5 else (b"SRC2", b"RES2")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((host, port))
        sock.send(ask + b"\0")
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            sock.settimeout(remaining)
            try:
                data, (sender, _port) = sock.recvfrom(256)
            except TimeoutError:
                break
            except ConnectionRefusedError:
                raise RegistError(f"Nothing listens for registration on {host}. Is it a PS4 or PS5 that is "
                                  "switched on (not in rest mode)?") from None
            if data.startswith(answer):
                return sender
    raise RegistError(f"No answer from {host}. Show the PIN on the console first (PS5: Link Device; PS4: Add "
                      "Device), and check that the board and the console are on the same network.")


def register(host: str, target: Target, account_id: bytes, pin: int, port: int = PORT, timeout: float = TIMEOUT,
             random: Callable[[int], bytes] = os.urandom, pause: float = SEARCH_PAUSE) -> Registration:
    """Register with the console at *host* while it shows *pin* (Link Device on a PS5, Add Device on a PS4)."""
    payload, crypt = build_payload(target, random(KEY_SIZE), account_id, pin)
    address = _search(host, target, port, timeout)
    time.sleep(pause)
    try:
        with socket.create_connection((address, port), timeout=timeout) as sock:
            sock.sendall(request_header(target, len(payload)) + payload)
            header, rest = recv_header(sock, timeout)
            response = parse_response(header)
            if response.code != 200:
                reason = response.get("RP-Application-Reason")
                why = reason_text(int(reason, 16)) if reason else f"HTTP {response.code}"
                raise RegistError(f"The console refused the registration: {why}.")
            try:
                size = int(response.get("Content-Length") or 0)
            except ValueError:
                size = 0
            if size <= 0:
                raise RegistError("The console's answer has no content.")
            body = rest[:size] + recv_exactly(sock, max(0, size - len(rest)), timeout)
    except (OSError, ProtocolError) as error:
        raise RegistError(f"Registration with {host} failed: {error}.") from error
    return parse_answer(target, crypt.decrypt(0, body))
