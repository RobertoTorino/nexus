# SPDX-License-Identifier: GPL-3.0-or-later
"""The HTTPS calls to Microsoft's services, with JSON in and out. The transport is a function, so the tests give
recorded answers and never reach the network."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass

TIMEOUT = 20                                # s for one call
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# (method, url, headers, body) -> (status, body); never raises for an HTTP status, only for no connection
Transport = Callable[[str, str, Mapping[str, str], bytes | None], tuple[int, bytes]]


class HttpError(Exception):
    """A call that failed: no connection (status 0) or a status outside 200-299."""

    def __init__(self, url: str, status: int, body: bytes | str = b""):
        self.url = url
        self.status = status
        self.body = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
        host = urllib.parse.urlsplit(url).hostname or url
        super().__init__(f"{host}: no connection ({self.body})" if status == 0 else f"{host}: HTTP {status}")

    def json(self) -> dict:
        """The error's body as JSON ({} when it is none)."""
        try:
            data = json.loads(self.body)
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}


def urllib_transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read() or b""
    except (urllib.error.URLError, OSError) as error:
        reason = getattr(error, "reason", error)
        raise HttpError(url, 0, str(reason)) from error


@dataclass
class Response:
    status: int
    data: object                            # the body as JSON, or the text when it is not JSON, None when empty


class Client:
    def __init__(self, transport: Transport = urllib_transport):
        self.transport = transport

    def call(self, method: str, url: str, headers: Mapping[str, str] | None = None, *, json_body: object = None,
             form: Mapping[str, str] | None = None) -> Response:
        """One call: *json_body* goes as JSON, *form* as a form. Raises HttpError for a status outside
        200-299."""
        sent = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
        body = None
        if json_body is not None:
            body = json.dumps(json_body).encode()
            sent.setdefault("Content-Type", "application/json")
        elif form is not None:
            body = urllib.parse.urlencode(form).encode()
            sent["Content-Type"] = "application/x-www-form-urlencoded"
        status, raw = self.transport(method, url, sent, body)
        if not 200 <= status <= 299:
            raise HttpError(url, status, raw)
        text = raw.decode("utf-8", "replace").strip()
        if not text:
            return Response(status, None)
        try:
            return Response(status, json.loads(text))
        except ValueError:
            return Response(status, text)

    def get(self, url: str, headers: Mapping[str, str] | None = None) -> Response:
        return self.call("GET", url, headers)

    def post(self, url: str, headers: Mapping[str, str] | None = None, **kwargs) -> Response:
        return self.call("POST", url, headers, **kwargs)
