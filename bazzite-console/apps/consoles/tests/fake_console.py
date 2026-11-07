# SPDX-License-Identifier: AGPL-3.0-or-later
"""A console on localhost for the tests: the console's side of discovery, registration and the control connection,
with the same crypto. It checks what the board sends (paths, keys, counters) and records it, so a test can assert
both what the app shows and what reached the console."""

from __future__ import annotations

import base64
import socket
import struct
import threading
from dataclasses import dataclass, field

from consoles_link import rpcrypt, session
from consoles_link.httpmsg import parse_headers
from consoles_link.target import Target

AMBASSADOR = bytes(range(16))           # the tests' "random" for registration
NONCE = bytes(range(100, 116))
REGIST_KEY = b"1a2b3c4d"                # as consoles send it: 8 hex digits as text
RP_KEY = bytes(range(0x40, 0x50))
MAC = bytes.fromhex("0cfe45a1b2c3")
SESSION_ID = b"\x4a" + b"Ab1" * 24 + b"Xy"   # the length byte, then 74 characters as a console sends


def free_port() -> int:
    """A port number free for both TCP and UDP on localhost (registration uses both on one port)."""
    for _attempt in range(50):
        with socket.socket() as tcp:
            tcp.bind(("127.0.0.1", 0))
            port = tcp.getsockname()[1]
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                try:
                    udp.bind(("127.0.0.1", port))
                except OSError:
                    continue
            return port
    raise RuntimeError("no free port")


def _read_request(conn: socket.socket) -> tuple[str, dict[str, str], bytes]:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            break
        data += chunk
    head, _sep, rest = data.partition(b"\r\n\r\n")
    first, _nl, header_text = head.decode().partition("\r\n")
    headers = {}
    for line in header_text.split("\r\n"):
        key, sep, value = line.partition(":")
        if sep:
            headers[key.strip()] = value.strip()
    return first, headers, rest


@dataclass
class DiscoveryConsole:
    """Answers SRCH on two UDP ports (the PS4 and PS5 discovery ports) and records WAKEUP packets."""
    ps5: bool = True
    state: int = 200
    name: str = "Living room PS5"
    host_id: str = "AABBCCDDEEFF"
    system_version: str = "08050001"
    received: list[bytes] = field(default_factory=list)

    def __post_init__(self):
        self.sockets = []
        for _port in range(2):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("127.0.0.1", 0))
            self.sockets.append(sock)
        self.ps4_port, self.ps5_port = (s.getsockname()[1] for s in self.sockets)
        self.threads = [threading.Thread(target=self._serve, args=(s, i == 1), daemon=True)
                        for i, s in enumerate(self.sockets)]
        for thread in self.threads:
            thread.start()

    def _serve(self, sock: socket.socket, ps5_port: bool) -> None:
        while True:
            try:
                data, sender = sock.recvfrom(1024)
            except OSError:
                return
            self.received.append(data)
            if not data.startswith(b"SRCH") or ps5_port != self.ps5:
                continue
            status = "200 Ok" if self.state == 200 else "620 Server Standby"
            protocol = "00030010" if self.ps5 else "00020020"
            answer = (f"HTTP/1.1 {status}\nhost-id:{self.host_id}\nhost-type:{'PS5' if self.ps5 else 'PS4'}\n"
                      f"host-name:{self.name}\nhost-request-port:997\ndevice-discovery-protocol-version:{protocol}\n"
                      f"system-version:{self.system_version}\nrunning-app-name:Astro Bot\n")
            try:
                sock.sendto(answer.encode(), sender)
            except OSError:
                return                                  # closed by the test meanwhile

    @property
    def ports(self) -> dict[str, int]:
        return {"ps4_port": self.ps4_port, "ps5_port": self.ps5_port}

    def close(self) -> None:
        for sock in self.sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)        # wakes the thread blocked in recvfrom()
            except OSError:
                pass
            sock.close()


class _TcpConsole:
    def __init__(self):
        self.port = free_port()
        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", self.port))
        self.server.listen(4)
        self.errors: list[str] = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while True:
            try:
                conn, _addr = self.server.accept()
            except OSError:
                return
            with conn:
                try:
                    self.connection(conn)
                except Exception as error:      # noqa: BLE001 (the test reads the errors)
                    self.errors.append(repr(error))

    def connection(self, conn: socket.socket) -> None:
        raise NotImplementedError

    def close(self) -> None:
        # close() alone does not wake a thread blocked in accept(): the socket would take one more connection.
        try:
            self.server.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.server.close()


class RegistConsole(_TcpConsole):
    """Answers SRC2/SRC3 on UDP and the registration POST on TCP, on one port."""

    def __init__(self, target: Target = Target.PS5_1, pin: int = 12345678, account_id: bytes = bytes(range(8)),
                 refuse: str = ""):
        super().__init__()
        self.target, self.pin, self.account_id, self.refuse = target, pin, account_id, refuse
        self.requests: list[tuple[str, dict[str, str], dict[str, str]]] = []
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("127.0.0.1", self.port))
        threading.Thread(target=self._search, daemon=True).start()

    def _search(self) -> None:
        while True:
            try:
                data, sender = self.udp.recvfrom(256)
            except OSError:
                return
            ask = b"SRC3" if self.target.ps5 else b"SRC2"
            if data.startswith(ask):
                try:
                    self.udp.sendto((b"RES3" if self.target.ps5 else b"RES2") + b"\0", sender)
                except OSError:
                    return                              # closed by the test meanwhile

    def close(self) -> None:
        super().close()
        self.udp.close()

    def connection(self, conn: socket.socket) -> None:
        first, headers, body = _read_request(conn)
        size = int(headers["Content-Length"])
        while len(body) < size:
            body += conn.recv(4096)
        if self.refuse:
            conn.sendall(f"HTTP/1.1 403 Forbidden\r\nRP-Application-Reason: {self.refuse}\r\n\r\n".encode())
            return
        if self.target.pre10:
            crypt = rpcrypt.RPCrypt.for_regist(self.target, AMBASSADOR, 0, self.pin)
            assert body[0x11c:0x12c] == rpcrypt.aeropause(self.target, 0, AMBASSADOR)
        else:
            crypt = rpcrypt.RPCrypt.for_regist(self.target, AMBASSADOR, body[0x18d] & 0x1f, self.pin)
            seed = rpcrypt.aeropause(self.target, body[0] >> 3, AMBASSADOR)
            assert body[0xc7:0xcf] == seed[8:] and body[0x191:0x199] == seed[:8]
        inner = dict(parse_headers(crypt.decrypt(0, body[0x1e0:]).decode()))
        self.requests.append((first, headers, inner))
        if base64.b64decode(inner["Np-AccountId"]) != self.account_id:
            conn.sendall(b"HTTP/1.1 403 Forbidden\r\nRP-Application-Reason: 80108b02\r\n\r\n")
            return
        prefix = "PS5" if self.target.ps5 else "PS4"
        answer = (f"AP-Ssid: none\r\n{prefix}-RegistKey: {REGIST_KEY.hex()}\r\nRP-KeyType: 2\r\n"
                  f"RP-Key: {RP_KEY.hex()}\r\n{prefix}-Mac: {MAC.hex()}\r\n{prefix}-Nickname: Living room\r\n").encode()
        encrypted = crypt.encrypt(0, answer)
        conn.sendall(f"HTTP/1.1 200 OK\r\nContent-Length: {len(encrypted)}\r\n\r\n".encode() + encrypted)


class SessionConsole(_TcpConsole):
    """Answers the session request and runs the console's side of the control connection."""

    def __init__(self, target: Target = Target.PS5_1, wants_version: str = "", login_pin: str = "",
                 session_id: bytes = SESSION_ID, server_type: int = 2):
        super().__init__()
        self.target, self.wants_version, self.login_pin = target, wants_version, login_pin
        self.session_id, self.server_type = session_id, server_type
        self.paths: list[str] = []
        self.ctrl_headers: dict[str, str] = {}
        self.decrypted: dict[str, bytes] = {}
        self.messages: list[tuple[int, bytes]] = []
        self.heartbeat_answered = threading.Event()

    def connection(self, conn: socket.socket) -> None:
        first, headers, rest = _read_request(conn)
        path = first.split(" ")[1]
        self.paths.append(path)
        if path.endswith(("/init", "/rp/session")):
            assert headers["RP-Registkey"] == REGIST_KEY.hex()
            if self.wants_version and headers["Rp-Version"] != self.wants_version:
                conn.sendall(f"HTTP/1.1 403 Forbidden\r\nRP-Application-Reason: 80108b11\r\n"
                             f"RP-Version: {self.wants_version}\r\n\r\n".encode())
                return
            conn.sendall(f"HTTP/1.1 200 OK\r\nRP-Nonce: {base64.b64encode(NONCE).decode()}\r\n\r\n".encode())
            return
        self.ctrl(conn, headers, rest)

    def ctrl(self, conn: socket.socket, headers: dict[str, str], rest: bytes) -> None:
        target = Target.PS4_9 if self.wants_version == "9.0" else self.target
        crypt = rpcrypt.RPCrypt.for_session(target, NONCE, RP_KEY)
        self.ctrl_headers = headers
        names = ["RP-Auth", "RP-Did", "RP-OSType"]
        if target >= Target.PS4_10:
            names.append("RP-StartBitrate")
        if target.ps5:
            names.append("RP-StreamingType")
        for counter, name in enumerate(names):
            self.decrypted[name] = crypt.decrypt(counter, base64.b64decode(headers[name]))
        remote = len(names)                     # the board's next counter
        server_type = base64.b64encode(crypt.encrypt(0, bytes([self.server_type]) + bytes(15))).decode()
        conn.sendall(f"HTTP/1.1 200 OK\r\nRP-Server-Type: {server_type}\r\n\r\n".encode())
        local = 1
        buffer = rest

        def send(msg_type: int, payload: bytes = b"") -> None:
            nonlocal local
            if payload:
                payload = crypt.encrypt(local, payload)
                local += 1
            conn.sendall(session.frame(msg_type, payload))

        def receive() -> tuple[int, bytes] | None:
            nonlocal buffer, remote
            conn.settimeout(2.0)
            while len(buffer) < 8 or len(buffer) < 8 + struct.unpack(">I", buffer[:4])[0]:
                try:
                    chunk = conn.recv(4096)
                except (TimeoutError, OSError):
                    return None
                if not chunk:
                    return None
                buffer += chunk
            size, msg_type, _zero = struct.unpack(">IHH", buffer[:8])
            payload, buffer = buffer[8:8 + size], buffer[8 + size:]
            if payload:
                payload = crypt.decrypt(remote, payload)
                remote += 1
            self.messages.append((msg_type, payload))
            return msg_type, payload

        if self.login_pin:
            send(session.LOGIN_PIN_REQ)
            message = receive()
            ok = message == (session.LOGIN_PIN_REP, self.login_pin.encode())
            send(session.LOGIN, b"\x00" if ok else b"\x01")
            if not ok:
                return
        send(session.HEARTBEAT_REQ)
        if receive() == (session.HEARTBEAT_REP, b""):
            self.heartbeat_answered.set()
        send(session.SESSION_ID, self.session_id)
        while receive() is not None:
            pass
