# SPDX-License-Identifier: GPL-3.0-or-later
"""MkDocs hook: a design panel on every page while `mkdocs serve` runs, never in a build.

The panel (design_panel.js and .css, put in each page) lists every CSS variable the site's own stylesheets
(extra_css) define, with a color picker, a slider or a text field, and shows a change at once. Its groups and labels
are the stylesheet's comments: the one before a rule names the group, the one after a variable on its line says what
it does. Each wiki has stylesheets of its own, so a change is to that wiki alone; the panel names the wiki and the
files its changes go in. The server keeps the
mock at <the config's folder>/.design-mock.json (git ignores it) and answers at <the site's path>/__design__: a POST
stores it, a GET returns it. Every open page asks once a second, so a phone, the board and the TV on the same server
all show the same mock. Copy CSS gives the changed variables to paste into the stylesheet; Copy stylesheet gives the
whole stylesheet with the changes written in, to paste over the file (merge() below does the same for
tools/apply_design.py). Screens opens <the site's path>/__design__/screens (design_screens.html): the page at the
sizes of PC, laptop and handheld screens, where the panel only applies the mock."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
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


VARIABLE = re.compile(r"(--[\w-]+)\s*:([^;]*);?")


def rules(css: str) -> list[tuple[str, int, str]]:
    """The top-level rules of a stylesheet, as the panel reads them: (selector, where its body starts, the body with
    the comments blanked out, so a position in it is a position in the text)."""
    code = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group()), css, flags=re.S)
    out, depth, start, opened = [], 0, 0, 0
    for i, ch in enumerate(code):
        if ch == "{":
            depth += 1
            if depth == 1:
                opened = i
        elif ch == "}":
            depth -= 1
            if depth == 0:
                out.append((" ".join(code[start:opened].split()), opened + 1, code[opened + 1:i]))
                start = i + 1
    return out


def merge(css: str, values: dict[str, str]) -> tuple[str, set[str]]:
    """*css* with the mock's *values* ("selector|--name": value) written in place of the variables' own: the file
    as it is, comments and all, only those values changed. Also returns the keys the stylesheet defines."""
    edits, defined = [], set()
    for selector, body_start, body in rules(css):
        if selector.startswith("@"):
            continue
        for m in VARIABLE.finditer(body):
            key = f"{selector}|{m.group(1)}"
            defined.add(key)
            if key in values:                       # the value only, not the blank after it (a comment, the line's end)
                end = body_start + m.start(2) + len(m.group(2).rstrip())
                edits.append((body_start + m.start(2), end, " " + values[key]))
    for start, end, text in sorted(edits, reverse=True):
        css = css[:start] + text + css[end:]
    return css, defined


def endpoint_for(page_url: str) -> str:
    """The panel's address relative to a page: a page at apps/check/ reaches it at ../../__design__."""
    return "../" * page_url.count("/") + ENDPOINT


def source_files(config) -> list[str]:
    """The site's stylesheets as paths in the checkout (docs/stylesheets/suite.css): where a change is pasted."""
    docs = Path(config.docs_dir).resolve()
    paths = []
    for sheet in config.extra_css:
        path = docs / str(sheet)
        paths.append(path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(sheet))
    return paths


def snippet(page_url: str, config) -> str:
    """The panel's style, settings and script, for the end of a page's <body>."""
    settings = json.dumps({"endpoint": endpoint_for(page_url), "site": config.site_name,
                           "sheets": [str(s) for s in config.extra_css], "files": source_files(config)})
    settings = settings.replace("</", "<\\/")
    css = (HERE / "design_panel.css").read_text(encoding="utf-8")
    js = (HERE / "design_panel.js").read_text(encoding="utf-8")
    return f"<style>{css}</style>\n<script>window.__designPanel = {settings};</script>\n<script>{js}</script>\n"


def on_post_page(output, page, config):
    if not _serving or "</body>" not in output:
        return output
    head, _, tail = output.rpartition("</body>")
    return head + snippet(page.url, config) + "</body>" + tail


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
