# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare two extraction folders (module version of ``scripts/compare_extractions.py``).

Used by the GUI's "Compare Extractions" button and available as::

    python -m shadps4_manager.pkgxtractor.compare <left> <right> [--hash] [--json-out report.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

Logger = Callable[[str], None]


def build_index(root: Path, hash_files: bool) -> Dict[str, Dict[str, str]]:
    index: Dict[str, Dict[str, str]] = {}
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(root).as_posix()
        entry = {"size": str(path.stat().st_size)}
        if hash_files:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            entry["sha256"] = digest.hexdigest()
        index[rel] = entry
    return index


def parse_filelist(filelist: Path) -> Dict[str, Tuple[str, str]]:
    result: Dict[str, Tuple[str, str]] = {}
    with filelist.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if 'Name: "' not in line:
                continue
            try:
                name = line.split('Name: "', 1)[1].split('"', 1)[0]
                inode = line.split("Inode:", 1)[1].split(" ", 1)[0]
                ftype = line.split("Type:", 1)[1].split(" ", 1)[0]
                result[f"inode={inode};type={ftype};name={name}"] = (inode, ftype)
            except Exception:
                continue
    return result


def run_compare(left: Path, right: Path, *, use_hash: bool = False,
                left_filelist: Optional[Path] = None, right_filelist: Optional[Path] = None,
                json_out: Optional[Path] = None, log: Logger = print) -> dict:
    left = Path(left).resolve()
    right = Path(right).resolve()
    if not left.is_dir():
        raise FileNotFoundError(f"Left folder not found: {left}")
    if not right.is_dir():
        raise FileNotFoundError(f"Right folder not found: {right}")

    log(f"Indexing left:  {left}")
    left_index = build_index(left, use_hash)
    log(f"Indexing right: {right}")
    right_index = build_index(right, use_hash)

    left_paths = set(left_index)
    right_paths = set(right_index)
    only_left = sorted(left_paths - right_paths)
    only_right = sorted(right_paths - left_paths)
    common = sorted(left_paths & right_paths)

    left_total_size = sum(int(left_index[p]["size"]) for p in left_paths)
    right_total_size = sum(int(right_index[p]["size"]) for p in right_paths)
    common_total_size = sum(int(left_index[p]["size"]) for p in common)

    size_mismatch = []
    hash_mismatch = []
    for rel in common:
        if left_index[rel]["size"] != right_index[rel]["size"]:
            size_mismatch.append(rel)
            continue
        if use_hash and left_index[rel].get("sha256") != right_index[rel].get("sha256"):
            hash_mismatch.append(rel)

    filelist_summary: dict = {}
    if left_filelist and right_filelist:
        left_keys = set(parse_filelist(left_filelist))
        right_keys = set(parse_filelist(right_filelist))
        filelist_summary = {
            "left_only_entries": sorted(left_keys - right_keys),
            "right_only_entries": sorted(right_keys - left_keys),
            "common_entries": len(left_keys & right_keys),
        }

    report = {
        "left": str(left),
        "right": str(right),
        "left_file_count": len(left_index),
        "right_file_count": len(right_index),
        "common_file_count": len(common),
        "left_total_size": left_total_size,
        "right_total_size": right_total_size,
        "common_total_size": common_total_size,
        "only_left_count": len(only_left),
        "only_right_count": len(only_right),
        "size_mismatch_count": len(size_mismatch),
        "hash_mismatch_count": len(hash_mismatch),
        "only_left": only_left,
        "only_right": only_right,
        "size_mismatch": size_mismatch,
        "hash_mismatch": hash_mismatch,
        "filelist_summary": filelist_summary,
    }

    gib = 1024 ** 3
    log("")
    log("=== Comparison Summary ===")
    log(f"Left files:           {report['left_file_count']}")
    log(f"Right files:          {report['right_file_count']}")
    log(f"Common files:         {report['common_file_count']}")
    log(f"Left total size:      {left_total_size:,} bytes ({left_total_size / gib:.2f} GB)")
    log(f"Right total size:     {right_total_size:,} bytes ({right_total_size / gib:.2f} GB)")
    log(f"Common total size:    {common_total_size:,} bytes ({common_total_size / gib:.2f} GB)")
    log(f"Only in left:         {report['only_left_count']}")
    log(f"Only in right:        {report['only_right_count']}")
    log(f"Size mismatches:      {report['size_mismatch_count']}")
    if use_hash:
        log(f"Hash mismatches:      {report['hash_mismatch_count']}")

    if json_out:
        json_out = Path(json_out)
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log("")
        log(f"JSON report written: {json_out}")

    preview = 20
    for title, items in (("Only in left", only_left), ("Only in right", only_right),
                         ("Size mismatch", size_mismatch),
                         ("Hash mismatch", hash_mismatch if use_hash else [])):
        if items:
            log("")
            log(f"-- {title} (first {preview}) --")
            for item in items[:preview]:
                log(item)
    return report


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two extracted PKG outputs quickly.")
    parser.add_argument("left", type=Path, help="First extraction folder (e.g. pkgxtractor output)")
    parser.add_argument("right", type=Path, help="Second extraction folder (e.g. LibOrbisPkg output)")
    parser.add_argument("--hash", action="store_true", help="Also compare SHA-256 for common files")
    parser.add_argument("--left-filelist", type=Path, default=None)
    parser.add_argument("--right-filelist", type=Path, default=None)
    parser.add_argument("--json-out", type=Path, default=None, help="Optional JSON report output path")
    args = parser.parse_args(argv)
    try:
        run_compare(args.left, args.right, use_hash=args.hash, left_filelist=args.left_filelist,
                    right_filelist=args.right_filelist, json_out=args.json_out)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
