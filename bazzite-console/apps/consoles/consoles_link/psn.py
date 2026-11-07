# SPDX-License-Identifier: AGPL-3.0-only
"""The PSN account ID through the PlayStation sign-in (the reference's scripts/psn-account-id.py and
gui/src/psnaccountid.cpp, after grill2010): PlayStation does not show the account ID anywhere, but the sign-in for
the Remote Play app tells it.

1. The browser opens the PlayStation sign-in page for the Remote Play client. After signing in, the sign-in sends
   the browser to remoteplay.dl.playstation.net/remoteplay/redirect?code=..., a page that only says "redirect".
2. That code (short-lived, usable once) is exchanged for an access token at the PSN token service.
3. The token's details hold user_id, the account ID; registration sends it as 8 bytes, little-endian.

Only the account ID is kept: the token is used once and dropped. The scope is the narrowest the reference uses
(psn:clientapp, its script's), enough for the account ID."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

# The official Remote Play client for Windows, as in the reference.
CLIENT_ID = "ba495a24-818c-472b-b12d-ff231c1b5745"
CLIENT_SECRET = "mvaiZkRsAsI1IBkY"
AUTH_BASE = "https://auth.api.sonyentertainmentnetwork.com/2.0/oauth"
REDIRECT_URI = "https://remoteplay.dl.playstation.net/remoteplay/redirect"
SCOPE = "psn:clientapp"
TIMEOUT = 15.0


class PsnError(Exception):
    pass


def login_url(auth_base: str = AUTH_BASE) -> str:
    """The PlayStation sign-in page, the address exactly as the reference's script builds it."""
    return (f"{auth_base}/authorize?service_entity=urn:service-entity:psn&response_type=code&client_id={CLIENT_ID}"
            f"&redirect_uri={REDIRECT_URI}&scope={SCOPE}&request_locale=en_US&ui=pr&service_logo=ps"
            "&layout_type=popup&smcid=remoteplay&prompt=always&PlatformPrivacyWs1=minimal&")


def code_from_redirect(text: str) -> str:
    """The code from the address the sign-in redirected to (the whole address pasted, or only the code)."""
    text = text.strip()
    if not text:
        raise PsnError("Paste the address of the page that says \"redirect\".")
    if "?" not in text and "=" not in text and "/" not in text:
        return text                                     # the code by itself
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(text).query)
    if query.get("error"):
        raise PsnError(f"The PlayStation sign-in reported: {query.get('error_description', query['error'])[0]}.")
    code = (query.get("code") or [""])[0]
    if not code:
        raise PsnError("That address has no code in it. Copy the address of the page that says \"redirect\", "
                       "after signing in.")
    return code


@dataclass
class Account:
    account_id: bytes                   # 8 bytes, little-endian, as registration sends it
    online_id: str = ""

    @property
    def number(self) -> int:
        return int.from_bytes(self.account_id, "little")

    @property
    def code(self) -> str:
        """The form the reference shows: base64 of the 8 bytes."""
        return base64.b64encode(self.account_id).decode()


def _auth_header() -> str:
    return "Basic " + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()


def _call(request: urllib.request.Request, what: str) -> dict:
    request.add_header("Authorization", _auth_header())
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read().decode("utf-8"))
        except (ValueError, OSError):
            body = {}
        if body.get("error") == "invalid_grant":
            raise PsnError("PSN did not accept the code: it works only once and only for a few minutes. Sign in "
                           "again and paste the new address.") from error
        detail = body.get("error_description") or body.get("error") or error.reason
        raise PsnError(f"PSN refused the {what} (HTTP {error.code}: {detail}).") from error
    except (urllib.error.URLError, OSError) as error:
        raise PsnError(f"The PSN sign-in service could not be reached: {getattr(error, 'reason', error)}.") from error
    except ValueError as error:
        raise PsnError(f"The PSN answer to the {what} is not readable.") from error


def account_id(code: str, auth_base: str = AUTH_BASE) -> Account:
    body = urllib.parse.urlencode({"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI})
    token = _call(urllib.request.Request(f"{auth_base}/token", data=body.encode(), method="POST",
                                         headers={"Content-Type": "application/x-www-form-urlencoded"}),
                  "sign-in code")
    access_token = token.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise PsnError("The PSN answer has no access token.")
    info = _call(urllib.request.Request(f"{auth_base}/token/{urllib.parse.quote(access_token, safe='')}"),
                 "account request")
    user_id = str(info.get("user_id", ""))
    if not user_id.isdigit() or not 0 < int(user_id) < 1 << 64:
        raise PsnError("The PSN answer has no account ID.")
    return Account(int(user_id).to_bytes(8, "little"), str(info.get("online_id", "")))
