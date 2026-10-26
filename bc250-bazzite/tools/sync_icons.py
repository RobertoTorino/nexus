#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Convert new category icons in icons/<category>/ and copy them to every app, as icons/categories.toml assigns them:

    python3 tools/sync_icons.py                                       # convert, then write the copies that differ
    python3 tools/sync_icons.py --check                               # only list them; exit 1 when there are any
    python3 tools/sync_icons.py --category C --from IMAGE             # the category's four icons from one image
    python3 tools/sync_icons.py --category C --from IMAGE --size 512  # only the sizes named (--size again for more)

The portal's Big Picture Mode also gets each category's 512 px icon, portal/images/categories/<category>.webp.
The copies stay in git where they are, so the installers, the portal, the wiki and a release find them as before;
icons/ is the one place to change them. They are WebP, which Qt and the wiki read, except the 128 px one: menu
entries, Desktop icons, Steam shortcuts and notifications get that PNG, which every desktop shows.

An image dropped in icons/<category>/ is converted when the copies are written. One named <category>-<size>.<any
extension> becomes that size's icon; one with any other name becomes all four. Either is scaled to the size, saved
in its format under its name, and the dropped file removed. Images must be square."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIZES = (1024, 512, 256, 128)
WEBP_QUALITY = 90


def icon_path(category_dir: Path, size: int) -> Path:
    """A category's icon at one size: WebP, the 128 px one PNG."""
    return category_dir / f"{category_dir.name}-{size}.{'png' if size == 128 else 'webp'}"


def copies(root: Path = ROOT) -> dict[Path, Path]:
    """Each copy (a path in the checkout) with the category icon it is a copy of."""
    table = tomllib.loads((root / "icons" / "categories.toml").read_text(encoding="utf-8"))
    found = {}
    for key, entry in table.items():
        category = entry["category"]
        if not (root / "icons" / category).is_dir():
            raise SystemExit(f"[{key}]: no icons/{category}/")
        for icon in entry["icons"]:
            found[root / f"{icon}.webp"] = icon_path(root / "icons" / category, 512)
            found[root / f"{icon}-128.png"] = icon_path(root / "icons" / category, 128)
        if "tile" in entry:
            found[root / entry["tile"]] = icon_path(root / "icons" / category, 256)
        # Suite Big Picture Mode draws a tile large, from the 512 px icon of its category (one file per category).
        found[root / "portal" / "images" / "categories" / f"{category}.webp"] = icon_path(
            root / "icons" / category, 512)
    return found


def stale(root: Path = ROOT) -> list[Path]:
    """The copies that are missing or differ from their category icon."""
    return [copy for copy, source in copies(root).items()
            if not copy.is_file() or copy.read_bytes() != source.read_bytes()]


def missing(root: Path = ROOT) -> list[Path]:
    """The category icons not there: no copy is written from them."""
    return [icon_path(category_dir, size)
            for category_dir in sorted(p for p in (root / "icons").iterdir() if p.is_dir())
            for size in SIZES if not icon_path(category_dir, size).is_file()]


def convert(source: Path, category_dir: Path, sizes: tuple[int, ...] = SIZES) -> list[Path]:
    """Write the category's icons at the sizes from one image; the paths written."""
    from PIL import Image   # imported here: the copies alone need no Pillow

    try:
        with Image.open(source) as image:
            image = image.convert("RGBA")
    except OSError as error:
        raise SystemExit(f"{source}: not an image Pillow reads ({error})") from None
    if image.width != image.height:
        raise SystemExit(f"{source}: {image.width} x {image.height} px, an icon must be square")
    written = []
    for size in sizes:
        target = icon_path(category_dir, size)
        scaled = image if image.width == size else image.resize((size, size), Image.Resampling.LANCZOS)
        if size == 128:
            scaled.save(target, "PNG", optimize=True)
        else:
            scaled.save(target, "WEBP", quality=WEBP_QUALITY, method=6)
        written.append(target)
    return written


def is_icon(path: Path) -> bool:
    """The file is a category icon as it should be: its name, format and size."""
    from PIL import Image

    match = re.fullmatch(rf"{re.escape(path.parent.name)}-(\d+)\.(webp|png)", path.name)
    if match is None or int(match[1]) not in SIZES or path != icon_path(path.parent, int(match[1])):
        return False
    with Image.open(path) as image:
        return image.format == match[2].upper() and image.size == (int(match[1]),) * 2


def dropped(root: Path = ROOT) -> dict[Path, tuple[int, ...]]:
    """The images in icons/<category>/ still to convert, each with the sizes it becomes, the whole sets first."""
    found: dict[Path, tuple[int, ...]] = {}
    for category_dir in sorted(p for p in (root / "icons").iterdir() if p.is_dir()):
        sets, singles = [], []
        for path in sorted(p for p in category_dir.iterdir() if p.is_file() and not p.name.startswith(".")):
            match = re.fullmatch(rf"{re.escape(category_dir.name)}-(\d+)\.[^.]+", path.name)
            if match and int(match[1]) in SIZES:
                if not is_icon(path):
                    singles.append((path, (int(match[1]),)))
            else:
                sets.append((path, SIZES))
        if len(sets) > 1:
            raise SystemExit(f"icons/{category_dir.name}/: more than one image for all sizes: "
                             + ", ".join(path.name for path, _sizes in sets))
        found.update(sets + singles)
    return found


def convert_dropped(root: Path = ROOT) -> list[Path]:
    """Convert every dropped image and remove it; the icons written."""
    written = []
    for source, sizes in dropped(root).items():
        targets = convert(source, source.parent, sizes)
        if source not in targets:
            source.unlink()
        for target in targets:
            print(f"converted: {source.relative_to(root).as_posix()} -> {target.relative_to(root).as_posix()}")
        written += targets
    return written


def main(argv: list[str], root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description="Convert the category icons and copy them to every app.")
    parser.add_argument("--check", action="store_true", help="only list what is out of date; exit 1 when any is")
    parser.add_argument("--category", help="the category (a folder of icons/) --from writes")
    parser.add_argument("--from", dest="source", type=Path, help="an image to make the category's icons from")
    parser.add_argument("--size", type=int, action="append", choices=SIZES,
                        help="only this size from --from (again for more); all four without it")
    args = parser.parse_args(argv)
    if (args.category is None) != (args.source is None) or (args.size and args.source is None):
        parser.error("--category and --from go together, --size only with them")
    if args.check and args.source is not None:
        parser.error("--check does not convert: leave out --category and --from")
    if args.source is not None:
        category_dir = root / "icons" / args.category
        if not category_dir.is_dir():
            parser.error(f"no icons/{args.category}/")
        if not args.source.is_file():
            parser.error(f"no such image: {args.source}")
        for target in convert(args.source, category_dir, tuple(args.size or SIZES)):
            print(f"converted: {args.source} -> {target.relative_to(root).as_posix()}")
    if args.check:
        pending = list(dropped(root))
        for path in pending:
            print("not converted: " + path.relative_to(root).as_posix())
    else:
        convert_dropped(root)
        pending = []
    absent = missing(root)
    for path in absent:
        print("missing: " + path.relative_to(root).as_posix(), file=sys.stderr)
    if absent:
        return 1
    sources, out = copies(root), stale(root)
    for copy in out:
        print(("out of date: " if args.check else "updated: ") + copy.relative_to(root).as_posix())
        if not args.check:
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(sources[copy].read_bytes())
    if args.check and (out or pending):
        print("run python3 tools/sync_icons.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
