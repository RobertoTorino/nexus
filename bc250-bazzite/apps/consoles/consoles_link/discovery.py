# SPDX-License-Identifier: AGPL-3.0-only
"""Finding consoles and waking them, over UDP.

A search is "SRCH * HTTP/1.1" to port 987 (PS4) or 9302 (PS5), broadcast or to one address; each console answers
with its name, id, state (200: on, 620: in rest mode) and system version. A wake-up is "WAKEUP * HTTP/1.1" to the
same port with the registration key as credential: only a console the board is registered with reacts."""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from typing import Callable

from .httpmsg import ProtocolError, parse_response
from .target import Target, from_system_version

PS4_PORT = 987
PS5_PORT = 9302
PS4_PROTOCOL = "00020020"
PS5_PROTOCOL = "00030010"
LOCAL_PORTS = range(9303, 9320)         # the reference binds the first free one of these, then any port
BROADCAST = "255.255.255.255"

SocketFactory = Callable[[], socket.socket]


def udp_socket() -> socket.socket:
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)


@dataclass(frozen=True)
class Console:
    address: str
    ps5: bool
    state: str                          # "ready", "standby" or "unknown"
    host_name: str = ""
    host_id: str = ""
    host_type: str = ""
    system_version: str = ""
    request_port: int = 0
    running_app: str = ""
    running_title_id: str = ""

    @property
    def target(self) -> Target:
        return from_system_version(self.system_version, self.ps5)

    @property
    def model(self) -> str:
        return self.host_type or ("PS5" if self.ps5 else "PS4")


def srch_packet(ps5: bool) -> bytes:
    protocol = PS5_PROTOCOL if ps5 else PS4_PROTOCOL
    return f"SRCH * HTTP/1.1\ndevice-discovery-protocol-version:{protocol}\n".encode() + b"\0"


def wakeup_packet(credential: int, ps5: bool) -> bytes:
    protocol = PS5_PROTOCOL if ps5 else PS4_PROTOCOL
    return ("WAKEUP * HTTP/1.1\nclient-type:vr\nauth-type:R\nmodel:w\napp-type:r\n"
            f"user-credential:{credential}\ndevice-discovery-protocol-version:{protocol}\n").encode() + b"\0"


def wakeup_credential(regist_key: bytes) -> int:
    """The console's registration key is 8 hex digits as text (sent as hex of that text); the wake-up carries
    their value as a decimal number."""
    text = regist_key.split(b"\0", 1)[0].decode("ascii", errors="replace")
    if not text or len(text) > 8:
        raise ValueError("the registration key is not usable for a wake-up")
    return int(text, 16)


def parse_answer(data: bytes, address: str) -> Console:
    response = parse_response(data)
    state = {200: "ready", 620: "standby"}.get(response.code, "unknown")
    protocol = response.get("device-discovery-protocol-version") or ""
    try:
        request_port = int(response.get("host-request-port") or 0)
    except ValueError:
        request_port = 0
    return Console(address=address, ps5=protocol == PS5_PROTOCOL, state=state,
                   host_name=response.get("host-name") or "", host_id=response.get("host-id") or "",
                   host_type=response.get("host-type") or "", system_version=response.get("system-version") or "",
                   request_port=request_port, running_app=response.get("running-app-name") or "",
                   running_title_id=response.get("running-app-titleid") or "")


def _bind(sock: socket.socket, ports=LOCAL_PORTS) -> None:
    for port in [*ports, 0]:
        try:
            sock.bind(("", port))
            return
        except OSError:
            if port == 0:
                raise


def search(address: str = BROADCAST, timeout: float = 2.0, ps4_port: int = PS4_PORT, ps5_port: int = PS5_PORT,
           make_socket: SocketFactory = udp_socket, local_ports=LOCAL_PORTS) -> list[Console]:
    """Ask for PS4s and PS5s at *address* (the broadcast address, or one console's); every console that answers
    within *timeout*, once each, in the order they answered."""
    found: dict[str, Console] = {}
    with make_socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        _bind(sock, local_ports)
        sock.sendto(srch_packet(False), (address, ps4_port))
        sock.sendto(srch_packet(True), (address, ps5_port))
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            sock.settimeout(remaining)
            try:
                data, (sender, _port) = sock.recvfrom(1024)
            except TimeoutError:
                break
            try:
                console = parse_answer(data, sender)
            except ProtocolError:
                continue                                # another device on the port, or our own broadcast
            key = console.host_id or sender
            if key not in found:
                found[key] = console
    return list(found.values())


def wake(address: str, regist_key: bytes, ps5: bool, port: int | None = None,
         make_socket: SocketFactory = udp_socket) -> None:
    """Send the wake-up to a console in rest mode. It gives no answer; a search a few seconds later shows it on."""
    packet = wakeup_packet(wakeup_credential(regist_key), ps5)
    with make_socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        _bind(sock)
        sock.sendto(packet, (address, port or (PS5_PORT if ps5 else PS4_PORT)))
