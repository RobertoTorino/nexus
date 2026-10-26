# SPDX-License-Identifier: GPL-3.0-or-later
"""Built-in tables: the setup screens and default values of a known BIOS release, so the app can name the settings
of the running board without a dump of its flash chip.

A table is gzipped JSON, made from a dump with `bc250-bios-reader --build-table DUMP`. It holds the form sets (as
hii.py reads them), the StdDefaults variables and the release's version and date."""

from __future__ import annotations

import base64
import gzip
import json
import re
from dataclasses import asdict
from pathlib import Path

from .hii import Condition, Form, FormSet, Option, Statement, VarStore

TABLES_DIR = Path(__file__).resolve().parent / "tables"
FORMAT = 1


def table_path(version: str, folder: Path = TABLES_DIR) -> Path:
    return folder / (re.sub(r"[^A-Za-z0-9._-]", "_", version) + ".json.gz")


def dump_table(version: str, date: str, formsets: list[FormSet], defaults: dict[tuple[str, str], bytes]) -> bytes:
    doc = {
        "format": FORMAT, "version": version, "date": date,
        "formsets": [asdict(fs) for fs in formsets],
        "defaults": [{"guid": g, "name": n, "data": base64.b64encode(d).decode()} for (g, n), d in defaults.items()],
    }
    return gzip.compress(json.dumps(doc, separators=(",", ":")).encode(), mtime=0)


def load_table(path: Path) -> tuple[str, str, list[FormSet], dict[tuple[str, str], bytes]]:
    """(version, date, form sets, defaults) of a table file."""
    doc = json.loads(gzip.decompress(path.read_bytes()))
    if doc.get("format") != FORMAT:
        raise ValueError(f"{path.name}: unknown table format {doc.get('format')}")
    defaults = {(d["guid"], d["name"]): base64.b64decode(d["data"]) for d in doc["defaults"]}
    return doc["version"], doc["date"], [_formset(fs) for fs in doc["formsets"]], defaults


def _formset(d: dict) -> FormSet:
    fs = FormSet(d["guid"], d["title"], d["help"], d["module"], sha256=d["sha256"])
    fs.varstores = {int(k): VarStore(**v) for k, v in d["varstores"].items()}
    fs.forms = [Form(f["id"], f["title"], [_statement(s) for s in f["statements"]]) for f in d["forms"]]
    return fs


def _statement(d: dict) -> Statement:
    d = dict(d)
    d["options"] = [Option(**o) for o in d["options"]]
    d["conditions"] = [Condition(c["kind"], [_term(e) for e in c["expr"]]) for c in d["conditions"]]
    return Statement(**d)


def _term(e: list) -> tuple:
    """JSON lists back to the tuples hii.py makes (eq_id_list keeps its values as a tuple too)."""
    return tuple(tuple(x) if isinstance(x, list) else x for x in e)
