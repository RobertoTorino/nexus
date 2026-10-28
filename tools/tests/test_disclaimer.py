# SPDX-License-Identifier: GPL-3.0-or-later
"""The disclaimer hook: one text for every wiki (owner, 28-10-2026), set as config.extra.disclaimer and put in
place of its marker in a page. Every wiki in the repository lists the hook, and each home page's footer shows the
text from it, not a copy of its own. No MkDocs needed."""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("disclaimer", ROOT / "tools" / "mkdocs" / "disclaimer.py")
disclaimer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(disclaimer)


def test_sets_the_text_and_fills_the_marker():
    config = SimpleNamespace(extra={})
    assert disclaimer.on_config(config).extra["disclaimer"] == disclaimer.DISCLAIMER
    page = f"## Disclaimer\n\n{disclaimer.MARKER}\n\nAfter."
    assert disclaimer.on_page_markdown(page, None, config, None) == f"## Disclaimer\n\n{disclaimer.DISCLAIMER}\n\nAfter."
    assert disclaimer.on_page_markdown("No marker.", None, config, None) == "No marker."


def test_every_disclaimer_has_the_same_text():
    """Every Disclaimer section in the repository's Markdown is the hook's text (owner, 28-10-2026: all disclaimers
    look the same): the marker on a wiki's home page, written out word for word everywhere else. A README is shown by
    GitHub without the hook, and an app's chapter ships as its MANUAL.md as it is (tools/stage_app.py)."""
    tracked = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    found = 0
    for name in tracked:
        path = ROOT / name
        if not path.is_file():
            continue
        for section in re.finditer(r"^## Disclaimer\n\n(.*?)(?=\n## |\Z)", path.read_text(encoding="utf-8"),
                                   re.S | re.M):
            text = " ".join(re.sub(r"(\s*</(div|section)>)+\s*$", "", section[1]).split())   # a home page's wrapping
            assert text in (disclaimer.DISCLAIMER, disclaimer.MARKER), name
            found += 1
    assert found and "README.md" in tracked


def test_every_wiki_uses_it():
    wikis = [p for p in ROOT.glob("*/mkdocs.yml")] + [p for p in ROOT.glob("*/*/mkdocs.yml")]
    assert wikis
    for config in wikis:
        hook = (ROOT / "tools" / "mkdocs" / "disclaimer.py").relative_to(ROOT).as_posix()
        assert re.search(rf"^\s+- (\.\./)+{re.escape(hook)}\b", config.read_text(encoding="utf-8"), re.M), config
        theme = re.search(r"^\s+custom_dir: (\S+)", config.read_text(encoding="utf-8"), re.M)
        home = config.parent / theme.group(1) / "home.html"
        if home.is_file():
            text = home.read_text(encoding="utf-8")
            assert "{{ config.extra.disclaimer }}" in text and "not affiliated" not in text, home
            # One disclaimer on the home page, the footer's, starting with a bold "Disclaimer:" (owner, 28-10-2026:
            # the page's own Disclaimer section above the footer showed the same text twice).
            assert "<strong>Disclaimer:</strong> {{ config.extra.disclaimer }}" in text, home
        index = (config.parent / "docs" / "index.md").read_text(encoding="utf-8")
        assert "## Disclaimer" not in index and disclaimer.MARKER not in index, config
        assert "not affiliated" not in index, config
