# SPDX-License-Identifier: GPL-3.0-or-later
# Ported from Greenlight (packages/desktop/main/helpers/xcloudapi.ts and streammanager.ts), MIT, Copyright (c) 2019
# UnknownSKL (Jim Kroon); the MIT notice is in the README's License section.
"""A stream session with the streaming service (gssv): the same calls for a console at home ("home", with the
console's ID) and a cloud game ("cloud", with the game's title ID).

1. play starts the session; the service then gets the console or a cloud server ready (Provisioning), may queue a
   cloud game (WaitingForResources, with a waiting time), and asks for the account's transfer token once
   (ReadyToConnect, answered with connect) before it is Provisioned, or Failed.
2. sdp: the board's WebRTC offer goes up, the service's answer comes back (polled: 204 while it has none).
3. ice: the board's candidates go up, the service's come back.
4. keepalive every 30 s while the stream runs, and the session's address with DELETE at the end."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from .auth import StreamToken
from .net import Client, HttpError

KEEPALIVE_S = 30
POLL_S = 1.0                                # between two state questions
EXCHANGE_POLL_S = 0.75                      # between two questions for the answer of an exchange (204: not yet)
EXCHANGE_TRIES = 40                         # 30 s
READY_TIMEOUT_S = 15 * 60                   # a queue for a cloud game can be long; the person can cancel it

# The settings the reference sends: Microsoft's own browser client's
DEVICE_INFO = json.dumps({
    "appInfo": {"env": {"clientAppId": "Microsoft.GamingApp", "clientAppType": "native",
                        "clientAppVersion": "2203.1001.4.0", "clientSdkVersion": "8.5.2", "httpEnvironment": "prod",
                        "sdkInstallId": ""}},
    "dev": {"hw": {"make": "Microsoft", "model": "Surface Pro", "sdktype": "native"},
            "os": {"name": "Windows 11", "ver": "22631.2715", "platform": "desktop"},
            "displayInfo": {"dimensions": {"widthInPixels": 1920, "heightInPixels": 1080},
                            "pixelDensity": {"dpiX": 1, "dpiY": 1}}},
})
CHANNELS = {                                # the data channels' versions the board speaks
    "chatConfiguration": {"bytesPerSample": 2, "expectedClipDurationMs": 20,
                          "format": {"codec": "opus", "container": "webm"}, "numChannels": 1,
                          "sampleFrequencyHz": 24000},
    "chat": {"minVersion": 1, "maxVersion": 1},
    "control": {"minVersion": 1, "maxVersion": 3},
    "input": {"minVersion": 1, "maxVersion": 8},
    "message": {"minVersion": 1, "maxVersion": 1},
}


class SessionError(Exception):
    """The session could not start, or the service ended it."""


@dataclass
class State:
    name: str                               # Provisioning, WaitingForResources, ReadyToConnect, Provisioned, Failed
    wait_s: int = 0                         # the queue's waiting time, while WaitingForResources
    error: str = ""                         # what the service says, when Failed


def timezone_offset_minutes(clock: Callable[[], float] = time.time) -> int:
    return round(time.localtime(clock()).tm_gmtoff / 60)


class Session:
    def __init__(self, client: Client, token: StreamToken, kind: str, target: str, locale: str = "en-US",
                 sleep: Callable[[float], None] = time.sleep):
        """*kind*: "home" (target: the console's ID) or "cloud" (target: the game's title ID)."""
        if kind not in ("home", "cloud"):
            raise ValueError(kind)
        self.client, self.token, self.kind, self.target, self.locale = client, token, kind, target, locale
        self.sleep = sleep
        self.base = token.base_uri()
        self.path = ""                      # v5/sessions/home/<session id>, once started

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token.token}", "X-Gssv-Client": "XboxComBrowser",
                "X-MS-Device-Info": DEVICE_INFO}

    def _url(self, part: str = "") -> str:
        return f"{self.base}/{self.path}{part}"

    def play(self) -> str:
        cloud = self.kind == "cloud"
        data = self.client.post(f"{self.base}/v5/sessions/{self.kind}/play", self._headers(), json_body={
            "titleId": self.target if cloud else "", "systemUpdateGroup": "", "clientSessionId": "",
            "settings": {"nanoVersion": "V3;WebrtcTransport.dll", "enableTextToSpeech": False, "highContrast": 0,
                         "locale": self.locale, "useIceConnection": False,
                         "timezoneOffsetMinutes": timezone_offset_minutes(), "sdkType": "web",
                         "osName": "windows"},
            "serverId": "" if cloud else self.target, "fallbackRegionNames": []}).data
        path = str(data.get("sessionPath", "")) if isinstance(data, dict) else ""
        if not path:
            raise SessionError("the streaming service started no session")
        self.path = path.strip("/")
        return self.path

    def state(self) -> State:
        data = self.client.get(self._url("/state"), self._headers()).data
        data = data if isinstance(data, dict) else {}
        details = data.get("errorDetails") if isinstance(data.get("errorDetails"), dict) else {}
        error = " ".join(str(details.get(k) or "") for k in ("code", "message")).strip()
        return State(str(data.get("state", "")), error=error)

    def wait_time(self) -> int:
        """The queue's estimated wait for a cloud game, in seconds (0 when the service gives none)."""
        try:
            data = self.client.get(f"{self.base}/v1/waittime/{self.target}", self._headers()).data
        except HttpError:
            return 0
        seconds = data.get("estimatedTotalWaitTimeInSeconds", 0) if isinstance(data, dict) else 0
        return int(seconds) if isinstance(seconds, (int, float)) else 0

    def connect(self, transfer_token: str) -> None:
        self.client.post(self._url("/connect"), self._headers(), json_body={"userToken": transfer_token})

    def wait_until_ready(self, transfer_token: Callable[[], str], on_state: Callable[[State], None] = lambda s: None,
                         cancelled: Callable[[], bool] = lambda: False,
                         clock: Callable[[], float] = time.monotonic) -> None:
        """Follows the session's state until it is Provisioned: answers ReadyToConnect once with the transfer
        token, and reports every state (with the queue's wait) to *on_state*. Raises SessionError when it
        Failed, timed out or was *canceled*."""
        end = clock() + READY_TIMEOUT_S
        connected = False
        wait = None
        while True:
            if cancelled():
                raise SessionError("cancelled")
            if clock() >= end:
                raise SessionError("the session was not ready in time")
            try:
                state = self.state()
            except HttpError as error:
                if error.status == 404:
                    raise SessionError("the streaming service ended the session") from error
                raise
            if state.name == "WaitingForResources":
                if wait is None:
                    wait = self.wait_time()
                state.wait_s = wait
            on_state(state)
            if state.name == "Provisioned":
                return
            if state.name == "Failed":
                raise SessionError(state.error or "the streaming service could not start the session")
            if state.name == "ReadyToConnect" and not connected:
                self.connect(transfer_token())
                connected = True
            self.sleep(POLL_S)

    def _exchange(self, part: str, body: dict) -> object:
        """Posts *body*, then asks for the service's answer until it has one (204 until then)."""
        self.client.post(self._url(part), self._headers(), json_body=body)
        for _ in range(EXCHANGE_TRIES):
            response = self.client.get(self._url(part), self._headers())
            if response.status != 204 and isinstance(response.data, dict):
                data = response.data
                details = data.get("errorDetails") if isinstance(data.get("errorDetails"), dict) else {}
                if details.get("code") or details.get("message"):
                    raise SessionError(f"{part.strip('/')}: {details.get('code') or ''} "
                                       f"{details.get('message') or ''}".strip())
                answer = data.get("exchangeResponse")
                if isinstance(answer, str) and answer:
                    try:
                        return json.loads(answer)
                    except ValueError as error:
                        raise SessionError(f"{part.strip('/')}: unreadable answer") from error
            self.sleep(EXCHANGE_POLL_S)
        raise SessionError(f"{part.strip('/')}: the streaming service gave no answer")

    def exchange_sdp(self, offer: str) -> str:
        """The board's offer up, the service's answer (its SDP) back."""
        answer = self._exchange("/sdp", {"messageType": "offer", "sdp": offer, "configuration": CHANNELS})
        sdp = answer.get("sdp") if isinstance(answer, dict) else None
        if not isinstance(sdp, str) or not sdp:
            raise SessionError("sdp: the answer has no SDP")
        return sdp

    def exchange_ice(self, candidates: list[dict]) -> list[dict]:
        """The board's ICE candidates up ({candidate, sdpMid, sdpMLineIndex}), the service's back."""
        answer = self._exchange("/ice", {"messageType": "iceCandidate", "candidate": candidates})
        if not isinstance(answer, list):
            raise SessionError("ice: the answer has no candidates")
        return [c for c in answer if isinstance(c, dict) and isinstance(c.get("candidate"), str)]

    def keepalive(self) -> None:
        self.client.post(self._url("/keepalive"), self._headers(), json_body={})

    def stop(self) -> None:
        """Ends the session (the console goes back to its home screen, a cloud server is freed); never raises."""
        if not self.path:
            return
        try:
            self.client.call("DELETE", self._url(), self._headers())
        except HttpError:
            pass
        self.path = ""
