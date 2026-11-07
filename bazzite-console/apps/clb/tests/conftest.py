# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared fixtures: an offscreen QApplication, settings and XDG folders in a temp folder, and Microsoft's services
as a fake transport that answers from a list of routes and records every call (the tests never reach the
network). The answers are shaped as the services answer; the values are made up."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CORE = Path(__file__).resolve().parents[4] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))           # bc250_core from the checkout, as the installer bundles it

NOT_AFTER = "2099-01-01T00:00:00.1234567Z"
USER_TOKEN = {"token_type": "Bearer", "expires_in": 3600, "scope": "xboxlive.signin", "access_token": "AT-1",
              "refresh_token": "RT-1"}


def xbox_token(token: str, uhs: str = "1234567890", gamertag: str = "") -> dict:
    claims = {"uhs": uhs, **({"gtg": gamertag} if gamertag else {})}
    return {"IssueInstant": "2026-10-21T10:00:00.0000000Z", "NotAfter": NOT_AFTER, "Token": token,
            "DisplayClaims": {"xui": [claims]}}


def stream_token(token: str, base: str = "https://weu.core.gssv-play-prod.xboxlive.com", market: str = "NL") -> dict:
    return {"offeringSettings": {"allowRegionSelection": False, "regions": [
        {"name": "UKSouth", "baseUri": "https://uks.core.gssv-play-prod.xboxlive.com", "isDefault": False},
        {"name": "WestEurope", "baseUri": base, "isDefault": True}]},
        "market": market, "gsToken": token, "tokenType": "bearer", "durationInSeconds": 14400}


class FakeTransport:
    """Answers calls from routes: (method, url start) -> a list of (status, body) used in turn, the last one again
    when the list runs out. A body that is not bytes is sent as JSON. Unknown calls get 404."""

    def __init__(self, routes: dict | None = None):
        self.routes: dict[tuple[str, str], list] = {}
        self.calls: list[tuple[str, str, dict, bytes | None]] = []
        for key, answers in (routes or {}).items():
            self.add(*key, *([answers] if isinstance(answers, tuple) else [answers]))

    def add(self, method: str, url: str, *answers) -> None:
        listed = []
        for answer in answers:
            listed.extend(answer if isinstance(answer, list) else [answer])
        self.routes[(method, url)] = listed

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        matches = [k for k in self.routes if k[0] == method and url.startswith(k[1])]
        if not matches:
            return 404, b""
        key = max(matches, key=lambda k: len(k[1]))
        answers = self.routes[key]
        status, data = answers.pop(0) if len(answers) > 1 else answers[0]
        return status, data if isinstance(data, bytes) else json.dumps(data).encode()

    def sent(self, method: str, url: str) -> list:
        """The bodies sent to *url* (JSON or a form, decoded)."""
        found = []
        for m, u, _headers, body in self.calls:
            if m == method and u.startswith(url):
                text = (body or b"").decode()
                try:
                    found.append(json.loads(text))
                except ValueError:
                    found.append(dict(urllib.parse.parse_qsl(text)))
        return found

    def headers(self, method: str, url: str) -> list[dict]:
        return [h for m, u, h, _body in self.calls if m == method and u.startswith(url)]


def signed_in_routes() -> dict:
    """The sign-in chain of an account that has Game Pass Ultimate."""
    return {
        ("POST", "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"): (200, USER_TOKEN),
        ("POST", "https://user.auth.xboxlive.com/user/authenticate"): (200, xbox_token("XBL")),
        ("POST", "https://xsts.auth.xboxlive.com/xsts/authorize"): (200, xbox_token("XSTS", gamertag="Player One")),
        ("POST", "https://xhome.gssv-play-prod.xboxlive.com/v2/login/user"): (200, stream_token("HOME")),
        ("POST", "https://xgpuweb.gssv-play-prod.xboxlive.com/v2/login/user"): (200, stream_token("CLOUD")),
        ("POST", "https://login.live.com/oauth20_token.srf"): (200, {"access_token": "LPT", "refresh_token": "RT-2",
                                                                     "user_id": "u"}),
    }


@pytest.fixture
def transport():
    return FakeTransport(signed_in_routes())


@pytest.fixture
def account(transport, tmp_path):
    from console_linkb.auth import Account, save_refresh_token
    from console_linkb.net import Client
    path = tmp_path / "account.json"
    save_refresh_token("RT-1", path)
    return Account(Client(transport), path)


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    """The app keeps an .ini (AppInfo.settings_ini), so this also keeps the tests out of the Windows registry."""
    from PyQt6.QtCore import QSettings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    return tmp_path / "settings"
