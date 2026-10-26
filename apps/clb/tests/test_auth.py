# SPDX-License-Identifier: GPL-3.0-or-later
"""The Microsoft account: the code sign-in, the token chain and its renewal, the kept refresh token."""

from __future__ import annotations

import stat

import pytest
from conftest import USER_TOKEN, FakeTransport, signed_in_routes, stream_token, xbox_token

from console_linkb import auth
from console_linkb.auth import Account, AuthError, DeviceCode, SignedOut
from console_linkb.net import Client, HttpError

LOGIN = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
CODE = {"user_code": "ABCD-EFGH", "device_code": "DC", "verification_uri": "https://www.microsoft.com/link",
        "expires_in": 900, "interval": 5, "message": "..."}


class Clock:
    def __init__(self):
        self.now = 1_000_000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_start_sign_in_asks_for_a_code_with_the_xbox_scope():
    transport = FakeTransport({("POST", f"{LOGIN}/devicecode"): (200, CODE)})
    code = auth.start_sign_in(Client(transport))
    assert code == DeviceCode("ABCD-EFGH", "DC", "https://www.microsoft.com/link", 900, 5)
    assert transport.sent("POST", f"{LOGIN}/devicecode") == [{"client_id": auth.CLIENT_ID, "scope": auth.SCOPE}]


def test_wait_for_sign_in_polls_until_the_code_was_entered():
    transport = FakeTransport()
    transport.add("POST", f"{LOGIN}/token", (400, {"error": "authorization_pending"}),
                  (400, {"error": "slow_down"}), (200, USER_TOKEN))
    clock = Clock()
    user = auth.wait_for_sign_in(Client(transport), DeviceCode("A", "DC", "u", 900, 5), sleep=clock.sleep,
                                 clock=clock)
    assert (user.access_token, user.refresh_token) == ("AT-1", "RT-1")
    assert user.expires_at == clock.now + 3600
    assert clock.slept == [5, 10]                       # slow_down adds 5 s
    assert transport.sent("POST", f"{LOGIN}/token")[0]["device_code"] == "DC"


@pytest.mark.parametrize("error, says", [("expired_token", "expired"), ("authorization_declined", "declined"),
                                         ("invalid_grant", "failed")])
def test_wait_for_sign_in_stops_on_an_error(error, says):
    transport = FakeTransport({("POST", f"{LOGIN}/token"): (400, {"error": error})})
    with pytest.raises(AuthError, match=says):
        auth.wait_for_sign_in(Client(transport), DeviceCode("A", "DC", "u", 900, 5), sleep=lambda s: None)


def test_wait_for_sign_in_ends_when_the_code_runs_out_or_is_cancelled():
    transport = FakeTransport({("POST", f"{LOGIN}/token"): (400, {"error": "authorization_pending"})})
    clock = Clock()
    with pytest.raises(AuthError, match="expired"):
        auth.wait_for_sign_in(Client(transport), DeviceCode("A", "DC", "u", 12, 5), sleep=clock.sleep, clock=clock)
    with pytest.raises(AuthError, match="canceled"):
        auth.wait_for_sign_in(Client(transport), DeviceCode("A", "DC", "u", 900, 5), lambda: True)


def test_the_refresh_token_is_kept_for_the_person_only(tmp_path):
    path = tmp_path / "sub" / "account.json"
    auth.save_refresh_token("secret", path)
    assert auth.load_refresh_token(path) == "secret"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    auth.forget(path)
    assert auth.load_refresh_token(path) == ""


def test_not_after_reads_seven_digit_fractions():
    assert auth._not_after("2026-10-22T10:00:00.1234567Z") == pytest.approx(1792663200.123456)
    assert auth._not_after("2026-10-22T10:00:00Z") == 1792663200
    assert auth._not_after("") == 0


def test_the_chain_gives_the_web_token_with_the_gamertag(account, transport):
    web = account.web_token()
    assert (web.token, web.uhs, web.gamertag) == ("XSTS", "1234567890", "Player One")
    assert web.header() == "XBL3.0 x=1234567890;XSTS"
    refresh = transport.sent("POST", f"{LOGIN}/token")[0]
    assert refresh["grant_type"] == "refresh_token" and refresh["refresh_token"] == "RT-1"
    rps = transport.sent("POST", "https://user.auth.xboxlive.com")[0]
    assert rps["Properties"]["RpsTicket"] == "d=AT-1"
    xsts = transport.sent("POST", "https://xsts.auth.xboxlive.com")[0]
    assert xsts["RelyingParty"] == "http://xboxlive.com" and xsts["Properties"]["UserTokens"] == ["XBL"]


def test_tokens_are_reused_until_they_run_out(account, transport):
    account.web_token()
    account.web_token()
    account.home_token()
    assert len(transport.sent("POST", f"{LOGIN}/token")) == 1
    assert len(transport.sent("POST", "https://user.auth.xboxlive.com")) == 1
    parties = [b["RelyingParty"] for b in transport.sent("POST", "https://xsts.auth.xboxlive.com")]
    assert parties == ["http://xboxlive.com", "http://gssv.xboxlive.com/"]


def test_home_and_cloud_tokens_with_their_default_region(account, transport):
    home = account.home_token()
    assert home.token == "HOME" and home.base_uri() == "https://weu.core.gssv-play-prod.xboxlive.com"
    assert transport.sent("POST", "https://xhome.gssv-play-prod")[0] == {"token": "XSTS", "offeringId": "xhome"}
    assert account.cloud_token().token == "CLOUD"
    assert account.cloud_offering == auth.CLOUD


def test_without_game_pass_the_cloud_is_the_free_to_play_games(tmp_path):
    routes = signed_in_routes()
    routes[("POST", "https://xgpuweb.gssv-play-prod.xboxlive.com/v2/login/user")] = (403, b"")
    routes[("POST", "https://xgpuwebf2p.gssv-play-prod.xboxlive.com/v2/login/user")] = (200, stream_token("F2P"))
    transport = FakeTransport(routes)
    auth.save_refresh_token("RT-1", tmp_path / "a.json")
    account = Account(Client(transport), tmp_path / "a.json")
    assert account.cloud_token().token == "F2P"
    assert account.cloud_offering == auth.CLOUD_FREE
    account.cloud_token()
    assert len(transport.sent("POST", "https://xgpuweb.gssv-play-prod")) == 1     # not asked again


def test_no_cloud_at_all_is_said(tmp_path):
    routes = signed_in_routes()
    for offering in ("xgpuweb", "xgpuwebf2p"):
        routes[("POST", f"https://{offering}.gssv-play-prod.xboxlive.com/v2/login/user")] = (403, b"")
    auth.save_refresh_token("RT-1", tmp_path / "a.json")
    account = Account(Client(FakeTransport(routes)), tmp_path / "a.json")
    with pytest.raises(AuthError, match="not open to this account"):
        account.cloud_token()


def test_a_refused_refresh_token_signs_out(account, transport, tmp_path):
    transport.add("POST", f"{LOGIN}/token", (400, {"error": "invalid_grant"}))
    with pytest.raises(SignedOut):
        account.web_token()
    assert not account.signed_in
    assert not (tmp_path / "account.json").exists()


def test_a_new_refresh_token_from_microsoft_is_kept(account, transport, tmp_path):
    transport.add("POST", f"{LOGIN}/token", (200, {**USER_TOKEN, "refresh_token": "RT-NEW"}))
    account.user_token()
    assert auth.load_refresh_token(tmp_path / "account.json") == "RT-NEW"


def test_xsts_errors_are_said_plainly(account, transport):
    transport.add("POST", "https://xsts.auth.xboxlive.com/xsts/authorize", (401, {"XErr": 2148916233}))
    with pytest.raises(AuthError, match="no Xbox profile"):
        account.web_token()


def test_the_transfer_token_for_a_session(account, transport):
    assert account.transfer_token() == "LPT"
    sent = transport.sent("POST", "https://login.live.com/oauth20_token.srf")[0]
    assert sent["scope"] == auth.TRANSFER_SCOPE and sent["refresh_token"] == "RT-1"


def test_signing_in_replaces_the_account(tmp_path):
    transport = FakeTransport(signed_in_routes())
    account = Account(Client(transport), tmp_path / "a.json")
    assert not account.signed_in
    with pytest.raises(SignedOut):
        account.web_token()
    account.signed_in_with(auth.UserToken("AT-9", "RT-9", 4_102_444_800))
    assert account.signed_in and auth.load_refresh_token(tmp_path / "a.json") == "RT-9"
    assert account.web_token().gamertag == "Player One"
    assert transport.sent("POST", f"{LOGIN}/token") == []           # the new access token is used as it is
    account.sign_out()
    assert not account.signed_in and not (tmp_path / "a.json").exists()


def test_no_connection_is_an_http_error_with_status_zero():
    def offline(method, url, headers, body):
        raise HttpError(url, 0, "Name or service not known")
    with pytest.raises(HttpError) as raised:
        auth.start_sign_in(Client(offline))
    assert raised.value.status == 0 and "no connection" in str(raised.value)


def test_xbox_token_without_claims_is_an_auth_error():
    with pytest.raises(AuthError):
        auth.XboxToken.from_json({"Token": "x"})
    assert auth.XboxToken.from_json(xbox_token("T")).not_after > 0
