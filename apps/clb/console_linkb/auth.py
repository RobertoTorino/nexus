# SPDX-License-Identifier: GPL-3.0-or-later
# Ported from xal-node (src/msal.ts and src/lib/tokens/), MIT, Copyright (c) 2023 UnknownSKL (Jim Kroon); the MIT
# notice is in the README's License section.
"""The Microsoft account: signing in with a code (the person enters it on microsoft.com/link, on a phone or any
browser, so no password passes through the app), and the tokens the Xbox services want.

The chain, as the reference has it:
1. Microsoft's device code sign-in gives a user token (an hour) and a refresh token (kept, to sign in again later).
2. The user token buys an Xbox Live user token (user.auth.xboxlive.com).
3. That buys an XSTS token per service (xsts.auth.xboxlive.com): http://xboxlive.com for the console list and the
   wake command, http://gssv.xboxlive.com/ for streaming.
4. The gssv token buys the streaming tokens: xhome for the consoles, xgpuweb for the cloud with Game Pass, or
   xgpuwebf2p for the cloud's free-to-play games without it.
5. For a stream, a console transfer token from login.live.com, sent when the session asks for it (ReadyToConnect).

Only the refresh token is kept, in ~/.config/bc250-console-linkb/account.json (mode 0600); the others live in
memory until they expire. Every call is blocking: the window runs them off its thread."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from bc250_core.platform import config_home

from . import APP_ID
from .net import Client, HttpError

CLIENT_ID = "1f907974-e22b-4810-a9de-d9647380c97e"         # Xbox's web client, as the reference uses
SCOPE = "xboxlive.signin openid profile offline_access"
LOGIN = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
TRANSFER_SCOPE = "service::http://Passport.NET/purpose::PURPOSE_XBOX_CLOUD_CONSOLE_TRANSFER_TOKEN"
WEB_PARTY = "http://xboxlive.com"
GSSV_PARTY = "http://gssv.xboxlive.com/"
HOME = "xhome"
CLOUD = "xgpuweb"                           # Xbox Cloud Gaming with Game Pass Ultimate
CLOUD_FREE = "xgpuwebf2p"                   # the free-to-play games, without Game Pass
MARGIN = 60                                 # s: a token closer than this to its end is renewed first
XBOX_HEADERS = {"x-xbl-contract-version": "1", "Cache-Control": "no-cache", "Origin": "https://www.xbox.com",
                "Referer": "https://www.xbox.com/"}


class AuthError(Exception):
    """Signing in failed or was canceled."""


class SignedOut(AuthError):
    """No account, or Microsoft no longer accepts the kept refresh token: sign in again."""


@dataclass
class DeviceCode:
    user_code: str
    device_code: str
    verification_uri: str
    expires_in: int
    interval: int

    @classmethod
    def from_json(cls, data: dict) -> DeviceCode:
        try:
            return cls(str(data["user_code"]), str(data["device_code"]), str(data["verification_uri"]),
                       int(data.get("expires_in", 900)), max(1, int(data.get("interval", 5))))
        except (KeyError, TypeError, ValueError) as error:
            raise AuthError(f"Microsoft's answer has no sign-in code ({error})") from error


@dataclass
class UserToken:
    access_token: str
    refresh_token: str
    expires_at: float                       # time.time()

    @classmethod
    def from_json(cls, data: dict, now: float) -> UserToken:
        try:
            return cls(str(data["access_token"]), str(data["refresh_token"]),
                       now + int(data.get("expires_in", 3600)))
        except (KeyError, TypeError, ValueError) as error:
            raise AuthError(f"Microsoft's answer has no token ({error})") from error


def _not_after(text: str) -> float:
    """An Xbox token's NotAfter ("2026-10-22T10:00:00.1234567Z") as time.time(); 0 when unreadable."""
    text = str(text or "").strip()
    if not text:
        return 0.0
    if "." in text:                                         # Python reads at most 6 digits of a fraction
        head, _, tail = text.partition(".")
        digits = "".join(c for c in tail if c.isdigit())[:6]
        text = f"{head}.{digits}" + ("+00:00" if tail.endswith("Z") else "")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


@dataclass
class XboxToken:
    """An Xbox Live user token or an XSTS token: the token, the user hash (uhs) and its end."""

    token: str
    uhs: str
    not_after: float
    gamertag: str = ""

    @classmethod
    def from_json(cls, data: dict) -> XboxToken:
        try:
            claims = data["DisplayClaims"]["xui"][0]
            return cls(str(data["Token"]), str(claims.get("uhs", "")), _not_after(data.get("NotAfter", "")),
                       str(claims.get("gtg", "")))
        except (KeyError, IndexError, TypeError) as error:
            raise AuthError(f"Xbox Live's answer has no token ({error})") from error

    def header(self) -> str:
        """The Authorization header of the Xbox Live web API."""
        return f"XBL3.0 x={self.uhs};{self.token}"


@dataclass
class Region:
    name: str
    base_uri: str                           # https://weu.core.gssv-play-prod.xboxlive.com
    default: bool


@dataclass
class StreamToken:
    """A streaming token for one offering (xhome, xgpuweb, xgpuwebf2p) and the regions it may stream from."""

    offering: str
    token: str
    market: str
    regions: list[Region]
    expires_at: float

    @classmethod
    def from_json(cls, offering: str, data: dict, now: float) -> StreamToken:
        try:
            regions = [Region(str(r.get("name", "")), str(r["baseUri"]).rstrip("/"), bool(r.get("isDefault")))
                       for r in data["offeringSettings"]["regions"]]
            return cls(offering, str(data["gsToken"]), str(data.get("market", "")), regions,
                       now + int(data.get("durationInSeconds", 3600)))
        except (KeyError, TypeError, ValueError) as error:
            raise AuthError(f"the streaming service's answer has no token ({error})") from error

    def base_uri(self) -> str:
        """The default region's address (the first when none is marked)."""
        for region in self.regions:
            if region.default:
                return region.base_uri
        if not self.regions:
            raise AuthError(f"no region to stream from for {self.offering}")
        return self.regions[0].base_uri


def account_file() -> Path:
    return config_home() / APP_ID / "account.json"


def load_refresh_token(path: Path | None = None) -> str:
    path = path or account_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(data.get("refresh_token", "")) if isinstance(data, dict) else ""


def save_refresh_token(token: str, path: Path | None = None) -> None:
    """Kept only for the person: mode 0600, written to a new file and moved over the old one."""
    path = path or account_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({"refresh_token": token}, handle)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def forget(path: Path | None = None) -> None:
    (path or account_file()).unlink(missing_ok=True)


# --- The calls --------------------------------------------------------------------------------------------------

def start_sign_in(client: Client) -> DeviceCode:
    response = client.post(f"{LOGIN}/devicecode", form={"client_id": CLIENT_ID, "scope": SCOPE})
    return DeviceCode.from_json(response.data if isinstance(response.data, dict) else {})


def wait_for_sign_in(client: Client, code: DeviceCode, cancelled: Callable[[], bool] = lambda: False,
                     sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.time) -> UserToken:
    """Asks Microsoft every few seconds whether the code was entered, until it was, it expired or *canceled*."""
    interval = code.interval
    end = clock() + code.expires_in
    form = {"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "client_id": CLIENT_ID,
            "device_code": code.device_code}
    while True:
        if cancelled():
            raise AuthError("signing in was canceled")
        if clock() >= end:
            raise AuthError("the code expired before it was entered: sign in again for a new one")
        try:
            response = client.post(f"{LOGIN}/token", form=form)
        except HttpError as error:
            reason = error.json().get("error", "")
            if reason == "authorization_pending":
                pass
            elif reason == "slow_down":
                interval += 5
            elif reason == "expired_token":
                raise AuthError("the code expired before it was entered: sign in again for a new one") from error
            elif reason in ("authorization_declined", "access_denied"):
                raise AuthError("signing in was declined on Microsoft's page") from error
            else:
                raise AuthError(f"signing in failed: {error}") from error
        else:
            return UserToken.from_json(response.data if isinstance(response.data, dict) else {}, clock())
        sleep(interval)


def refresh_user_token(client: Client, refresh_token: str, now: float) -> UserToken:
    try:
        response = client.post(f"{LOGIN}/token", headers={"Cache-Control": "no-store, must-revalidate, no-cache"},
                               form={"client_id": CLIENT_ID, "grant_type": "refresh_token",
                                     "refresh_token": refresh_token, "scope": SCOPE})
    except HttpError as error:
        if error.status in (400, 401):
            raise SignedOut("Microsoft no longer accepts the saved sign-in: sign in again") from error
        raise
    return UserToken.from_json(response.data if isinstance(response.data, dict) else {}, now)


def xbox_user_token(client: Client, access_token: str) -> XboxToken:
    response = client.post("https://user.auth.xboxlive.com/user/authenticate", headers=XBOX_HEADERS,
                           json_body={"Properties": {"AuthMethod": "RPS", "RpsTicket": f"d={access_token}",
                                                     "SiteName": "user.auth.xboxlive.com"},
                                      "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"})
    return XboxToken.from_json(response.data if isinstance(response.data, dict) else {})


XSTS_ERRORS = {                             # XErr codes of xsts.auth.xboxlive.com
    2148916233: "this Microsoft account has no Xbox profile yet: sign in once on xbox.com to create one",
    2148916235: "Xbox Live is not available in this account's country",
    2148916236: "this account needs adult verification on xbox.com first",
    2148916237: "this account needs adult verification on xbox.com first",
    2148916238: "this is a child account: an adult has to add it to a Microsoft family first",
}


def xsts_token(client: Client, user: XboxToken, relying_party: str) -> XboxToken:
    try:
        response = client.post("https://xsts.auth.xboxlive.com/xsts/authorize",
                               headers={**XBOX_HEADERS, "Accept": "*/*", "ms-cv": "0"},
                               json_body={"Properties": {"SandboxId": "RETAIL", "UserTokens": [user.token]},
                                          "RelyingParty": relying_party, "TokenType": "JWT"})
    except HttpError as error:
        reason = XSTS_ERRORS.get(error.json().get("XErr"))
        if reason:
            raise AuthError(reason) from error
        raise
    return XboxToken.from_json(response.data if isinstance(response.data, dict) else {})


def stream_token(client: Client, gssv: XboxToken, offering: str, now: float) -> StreamToken:
    response = client.post(f"https://{offering}.gssv-play-prod.xboxlive.com/v2/login/user",
                           headers={"Cache-Control": "no-store, must-revalidate, no-cache",
                                    "x-gssv-client": "XboxComBrowser"},
                           json_body={"token": gssv.token, "offeringId": offering})
    return StreamToken.from_json(offering, response.data if isinstance(response.data, dict) else {}, now)


def transfer_token(client: Client, refresh_token: str) -> str:
    """The console transfer token a stream session asks for (ReadyToConnect)."""
    response = client.post("https://login.live.com/oauth20_token.srf",
                           form={"client_id": CLIENT_ID, "scope": TRANSFER_SCOPE, "grant_type": "refresh_token",
                                 "refresh_token": refresh_token})
    data = response.data if isinstance(response.data, dict) else {}
    token = str(data.get("access_token", ""))
    if not token:
        raise AuthError("login.live.com gave no transfer token")
    return token


# --- The account ------------------------------------------------------------------------------------------------

@dataclass
class Account:
    """The signed-in account and its tokens, renewed when they run out. Safe to use from several threads."""

    client: Client = field(default_factory=Client)
    path: Path | None = None                # where the refresh token is kept (None: account_file())
    clock: Callable[[], float] = time.time

    def __post_init__(self):
        self._lock = threading.RLock()
        self._refresh = load_refresh_token(self.path)
        self._user: UserToken | None = None
        self._xbox: XboxToken | None = None
        self._xsts: dict[str, XboxToken] = {}
        self._streams: dict[str, StreamToken] = {}
        self.cloud_offering = ""            # CLOUD or CLOUD_FREE, once a cloud token was got; "" when none

    @property
    def signed_in(self) -> bool:
        return bool(self._refresh)

    def signed_in_with(self, user: UserToken) -> None:
        """Keeps a new sign-in (wait_for_sign_in's token) and drops what belonged to an earlier one."""
        with self._lock:
            self._drop()
            self._user = user
            self._refresh = user.refresh_token
            save_refresh_token(user.refresh_token, self.path)

    def sign_out(self) -> None:
        with self._lock:
            self._drop()
            self._refresh = ""
            forget(self.path)

    def _drop(self) -> None:
        self._user, self._xbox = None, None
        self._xsts.clear()
        self._streams.clear()
        self.cloud_offering = ""

    def _fresh(self, until: float) -> bool:
        return until - self.clock() > MARGIN

    def user_token(self) -> UserToken:
        with self._lock:
            if not self._refresh:
                raise SignedOut("not signed in")
            if self._user is None or not self._fresh(self._user.expires_at):
                try:
                    self._user = refresh_user_token(self.client, self._refresh, self.clock())
                except SignedOut:
                    self.sign_out()
                    raise
                if self._user.refresh_token != self._refresh:       # Microsoft hands out a new one now and then
                    self._refresh = self._user.refresh_token
                    save_refresh_token(self._refresh, self.path)
            return self._user

    def xbox_token(self) -> XboxToken:
        with self._lock:
            if self._xbox is None or not self._fresh(self._xbox.not_after):
                self._xbox = xbox_user_token(self.client, self.user_token().access_token)
            return self._xbox

    def xsts(self, relying_party: str) -> XboxToken:
        with self._lock:
            token = self._xsts.get(relying_party)
            if token is None or not self._fresh(token.not_after):
                token = self._xsts[relying_party] = xsts_token(self.client, self.xbox_token(), relying_party)
            return token

    def web_token(self) -> XboxToken:
        """For the console list and the wake command; its gamertag is the account's."""
        return self.xsts(WEB_PARTY)

    def stream(self, offering: str) -> StreamToken:
        with self._lock:
            token = self._streams.get(offering)
            if token is None or not self._fresh(token.expires_at):
                token = self._streams[offering] = stream_token(self.client, self.xsts(GSSV_PARTY), offering,
                                                               self.clock())
            return token

    def home_token(self) -> StreamToken:
        return self.stream(HOME)

    def cloud_token(self) -> StreamToken:
        """Game Pass's cloud when the account has it, else the free-to-play games (as the reference tries them).
        Raises AuthError when neither is open to the account (a country without Xbox Cloud Gaming)."""
        with self._lock:
            offerings = [self.cloud_offering] if self.cloud_offering else [CLOUD, CLOUD_FREE]
            last: Exception | None = None
            for offering in offerings:
                try:
                    token = self.stream(offering)
                except (HttpError, AuthError) as error:
                    last = error
                    continue
                self.cloud_offering = offering
                return token
            raise AuthError(f"Xbox Cloud Gaming is not open to this account ({last})")

    def transfer_token(self) -> str:
        with self._lock:
            self.user_token()
            return transfer_token(self.client, self._refresh)
