# SPDX-License-Identifier: AGPL-3.0-or-later
"""psn.py: the account ID through the PlayStation sign-in, against a fake token service on localhost that checks what
The reference's script sends (the Remote Play client's credentials, the code, the redirect address)."""

from __future__ import annotations

import base64
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from consoles_link import jobs, psn

CODE = "v3.AbCdEf"
TOKEN = "tok/with+chars="
USER_ID = "4782394583276428394"


class FakePsn(BaseHTTPRequestHandler):
    user_info: dict = {"user_id": USER_ID, "online_id": "board_player", "scopes": "psn:clientapp"}
    requests: list = []

    def log_message(self, *args):
        pass

    def _answer(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        expected = "Basic " + base64.b64encode(f"{psn.CLIENT_ID}:{psn.CLIENT_SECRET}".encode()).decode()
        return self.headers.get("Authorization") == expected

    def do_POST(self):
        form = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        self.requests.append(("POST", self.path, form))
        if self.path != "/oauth/token" or not self._authorized():
            return self._answer(401, {"error": "invalid_client"})
        if form != {"grant_type": ["authorization_code"], "code": [CODE], "redirect_uri": [psn.REDIRECT_URI]}:
            return self._answer(400, {"error": "invalid_grant", "error_description": "Invalid authorization code"})
        self._answer(200, {"access_token": TOKEN, "token_type": "bearer", "expires_in": 3599})

    def do_GET(self):
        self.requests.append(("GET", self.path, None))
        if self.path != "/oauth/token/" + urllib.parse.quote(TOKEN, safe="") or not self._authorized():
            return self._answer(404, {"error": "not_found"})
        self._answer(200, self.user_info)


@pytest.fixture
def psn_service():
    FakePsn.requests = []
    FakePsn.user_info = {"user_id": USER_ID, "online_id": "board_player", "scopes": "psn:clientapp"}
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakePsn)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/oauth"
    server.shutdown()
    server.server_close()


def test_login_url_is_the_references():
    assert psn.login_url() == (
        "https://auth.api.sonyentertainmentnetwork.com/2.0/oauth/authorize?service_entity=urn:service-entity:psn"
        "&response_type=code&client_id=ba495a24-818c-472b-b12d-ff231c1b5745"
        "&redirect_uri=https://remoteplay.dl.playstation.net/remoteplay/redirect&scope=psn:clientapp"
        "&request_locale=en_US&ui=pr&service_logo=ps&layout_type=popup&smcid=remoteplay&prompt=always"
        "&PlatformPrivacyWs1=minimal&")


def test_code_from_the_pasted_address():
    assert psn.code_from_redirect(f"  {psn.REDIRECT_URI}?code={CODE}&cid=x \n") == CODE
    assert psn.code_from_redirect(CODE) == CODE
    with pytest.raises(psn.PsnError, match="no code"):
        psn.code_from_redirect(psn.REDIRECT_URI)
    with pytest.raises(psn.PsnError, match="access_denied"):
        psn.code_from_redirect(f"{psn.REDIRECT_URI}?error=access_denied")
    with pytest.raises(psn.PsnError, match="Paste"):
        psn.code_from_redirect("   ")


def test_account_id_from_psn(psn_service):
    account = psn.account_id(CODE, auth_base=psn_service)
    assert account.number == int(USER_ID) and account.online_id == "board_player"
    assert account.account_id == int(USER_ID).to_bytes(8, "little")
    assert account.code == base64.b64encode(int(USER_ID).to_bytes(8, "little")).decode()
    assert [r[:2] for r in FakePsn.requests] == [("POST", "/oauth/token"),
                                                  ("GET", "/oauth/token/" + urllib.parse.quote(TOKEN, safe=""))]


def test_used_or_old_code(psn_service):
    with pytest.raises(psn.PsnError, match="works only once"):
        psn.account_id("v3.used", auth_base=psn_service)


def test_answer_without_account_id(psn_service):
    FakePsn.user_info = {"online_id": "x"}
    with pytest.raises(psn.PsnError, match="no account ID"):
        psn.account_id(CODE, auth_base=psn_service)


def test_psn_unreachable():
    with pytest.raises(psn.PsnError, match="could not be reached"):
        psn.account_id(CODE, auth_base="http://127.0.0.1:9/oauth")


def test_job(psn_service):
    outcome = jobs.psn_account(f"{psn.REDIRECT_URI}?code={CODE}", auth_base=psn_service)
    assert outcome.ok and outcome.value.number == int(USER_ID)
    assert "(board_player)" in outcome.message and outcome.value.code in outcome.message
    failed = jobs.psn_account("https://example.com/", auth_base=psn_service)
    assert not failed.ok and "no code" in failed.message
