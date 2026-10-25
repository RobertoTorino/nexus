# SPDX-License-Identifier: GPL-3.0-or-later
"""MkDocs hook: the Nexus page takes the wiki's stylesheet (its layout) from where it lives (docs/), without a copy."""

from __future__ import annotations

from pathlib import Path

from mkdocs.structure.files import File

WIKI_DOCS = Path(__file__).resolve().parents[1] / "docs"
SHARED = ["stylesheets/suite.css"]


def on_files(files, config):
    for uri in SHARED:
        files.append(File.generated(config, uri, abs_src_path=str(WIKI_DOCS / uri)))
    return files
