#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write a wiki's design mock into its stylesheets:

    python3 tools/apply_design.py                     # every wiki (mkdocs.yml, */mkdocs.yml) that has a mock
    python3 tools/apply_design.py nexus/mkdocs.yml    # one wiki

The mock is what the design panel changed while `mkdocs serve` ran: .design-mock.json beside the wiki's mkdocs.yml.
Each changed variable is written in place into the stylesheet that defines it (the wiki's own, extra_css): the file
stays as it is, comments and all, only the values change. The mock is then emptied, as the panel's Reset all does,
so the pages show the stylesheet alone. A variable no stylesheet defines (a font, set in mkdocs.yml) is reported
and left for you."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent / "mkdocs"))
import design_panel  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class Loader(yaml.SafeLoader):
    """mkdocs.yml with its !!python tags read as nothing: only docs_dir and extra_css matter here."""


Loader.add_multi_constructor("tag:yaml.org,2002:python/", lambda loader, suffix, node: None)


def stylesheets(config: Path) -> list[Path]:
    data = yaml.load(config.read_text(encoding="utf-8"), Loader=Loader) or {}
    docs = config.parent / data.get("docs_dir", "docs")
    return [docs / sheet for sheet in data.get("extra_css", [])]


def apply(config: Path, root: Path = ROOT) -> tuple[list[Path], list[str]]:
    """The mock beside *config* written into its stylesheets: the files changed, and the mock's keys no stylesheet
    defines. An empty mock changes nothing."""
    mock_file = config.parent / design_panel.MOCK_FILE
    values = design_panel.load(mock_file)["values"]
    if not values:
        return [], []
    written, defined = [], set()
    for sheet in stylesheets(config):
        css = sheet.read_text(encoding="utf-8")
        merged, keys = design_panel.merge(css, values)
        defined |= keys
        if merged != css:
            sheet.write_text(merged, encoding="utf-8", newline="\n")
            written.append(sheet)
    leftover = sorted(k for k in values if k not in defined)
    mock_file.write_text(json.dumps({"version": int(time.time() * 1000), "values": {}}) + "\n", encoding="utf-8")
    return written, leftover


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", nargs="*", type=Path, help="a wiki's mkdocs.yml (default: every wiki with a mock)")
    args = parser.parse_args(argv)
    configs = args.config or [c for c in [ROOT / "mkdocs.yml", *sorted(ROOT.glob("*/mkdocs.yml"))]
                              if (c.parent / design_panel.MOCK_FILE).is_file()]
    if not configs:
        print("no wiki has a mock (.design-mock.json beside its mkdocs.yml)")
        return 0
    for config in configs:
        written, leftover = apply(config.resolve())
        shown = config.resolve().relative_to(ROOT).as_posix() if config.resolve().is_relative_to(ROOT) else config
        if not written and not leftover:
            print(f"{shown}: nothing to apply")
        for sheet in written:
            print(f"{shown}: wrote {sheet.relative_to(ROOT).as_posix() if sheet.is_relative_to(ROOT) else sheet}")
        for key in leftover:
            print(f"{shown}: not in a stylesheet, left for you: {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
