# SPDX-License-Identifier: GPL-3.0-or-later
"""The wiki's design panel hook: on the pages only while `mkdocs serve` runs, its address relative to each page, and
the mock it keeps (a POST stores it, a GET returns it, anything but variables dropped). No MkDocs needed."""

from __future__ import annotations

import importlib.util
import io
import json
import re
from pathlib import Path
from types import SimpleNamespace

SUITE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("design_panel", SUITE / "tools" / "mkdocs" / "design_panel.py")
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)

PAGE = "<html><body><p>Page</p></body></html>"
CONFIG = SimpleNamespace(site_name="BC250 Bazzite Suite", docs_dir=str(SUITE / "docs"),
                         extra_css=["stylesheets/suite.css"])


def test_only_while_serving():
    page = SimpleNamespace(url="design/")
    panel.on_startup("build", dirty=False)
    assert panel.on_post_page(PAGE, page, CONFIG) == PAGE
    panel.on_startup("serve", dirty=False)
    try:
        output = panel.on_post_page(PAGE, page, CONFIG)
    finally:
        panel.on_startup("build", dirty=False)
    assert output.index("window.__designPanel") < output.index("</body>")
    assert '"endpoint": "../__design__"' in output and '"sheets": ["stylesheets/suite.css"]' in output
    assert '"site": "BC250 Bazzite Suite"' in output and '"files": ["docs/stylesheets/suite.css"]' in output


def test_the_panel_names_the_files_of_each_wiki():
    """Copy CSS goes to the wiki's own stylesheet: the panel says which, as a path in the checkout."""
    nexus = SimpleNamespace(docs_dir=str(SUITE / "nexus" / "docs"), extra_css=["stylesheets/nexus.css"])
    assert panel.source_files(nexus) == ["nexus/docs/stylesheets/nexus.css"]
    assert panel.source_files(CONFIG) == ["docs/stylesheets/suite.css"]


def test_the_address_is_relative_to_the_page():
    assert panel.endpoint_for("") == "__design__"
    assert panel.endpoint_for("design/") == "../__design__"
    assert panel.endpoint_for("apps/check/") == "../../__design__"
    assert panel.endpoint_for("404.html") == "__design__"


def call(app, method, path, body=b""):
    seen = {}
    environ = {"PATH_INFO": path, "REQUEST_METHOD": method, "CONTENT_LENGTH": str(len(body)),
               "wsgi.input": io.BytesIO(body)}
    result = b"".join(app(environ, lambda status, headers: seen.update(status=status)))
    return seen["status"], result


def test_the_mock_is_stored_and_returned(tmp_path):
    mock_file = tmp_path / ".design-mock.json"
    inner = lambda environ, start_response: (start_response("200 OK", []), [b"page"])[1]     # noqa: E731
    app = panel.app(inner, "/nexus/", mock_file)
    assert call(app, "GET", "/nexus/design/") == ("200 OK", b"page")                         # the site itself
    assert json.loads(call(app, "GET", "/nexus/__design__")[1]) == {"version": 0, "values": {}}
    sent = {"version": 7, "values": {":root|--suite-primary": "#ff8800", "not a variable": "x", ":root|--n": 3}}
    status, body = call(app, "POST", "/nexus/__design__", json.dumps(sent).encode())
    expected = {"version": 7, "values": {":root|--suite-primary": "#ff8800"}}
    assert status == "200 OK" and json.loads(body) == expected
    assert panel.load(mock_file) == expected                                                # outlasts a restart


def test_a_bad_post_changes_nothing(tmp_path):
    mock_file = tmp_path / ".design-mock.json"
    app = panel.app(lambda e, s: [], "/", mock_file)
    assert call(app, "POST", "/__design__", b"not json")[0] == "400 Bad Request"
    assert call(app, "POST", "/__design__", b"")[0] == "413 Content Too Large"
    assert not mock_file.exists()


def test_screens_shows_pc_laptop_and_handheld_sizes(tmp_path):
    app = panel.app(lambda e, s: [], "/nexus/", tmp_path / ".design-mock.json")
    status, body = call(app, "GET", "/nexus/__design__/screens")
    html = body.decode("utf-8")
    assert status == "200 OK" and "<iframe" not in html                    # the frames are made by its script
    sizes = set(re.findall(r"w: (\d+), h: (\d+)", html))
    assert ("1280", "720") in sizes and "ASUS ROG Xbox Ally X" in html      # 1920 x 1080 at 150 %
    assert all(int(w) >= 1280 for w, _ in sizes)                            # no phone sizes
    assert not (tmp_path / ".design-mock.json").exists()


def test_the_panel_keeps_its_own_colours_and_sizes():
    """A mock changes the site's variables and Material scales rem: the panel uses neither."""
    css = re.sub(r"/\*.*?\*/", "", (SUITE / "tools" / "mkdocs" / "design_panel.css").read_text(encoding="utf-8"),
                 flags=re.S)
    assert "var(--" not in css and not re.search(r"\d(rem|vmin)\b", css)
