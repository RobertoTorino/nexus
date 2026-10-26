# SPDX-License-Identifier: GPL-3.0-or-later
"""The system software versions of every PlayStation, from data/<system>_systemsoftware.json (the files of the
Android app, unchanged). A file is a list of versions, a list of series (each with its entries), or an object with
a "series" list; an entry's keys are read as SystemSoftware.kt reads them."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import DATA_DIR


@dataclass(frozen=True)
class Page:
    title: str
    file: str


# In the order of the Android app's list.
PAGES = (Page("PlayStation 6 System Software", "ps6_systemsoftware.json"),
         Page("PlayStation 5 System Software", "ps5_systemsoftware.json"),
         Page("PlayStation Portal System Software", "psportal_systemsoftware.json"),
         Page("PlayStation 4 System Software", "ps4_systemsoftware.json"),
         Page("PlayStation 3 System Software", "ps3_systemsoftware.json"),
         Page("PlayStation Vita System Software", "psvita_systemsoftware.json"),
         Page("PlayStation Portable System Software", "psp_systemsoftware.json"),
         Page("PlayStation 2 System Software", "ps2_systemsoftware.json"),
         Page("PlayStation 1 System Software", "ps1_systemsoftware.json"))


@dataclass(frozen=True)
class Entry:
    version: str
    release_date: str
    size: str = ""
    model: str = ""
    region: str = ""
    region_code: str = ""
    color: str = ""
    notes: tuple[str, ...] = ()
    region_free: str = ""
    cdr_copies: str = ""
    av_direct_out: str = ""
    parallel_port: str = ""
    serial_port: str = ""

    @property
    def specs(self) -> list[tuple[str, str]]:
        """The hardware facts an entry may carry, in the order the Android app showed them."""
        pairs = (("Region Free", self.region_free), ("CD-R Copies", self.cdr_copies),
                 ("A/V Direct Out", self.av_direct_out), ("Parallel Port", self.parallel_port),
                 ("Serial Port", self.serial_port))
        return [(name, value) for name, value in pairs if value]


@dataclass(frozen=True)
class Series:
    id: str
    name: str
    entries: tuple[Entry, ...] = field(default_factory=tuple)

    @property
    def heading(self) -> str:
        return self.name.replace("_", " ")


def _text(item: dict, *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _entry(item: dict) -> Entry:
    raw_notes = item.get("notes")
    if isinstance(raw_notes, list):
        notes = tuple(str(n) for n in raw_notes if str(n).strip())
    elif isinstance(raw_notes, str) and raw_notes.strip():
        notes = (raw_notes,)
    else:
        notes = ()
    return Entry(version=_text(item, "version"), release_date=_text(item, "releaseDate", "release_date"),
                 size=_text(item, "size"), model=_text(item, "model"), region=_text(item, "region"),
                 region_code=_text(item, "region_code"), color=_text(item, "color"), notes=notes,
                 region_free=_text(item, "region_free"), cdr_copies=_text(item, "cdr_copies"),
                 av_direct_out=_text(item, "av_direct_out"), parallel_port=_text(item, "parallel_port"),
                 serial_port=_text(item, "serial_port"))


def _series_list(items: list) -> list[Series]:
    return [Series(_text(s, "id"), _text(s, "name"), tuple(_entry(e) for e in s.get("entries", [])))
            for s in items if isinstance(s, dict)]


def load_series(path: Path) -> list[Series]:
    """The versions in a file, grouped in series; one unnamed series when the file is a plain list of versions;
    nothing when the file is missing or not JSON."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict) and isinstance(data.get("series"), list):
        return _series_list(data["series"])
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and "entries" in data[0]:
            return _series_list(data)
        return [Series("default", "", tuple(_entry(e) for e in data if isinstance(e, dict)))]
    return []


def load_page(page: Page, folder: Path = DATA_DIR) -> list[Series]:
    return load_series(folder / page.file)


def count(series: list[Series]) -> int:
    return sum(len(s.entries) for s in series)
