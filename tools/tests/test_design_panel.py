# SPDX-License-Identifier: GPL-3.0-or-later
"""The wiki's design panel hook: on the pages only while `mkdocs serve` runs, its address relative to each page, the
mock it keeps (a POST stores it, a GET returns it, anything but variables dropped), and a mock merged into a
stylesheet in place. No MkDocs needed."""

from __future__ import annotations

import importlib.util
import io
import json
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

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


SHEET = """/* The colors. */
:root {
  --a-primary: #5835CE;     /* Main color */
  --a-deep: #1e1340         /* Deep, no semicolon */
}

/* Header. */
:root {
  --a-header-bg: var(--a-deep);   /* Header background */
}

@media screen and (max-width: 44.9375em) {
  :root { --a-primary: #000000; }
}

.md-header { background: var(--a-header-bg); }
"""


def test_merge_writes_the_values_in_place():
    """Only the values change: the layout, the comments and the rest of the file stay; the same variable under
    @media is not the panel's and stays; a key no rule defines is not in the keys returned."""
    merged, defined = panel.merge(SHEET, {":root|--a-primary": "#ff8800", ":root|--a-deep": "#101010",
                                          ":root|--a-header-bg": "#ffffff", ".x|--y": "1"})
    assert merged == SHEET.replace("#5835CE;     /* Main", "#ff8800;     /* Main") \
        .replace("#1e1340         /* Deep", "#101010         /* Deep") \
        .replace("var(--a-deep);   /* Header", "#ffffff;   /* Header")
    assert "#000000" in merged
    assert defined == {":root|--a-primary", ":root|--a-deep", ":root|--a-header-bg"}
    assert panel.merge(SHEET, {}) == (SHEET, defined)


def test_the_panels_merge_is_pythons(tmp_path):
    """Copy stylesheet in the browser and tools/apply_design.py give the same file: the panel's topRules() and
    merged() run in Node.js on the fixture above, against merge() here. Skipped where Node.js is not installed
    (on Bazzite: brew install node)."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    js = (SUITE / "tools" / "mkdocs" / "design_panel.js").read_text(encoding="utf-8")
    functions = [re.search(rf"\n  function {name}\(.*?\n  \}}\n", js, re.S).group() for name in ("topRules", "merged")]
    values = {":root|--a-primary": "#ff8800", ":root|--a-deep": "#101010", ":root|--a-header-bg": "#ffffff"}
    script = tmp_path / "merge.js"
    script.write_text(f"const mock = {{values: {json.dumps(values)}}};\n" + "".join(functions) +
                      f"\nconst parsed = topRules({json.dumps(SHEET)});\n"
                      "process.stdout.write(merged({text: parsed.text, rules: parsed.rules}));\n", encoding="utf-8")
    result = subprocess.run([node, str(script)], capture_output=True, text=True, check=True)
    assert result.stdout == panel.merge(SHEET, values)[0]


def test_the_panel_offers_both_copies():
    js = (SUITE / "tools" / "mkdocs" / "design_panel.js").read_text(encoding="utf-8")
    assert 'data-action="copy"' in js and 'data-action="copy-sheet"' in js and "function merged(" in js


def test_the_panel_keeps_its_own_colours_and_sizes():
    """A mock changes the site's variables and Material scales rem: the panel uses neither."""
    css = re.sub(r"/\*.*?\*/", "", (SUITE / "tools" / "mkdocs" / "design_panel.css").read_text(encoding="utf-8"),
                 flags=re.S)
    assert "var(--" not in css and not re.search(r"\d(rem|vmin)\b", css)
