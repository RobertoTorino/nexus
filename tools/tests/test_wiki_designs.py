# SPDX-License-Identifier: GPL-3.0-or-later
"""Every wiki (each mkdocs.yml) has a design of its own: no INHERIT, stylesheets only from its own docs folder, none
shared with another wiki, and every variable its stylesheets define labeled for the design panel (a comment before
the rule names its group, a comment after the variable says what it does)."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

SUITE = Path(__file__).resolve().parents[2]
WIKIS = [SUITE / "mkdocs.yml", *sorted(SUITE.glob("*/mkdocs.yml"))]


class Loader(yaml.SafeLoader):
    """mkdocs.yml with its !!python tags read as nothing: only the plain keys matter here."""


Loader.add_multi_constructor("tag:yaml.org,2002:python/", lambda loader, suffix, node: None)


def config(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=Loader)


def stylesheets(path: Path) -> list[Path]:
    data = config(path)
    docs = (path.parent / data.get("docs_dir", "docs")).resolve()
    return [(docs / sheet).resolve() for sheet in data.get("extra_css", [])]


def test_there_is_more_than_one_wiki():
    assert len(WIKIS) >= 2 and all(w.is_file() for w in WIKIS)


@pytest.mark.parametrize("wiki", WIKIS, ids=lambda p: p.relative_to(SUITE).as_posix())
def test_a_wiki_stands_on_its_own(wiki):
    text = wiki.read_text(encoding="utf-8")
    assert not re.search(r"^INHERIT:", text, re.M), "a wiki inherits no other wiki's config"
    data = config(wiki)
    docs = (wiki.parent / data.get("docs_dir", "docs")).resolve()
    assert data.get("extra_css"), "a wiki has a stylesheet of its own"
    for sheet in stylesheets(wiki):
        assert sheet.is_file() and sheet.is_relative_to(docs), f"{sheet} is not in {docs}"
    custom = data.get("theme", {}).get("custom_dir")
    if custom:
        assert (wiki.parent / custom).resolve().is_relative_to(wiki.parent.resolve())


def test_no_stylesheet_is_shared():
    seen = {}
    for wiki in WIKIS:
        for sheet in stylesheets(wiki):
            assert sheet not in seen, f"{sheet} is in {seen.get(sheet)} and {wiki}"
            seen[sheet] = wiki
    for wiki in WIKIS:                          # nor watched or hooked in from another wiki's config
        for other in WIKIS:
            if other == wiki:
                continue
            text = other.read_text(encoding="utf-8")
            for sheet in stylesheets(wiki):
                rel = Path(os.path.relpath(sheet.parent, other.parent)).as_posix()
                assert not re.search(rf"(^|[\s'\"]){re.escape(rel)}", text), f"{other} refers to {wiki}'s {rel}"


def variable_rules(css: str):
    """The top-level rules that define variables: (the comment before, selector, [(name, label)])."""
    code = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group()), css, flags=re.S)
    rules, depth, start, opened = [], 0, 0, 0
    for i, ch in enumerate(code):
        if ch == "{":
            depth += 1
            if depth == 1:
                opened = i
        elif ch == "}":
            depth -= 1
            if depth == 0:
                selector = code[start:opened].strip()
                body = code[opened + 1:i]
                head = code[start:opened]
                selector_at = start + len(head) - len(head.lstrip())
                before = re.findall(r"/\*((?:(?!\*/).)*)\*/\s*$", css[start:selector_at], re.S)
                found = []
                for m in re.finditer(r"(--[\w-]+)\s*:[^;]*;?", body):
                    end = opened + 1 + m.end()
                    line = css[end:css.find("\n", end)]
                    label = re.match(r"\s*/\*(.*?)\*/", line)
                    found.append((m.group(1), label.group(1).strip() if label else ""))
                if found and not selector.startswith("@"):
                    rules.append((before[0].strip() if before else "", selector, found))
                start = i + 1
    return rules


@pytest.mark.parametrize("wiki", WIKIS, ids=lambda p: p.relative_to(SUITE).as_posix())
def test_every_variable_is_labelled(wiki):
    for sheet in stylesheets(wiki):
        rules = variable_rules(sheet.read_text(encoding="utf-8"))
        assert rules, f"{sheet} defines no variables for the design panel"
        for title, selector, found in rules:
            assert title, f"{sheet}: the rule {selector} has no comment before it"
            for name, label in found:
                assert label, f"{sheet}: {name} in {selector} has no comment after it"


@pytest.mark.parametrize("wiki", WIKIS, ids=lambda p: p.relative_to(SUITE).as_posix())
def test_every_colour_is_a_variable(wiki):
    """A color written anywhere but in a variable could not be changed in the design panel."""
    for sheet in stylesheets(wiki):
        code = re.sub(r"/\*.*?\*/", "", sheet.read_text(encoding="utf-8"), flags=re.S)
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", code):
            if re.search(r"--[\w-]+\s*:", m.group(2)):
                continue
            fixed = re.findall(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla)\(", m.group(2))
            assert not fixed, f"{sheet}: {m.group(1).strip()} has the fixed colour {fixed[0]}"


def test_the_header_has_variables_of_its_own():
    """The header's background and text are what the panel changes for the header, in each wiki: the text is the
    name beside the icon (the wiki) or the links alone (the Nexus page, whose icon carries the name)."""
    for wiki in WIKIS:
        css = "\n".join(s.read_text(encoding="utf-8") for s in stylesheets(wiki))
        bg = re.search(r"(--[\w]+-header-bg)\s*:", css)
        fg = re.search(r"(--[\w]+-header-fg)\s*:", css)
        assert bg and fg, wiki
        assert re.search(rf"\.md-header[^{{]*\{{[^}}]*background: var\({bg.group(1)}\)", css)
        assert re.search(rf"\.md-header__(name|link) \{{[^}}]*color: var\({fg.group(1)}\)", css)
        assert not re.search(r"\.md-header__(name|link)[^{]*\{[^}]*color: #", css), "a fixed color in the header"
