# SPDX-License-Identifier: GPL-3.0-or-later
"""Before/after of two compare reports (module version of ``scripts/compare_report_delta.py``): what a change in
the extractor fixed and what it broke, read from the JSON files ``compare.py`` writes.

Used by the window's Compare menu ("Delta between two compare reports…") and available as::

    python -m shadps4_manager.pkgxtractor.compare_delta <before.json> <after.json> [--out delta.txt]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

COUNT_KEYS = (
    "left_file_count",
    "right_file_count",
    "common_file_count",
    "only_left_count",
    "only_right_count",
    "size_mismatch_count",
    "hash_mismatch_count",
)
LIST_KEYS = ("only_left", "only_right", "size_mismatch", "hash_mismatch")
PREVIEW = 20


def load_report(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        report = json.load(handle)
    if not isinstance(report, dict):
        raise ValueError(f"{path} is not a compare report")
    return report


def summarize_delta(before: dict, after: dict) -> str:
    lines = ["=== Compare Report Delta ==="]
    for key in COUNT_KEYS:
        b = int(before.get(key, 0))
        a = int(after.get(key, 0))
        delta = a - b
        trend = "DOWN" if delta < 0 else "UP" if delta > 0 else "UNCHANGED"
        lines.append(f"{key}: before={b}, after={a}, delta={delta:+d} ({trend})")

    for key in LIST_KEYS:
        before_set = set(before.get(key, []))
        after_set = set(after.get(key, []))
        fixed = sorted(before_set - after_set)
        new = sorted(after_set - before_set)
        lines.append("")
        lines.append(f"[{key}] fixed={len(fixed)}, new={len(new)}")
        if fixed:
            lines.append(f"  fixed (first {PREVIEW}):")
            lines.extend(f"    - {item}" for item in fixed[:PREVIEW])
        if new:
            lines.append(f"  new (first {PREVIEW}):")
            lines.extend(f"    - {item}" for item in new[:PREVIEW])
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two compare_report JSON files (before vs after).")
    parser.add_argument("before", type=Path, help="Path to the before report JSON")
    parser.add_argument("after", type=Path, help="Path to the after report JSON")
    parser.add_argument("--out", type=Path, default=None, help="Optional output txt file")
    args = parser.parse_args(argv)

    text = summarize_delta(load_report(args.before), load_report(args.after))
    print(text)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"\nDelta written to: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
