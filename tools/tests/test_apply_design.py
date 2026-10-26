# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/apply_design.py: the mock beside a wiki's mkdocs.yml is written into the wiki's own stylesheets in place,
then emptied with a new version so open pages drop it; a variable no stylesheet defines is reported."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import apply_design  # noqa: E402

CSS = "/* Colours. */\n:root {\n  --w-primary: #112233;   /* Main */\n  --w-fg: #ffffff;        /* Text */\n}\n"


def wiki(tmp_path: Path, mock) -> Path:
    (tmp_path / "docs" / "stylesheets").mkdir(parents=True)
    (tmp_path / "docs" / "stylesheets" / "w.css").write_text(CSS, encoding="utf-8")
    (tmp_path / "mkdocs.yml").write_text("site_name: W\ndocs_dir: docs\nextra_css:\n  - stylesheets/w.css\n"
                                         "markdown_extensions:\n  - toc:\n      slugify: !!python/name:str\n",
                                         encoding="utf-8")
    if mock is not None:
        (tmp_path / ".design-mock.json").write_text(json.dumps(mock), encoding="utf-8")
    return tmp_path / "mkdocs.yml"


def test_the_mock_is_written_into_the_stylesheet_and_emptied(tmp_path):
    config = wiki(tmp_path, {"version": 5, "values": {":root|--w-primary": "#ff8800", ":root|--md-text-font": '"X"'}})
    written, leftover = apply_design.apply(config, tmp_path)
    assert written == [tmp_path / "docs" / "stylesheets" / "w.css"] and leftover == [":root|--md-text-font"]
    assert (tmp_path / "docs" / "stylesheets" / "w.css").read_text(encoding="utf-8") == \
        CSS.replace("#112233", "#ff8800")
    mock = json.loads((tmp_path / ".design-mock.json").read_text(encoding="utf-8"))
    assert mock["values"] == {} and mock["version"] > 5


def test_an_empty_or_missing_mock_changes_nothing(tmp_path):
    config = wiki(tmp_path, None)
    assert apply_design.apply(config, tmp_path) == ([], [])
    assert not (tmp_path / ".design-mock.json").exists()
    config = wiki(tmp_path / "two", {"version": 1, "values": {}})
    assert apply_design.apply(config, tmp_path / "two") == ([], [])
    assert (tmp_path / "two" / "docs" / "stylesheets" / "w.css").read_text(encoding="utf-8") == CSS


def test_main_names_the_files_it_wrote(tmp_path, capsys):
    config = wiki(tmp_path, {"version": 1, "values": {":root|--w-fg": "#000000"}})
    assert apply_design.main([str(config)]) == 0
    out = capsys.readouterr().out
    assert "wrote" in out and "w.css" in out and "left for you" not in out
    assert apply_design.main([str(config)]) == 0
    assert "nothing to apply" in capsys.readouterr().out
