# SPDX-License-Identifier: GPL-3.0-or-later
"""MkDocs hook: a design panel on every page while `mkdocs serve` runs, never in a build.

The panel (design_panel.js and .css, put in each page) lists every CSS variable the site's own stylesheets
(extra_css) define, with a colour picker, a slider or a text field, and shows a change at once. The server keeps the
mock at <the config's folder>/.design-mock.json (git ignores it) and answers at <the site's path>/__design__: a POST
stores it, a GET returns it. Every open page asks once a second, so a phone, the board and the TV on the same server
all show the same mock. Copy CSS gives the changed variables to paste into the stylesheet. Screens opens
<the site's path>/__design__/screens (design_screens.html): the page at the sizes of PC, laptop and handheld screens,
where the panel only applies the mock."""

from __future__ import annotations

import json
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENDPOINT = "__design__"
MOCK_FILE = ".design-mock.json"
MAX_BODY = 256 * 1024                   # a mock is a few hundred variables at most

_serving = False
_mock_path: Path | None = None
_lock = threading.Lock()


def on_startup(command, dirty):
    global _serving
    _serving = command == "serve"


def on_config(config):
    global _mock_path
    _mock_path = Path(config.config_file_path).resolve().parent / MOCK_FILE
    return config


def endpoint_for(page_url: str) -> str:
    """The panel's address relative to a page: a page at apps/check/ reaches it at ../../__design__."""
    return "../" * page_url.count("/") + ENDPOINT


def snippet(page_url: str, sheets: list[str]) -> str:
    """The panel's style, settings and script, for the end of a page's <body>."""
    settings = json.dumps({"endpoint": endpoint_for(page_url), "sheets": [str(s) for s in sheets]}).replace("</", "<\\/")
    css = (HERE / "design_panel.css").read_text(encoding="utf-8")
    js = (HERE / "design_panel.js").read_text(encoding="utf-8")
    return f"<style>{css}</style>\n<script>window.__designPanel = {settings};</script>\n<script>{js}</script>\n"


def on_post_page(output, page, config):
    if not _serving or "</body>" not in output:
        return output
    head, _, tail = output.rpartition("</body>")
    return head + snippet(page.url, list(config.extra_css)) + "</body>" + tail


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 0, "values": {}}
    return clean(data)


def clean(data) -> dict:
    """A mock as the panel sends it: a version and string values by "selector|--name"; anything else dropped."""
    if not isinstance(data, dict):
        return {"version": 0, "values": {}}
    values = data.get("values") if isinstance(data.get("values"), dict) else {}
    try:
        version = int(data.get("version") or 0)
    except (TypeError, ValueError):
        version = 0
    return {"version": version,
            "values": {k: v for k, v in values.items() if isinstance(k, str) and "|--" in k and isinstance(v, str)}}


def app(inner, mount_path: str, path: Path):
    """*inner* (the server's own WSGI app) with the panel's address in front of it."""
    address = mount_path + ENDPOINT

    def serve(environ, start_response):
        if environ.get("PATH_INFO") == address + "/screens":
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "no-store")])
            return [(HERE / "design_screens.html").read_bytes()]
        if environ.get("PATH_INFO") != address:
            return inner(environ, start_response)
        if environ.get("REQUEST_METHOD") == "POST":
            try:
                length = int(environ.get("CONTENT_LENGTH") or 0)
            except ValueError:
                length = 0
            if not 0 < length <= MAX_BODY:
                start_response("413 Content Too Large", [("Content-Type", "text/plain")])
                return [b"too large"]
            try:
                mock = clean(json.loads(environ["wsgi.input"].read(length)))
            except ValueError:
                start_response("400 Bad Request", [("Content-Type", "text/plain")])
                return [b"not JSON"]
            with _lock:
                path.write_text(json.dumps(mock, indent=1) + "\n", encoding="utf-8")
        with _lock:
            body = json.dumps(load(path)).encode()
        start_response("200 OK", [("Content-Type", "application/json"), ("Cache-Control", "no-store")])
        return [body]

    return serve


def on_serve(server, config, builder):
    server.set_app(app(server.get_app(), server.mount_path, _mock_path))
    return server
