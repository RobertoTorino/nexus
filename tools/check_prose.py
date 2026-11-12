#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scores how hard the repository's text is to read, and lists the files that need work most:

    python3 tools/check_prose.py                      # every wiki, README and window text, worst first
    python3 tools/check_prose.py bc250-bazzite/docs   # only what is under these files or folders
    python3 tools/check_prose.py --details FILE       # every finding in the file, with its line
    python3 tools/check_prose.py --base origin/main   # fails when a file scores worse than it did at that commit

It reads the Markdown files (the wikis, the READMEs, the root's documents) and the text the apps show: every string
of four words or more in the Python code that is not a docstring or a test. The CHANGELOGs and MIGRATION.md are
history and stay out. Code blocks, inline code and link addresses are not text.

A finding is one of:
    long          a sentence of more than 30 words
    semicolon     a semicolon that joins two sentences
    colon         a colon after four words or more that goes on with the sentence (not one before a command)
    parenthesis   a parenthesis with more than four words in it
    word          a word from the list below (British spelling; "manual" for the wiki)

A file's score is its findings per 1000 words. Files of under 100 words come last: one finding there says little.
The score points at dense text; it does not say the text is good."""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LONG_WORDS = 30
ASIDE_WORDS = 4
LEAD_WORDS = 4                          # a colon after fewer words ends a name: "Turn on…: ..."
SMALL_FILE = 100
SKIP_NAMES = {"CHANGELOG", "MIGRATION.md", "LICENSE"}
SKIP_PARTS = {"tests", "node_modules", "site", "__pycache__"}
STRING_WORDS = 4                        # a shorter string is a label, not a sentence

# The words not to write, with what to write instead (CLAUDE.md: American English, and the manual is "the wiki").
WORDS = {
    "colour": "color", "colours": "colors", "coloured": "colored", "grey": "gray", "centre": "center",
    "centred": "centered", "cancelled": "canceled", "cancelling": "canceling", "licence": "license",
    "catalogue": "catalog", "labelled": "labeled", "behaviour": "behavior", "favourite": "favorite",
    "manual": "wiki (unless it means done by hand)",
}
_WORD = re.compile(r"\b(" + "|".join(WORDS) + r")\b", re.I)
_MANUAL_BY_HAND = re.compile(r"\bmanual (value|mode|fan|speed|step|setting|\d)|\bmanual\b[^.]*%", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(*\[])")
_FENCE = re.compile(r"^\s*(```|~~~)")
_SKIP_LINE = re.compile(r"^\s*(#|<!--|!\[|\[!\[|!!!|\?\?\?|\|\s*-{3}|-{3,}\s*$|<[a-z/])")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
_LEAD = re.compile(r"^\*\*[^*]{1,80}\*\*:?\s*")     # a list item's bold name, with its colon
_MID_COLON = re.compile(r":\s+(?=[a-z*\[])")
_NOT_PROSE = {"code", "value"}          # what plain() and strings() leave of inline code and an f-string's value
_PAREN = re.compile(r"\(([^()]*)\)")


@dataclass
class Finding:
    line: int
    kind: str
    text: str


@dataclass
class Score:
    path: str
    words: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def per_1000(self) -> float:
        return 1000 * len(self.findings) / self.words if self.words else 0.0


def plain(text: str) -> str:
    """Markdown or rich text without what is not prose: inline code, link addresses, tags, emphasis marks."""
    text = re.sub(r"`[^`]*`", "code", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\{[^}]*\}", "", text)


def check_passage(passage: str, line: int, score: Score) -> None:
    """One paragraph, list item, table cell or window text."""
    passage = _LEAD.sub("", plain(passage).strip())
    words = len(passage.split())
    if not words:
        return
    score.words += words
    for sentence in _SENTENCE_END.split(passage):
        count = len(sentence.split())
        short = sentence if len(sentence) <= 90 else sentence[:87] + "..."
        if count > LONG_WORDS:
            score.findings.append(Finding(line, "long", f"{count} words: {short}"))
        for _ in range(sentence.count(";")):
            score.findings.append(Finding(line, "semicolon", short))
        bare = sentence.replace("**", "")
        for match in _MID_COLON.finditer(bare):
            after = bare[match.end():].split(None, 1)[0].strip(".,")
            if len(bare[:match.start()].split()) >= LEAD_WORDS and after not in _NOT_PROSE:
                score.findings.append(Finding(line, "colon", short))
        for inside in _PAREN.findall(sentence):
            if len(inside.split()) > ASIDE_WORDS:
                score.findings.append(Finding(line, "parenthesis", f"({inside})"[:90]))
        for match in _WORD.finditer(sentence):
            word = match.group(1).lower()
            if word == "manual" and _MANUAL_BY_HAND.search(sentence):
                continue
            score.findings.append(Finding(line, "word", f"{match.group(1)}: write {WORDS[word]}"))


def score_markdown(path: str, text: str) -> Score:
    score = Score(path)
    passage: list[str] = []
    start = 0
    fenced = False

    def flush() -> None:
        if passage:
            check_passage(" ".join(passage), start, score)
            passage.clear()

    for number, line in enumerate(text.splitlines(), 1):
        if _FENCE.match(line):
            flush()
            fenced = not fenced
            continue
        if fenced:
            continue
        if not line.strip() or _SKIP_LINE.match(line):
            flush()
            continue
        if line.lstrip().startswith("|"):                       # a table row: every cell by itself
            flush()
            for cell in line.strip().strip("|").split("|"):
                check_passage(cell, number, score)
            continue
        bullet = _BULLET.match(line)
        if bullet:
            flush()
            line = line[bullet.end():]
        if not passage:
            start = number
        passage.append(line.strip())
    flush()
    return score


def strings(tree: ast.AST):
    """The strings a program shows: every literal that is not a docstring, an f-string's values as one word."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    inside = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                inside.add(id(value))
                parts.append(value.value if isinstance(value, ast.Constant) and isinstance(value.value, str)
                             else "value")
            yield node.lineno, "".join(parts)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
                and id(node) not in inside):
            yield node.lineno, node.value


def score_python(path: str, text: str) -> Score:
    score = Score(path)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return score
    for line, value in sorted(strings(tree)):
        if len(value.split()) >= STRING_WORDS and value[:1].isupper() and "\n    " not in value:
            for passage in re.split(r"\n\s*\n|<br><br>", value):
                check_passage(passage.replace("<br>", " "), line, score)
    return score


def score_text(path: str, text: str) -> Score:
    return score_python(path, text) if path.endswith(".py") else score_markdown(path, text)


def wanted(path: str) -> bool:
    parts = Path(path).parts
    if parts[-1] in SKIP_NAMES or SKIP_PARTS.intersection(parts) or parts[0] in (".github", ".claude"):
        return False
    if path.endswith(".md"):
        return parts[-1] != "CLAUDE.md"
    return path.endswith(".py") and parts[0] != "tools" and "tools" not in parts[:2]


def tracked(root: Path, targets: list[str]) -> list[str]:
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "--", *targets], cwd=root,
                         capture_output=True, text=True, check=True).stdout
    return sorted(path for path in out.splitlines() if wanted(path) and (root / path).is_file())


def at_base(root: Path, base: str, path: str) -> str | None:
    result = subprocess.run(["git", "show", f"{base}:{path}"], cwd=root, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    return result.stdout if result.returncode == 0 else None


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description="Scores how hard the repository's text is to read.")
    parser.add_argument("paths", nargs="*", help="files or folders, from the repository root (default: everything)")
    parser.add_argument("--details", action="store_true", help="list every finding with its line")
    parser.add_argument("--base", help="fail when a file scores worse than at this commit")
    parser.add_argument("--top", type=int, default=0, help="show only the worst N files")
    args = parser.parse_args(argv)

    scores = []
    for path in tracked(root, args.paths):
        scores.append(score_text(path, (root / path).read_text(encoding="utf-8", errors="replace")))
    scores = [s for s in scores if s.words]
    scores.sort(key=lambda s: (s.words < SMALL_FILE, -s.per_1000, s.path))

    worse = []
    if args.base:
        for score in scores:
            old_text = at_base(root, args.base, score.path)
            if old_text is None:
                continue
            old = score_text(score.path, old_text)
            if score.per_1000 > old.per_1000 + 0.05 and len(score.findings) > len(old.findings):
                worse.append((score, old))
        for score, old in worse:
            print(f"{score.path}: {old.per_1000:.1f} -> {score.per_1000:.1f} findings per 1000 words "
                  f"({len(old.findings)} -> {len(score.findings)})")
        if worse:
            print(f"\n{len(worse)} file(s) read worse than at {args.base}. See them with: "
                  "python3 tools/check_prose.py --details FILE")
            return 1
        print(f"No file reads worse than at {args.base}.")
        return 0

    shown = scores[:args.top] if args.top else scores
    print(f"{'score':>7} {'findings':>8} {'words':>7}  file")
    for score in shown:
        print(f"{score.per_1000:7.1f} {len(score.findings):8d} {score.words:7d}  {score.path}")
        if args.details:
            for finding in sorted(score.findings, key=lambda f: (f.line, f.kind)):
                print(f"{'':25}{finding.line}: {finding.kind}: {finding.text}")
    words = sum(s.words for s in scores)
    findings = sum(len(s.findings) for s in scores)
    print(f"\n{len(scores)} files, {words} words, {findings} findings"
          + (f" ({1000 * findings / words:.1f} per 1000 words)" if words else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
