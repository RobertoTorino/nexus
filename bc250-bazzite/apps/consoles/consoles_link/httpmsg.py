# SPDX-License-Identifier: AGPL-3.0-only
"""The HTTP-like messages of Remote Play: discovery answers, the registration and session responses and the
headers inside the registration payload. Parsed the way the reference's lib/src/http.c does: lines end at \\r or \\n,
"Key: value", keys compared as sent."""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field

MAX_HEADER = 4096


class ProtocolError(Exception):
    """The console answered something this app cannot read."""


@dataclass
class Response:
    code: int
    headers: list[tuple[str, str]] = field(default_factory=list)

    def get(self, key: str, ignore_case: bool = False) -> str | None:
        for name, value in self.headers:
            if name == key or (ignore_case and name.lower() == key.lower()):
                return value
        return None


def parse_headers(text: str) -> list[tuple[str, str]]:
    headers = []
    for line in text.replace("\r", "\n").split("\n"):
        line = line.rstrip("\0")
        if not line:
            continue
        key, sep, value = line.partition(":")
        if not sep or not key:
            raise ProtocolError(f"not a header line: {line!r}")
        value = value[1:] if value.startswith(" ") else value
        if not value:
            raise ProtocolError(f"empty header value: {key}")
        headers.append((key, value))
    return headers


def parse_response(data: bytes) -> Response:
    text = data.split(b"\0", 1)[0].decode("utf-8", errors="replace")
    if not text.startswith("HTTP/1.1 "):
        raise ProtocolError("not an HTTP/1.1 response")
    status, _sep, rest = text[9:].partition("\n")
    try:
        code = int(status.strip().split(" ", 1)[0])
    except ValueError:
        raise ProtocolError(f"no status code in {status!r}") from None
    return Response(code, parse_headers(rest))


def recv_header(sock: socket.socket, timeout: float) -> tuple[bytes, bytes]:
    """Read up to the blank line that ends the header; returns the header and whatever came after it."""
    deadline = time.monotonic() + timeout
    data = b""
    while b"\r\n\r\n" not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("the console did not answer in time")
        sock.settimeout(remaining)
        chunk = sock.recv(1024)
        if not chunk:
            raise ProtocolError("the console closed the connection")
        data += chunk
        if len(data) > MAX_HEADER:
            raise ProtocolError("the console's answer is too long")
    end = data.index(b"\r\n\r\n") + 4
    return data[:end], data[end:]


def recv_exactly(sock: socket.socket, size: int, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    data = b""
    while len(data) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("the console did not send everything in time")
        sock.settimeout(remaining)
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ProtocolError("the console closed the connection")
        data += chunk
    return data
