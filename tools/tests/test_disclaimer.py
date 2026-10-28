# SPDX-License-Identifier: GPL-3.0-or-later
"""The disclaimer hook: one text for every wiki (owner, 28-10-2026), set as config.extra.disclaimer and put in
place of its marker in a page. Every wiki in the repository lists the hook, and each home page's footer shows the
text from it, not a copy of its own. No MkDocs needed."""

from __future__ import annotations

import importlib.util
import re
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
        # The home page ends with the Disclaimer section, its text the hook's (owner, 28-10-2026: every disclaimer
        # looks the same, on every home page to come too).
        index = (config.parent / "docs" / "index.md").read_text(encoding="utf-8")
        assert re.search(rf"^## Disclaimer\n\n{re.escape(disclaimer.MARKER)}$", index, re.M), config
        assert "not affiliated" not in index, config
