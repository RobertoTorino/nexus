#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Convert new category icons in a suite's icons/<category>/ and copy them to every app of the suite, as its
icons/categories.toml assigns them (a Nexus tool since 02-11-2026, every suite's; --suite names the suite, as
tools/suites.py says, and the paths below are the suite's):

    python3 tools/sync_icons.py                                       # convert, then write the copies that differ
    python3 tools/sync_icons.py --check                               # only list them; exit 1 when there are any
    python3 tools/sync_icons.py --category C --from IMAGE             # the category's four icons from one image
    python3 tools/sync_icons.py --category C --from IMAGE --size 512  # only the sizes named (--size again for more)
    python3 tools/sync_icons.py --suite bc250-bazzite --check         # the suite by name

The portal also gets the 512 px icon of each category it lists apps in, portal/images/categories/<category>.webp, which
its tiles are drawn from.
The copies stay in git where they are, so the installers, the portal, the wiki and a release find them as before;
icons/ is the one place to change them. They are WebP, which Qt and the wiki read, except the 128 px one: menu
entries, Desktop icons, Steam shortcuts and notifications get that PNG, which every desktop shows.

An image dropped in icons/<category>/ is converted when the copies are written. One named <category>-<size>.<any
extension> becomes that size's icon; one with any other name becomes all four. Either is scaled to the size, saved
in its format under its name, and the dropped file removed. Images must be square.

A suite whose icons are made otherwise says so in an [icons] table of its categories.toml (the Windows Portable Suite,
05-11-2026; the BC250 suite's has none, so it keeps the above): format = "png", every size a PNG; wide = {category =
2}, a category whose pictures are that many times as wide as high (its sizes are the widths: 1024 x 512 down to
128 x 64), and refused when they are not; apps = "portal", no app table here: every app takes its category's icon as
the portal's apps.toml gives it, and tools/make_icons.py writes the copies (a wide picture centered on a transparent
square for a window icon, the wiki's lossy), so they are checked by their pixels."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

import suites

ROOT = suites.ROOT                                  # the checkout; the functions take the suite's folder
SIZES = (1024, 512, 256, 128)
WEBP_QUALITY = 90


def options(root: Path) -> dict:
    """The suite's [icons] table of categories.toml (format, wide, apps), {} when it has none."""
    return tomllib.loads((root / "icons" / "categories.toml").read_text(encoding="utf-8")).get("icons", {})


def icon_path(category_dir: Path, size: int, png: bool = False) -> Path:
    """A category's icon at one size: WebP, the 128 px one PNG; every size PNG for a suite of PNG icons (*png*)."""
    return category_dir / f"{category_dir.name}-{size}.{'png' if png or size == 128 else 'webp'}"


def _png(root: Path) -> bool:
    return options(root).get("format") == "png"


def _ratio(root: Path, category: str) -> int:
    """How many times as wide as high the category's pictures are (1: square)."""
    return int(options(root).get("wide", {}).get(category, 1))


def portal_copies(root: Path) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """A suite whose apps take their icons from the portal (apps = "portal"): tools/make_icons.py's copies, (source,
    target) relative to the checkout, lossless and the wiki's."""
    import make_icons                                   # beside this tool; it imports Pillow only when it writes
    return make_icons.windows_portable_app_copies(root.parent)


def stale_portal(root: Path) -> list[Path]:
    """The portal-made copies missing or not their category icon: the lossless ones by their pixels (a wide picture
    on a transparent square for a window icon), the wiki's lossy ones by their size."""
    from PIL import Image

    import make_icons
    exact, page = portal_copies(root)
    out = []
    for (source, target), lossy in [*((pair, False) for pair in exact), *((pair, True) for pair in page)]:
        path = root.parent / target
        if not path.is_file():
            out.append(path)
            continue
        with Image.open(root.parent / source) as image, Image.open(path) as copy:
            want = image.convert("RGBA")
            if make_icons.square_target(target) and want.width != want.height:
                side = max(want.size)
                canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                canvas.paste(want, ((side - want.width) // 2, (side - want.height) // 2))
                want = canvas
            if copy.size != want.size or (not lossy and copy.convert("RGBA").tobytes() != want.tobytes()):
                out.append(path)
    return out


def copies(root: Path | None = None) -> dict[Path, Path]:
    """Each copy (a path in the suite) with the category icon it is a copy of; none for a suite whose apps take
    their icons from the portal (tools/make_icons.py writes those)."""
    root = root or suites.suite()
    table = tomllib.loads((root / "icons" / "categories.toml").read_text(encoding="utf-8"))
    table.pop("icons", None)
    if options(root).get("apps") == "portal":
        return {}
    found = {}
    for key, entry in table.items():
        category = entry["category"]
        if not (root / "icons" / category).is_dir():
            raise SystemExit(f"[{key}]: no icons/{category}/")
        for icon in entry["icons"]:
            found[root / f"{icon}.webp"] = icon_path(root / "icons" / category, 512)
            found[root / f"{icon}-128.png"] = icon_path(root / "icons" / category, 128)
        if "tile" in entry:                     # an app the portal lists
            found[root / entry["tile"]] = icon_path(root / "icons" / category, 256)
            # The portal draws a tile large, from the 512 px icon of its category (one file per category).
            found[root / "portal" / "images" / "categories" / f"{category}.webp"] = icon_path(
                root / "icons" / category, 512)
    return found


def stale(root: Path | None = None) -> list[Path]:
    """The copies that are missing or differ from their category icon."""
    root = root or suites.suite()
    return [copy for copy, source in copies(root).items()
            if not copy.is_file() or copy.read_bytes() != source.read_bytes()]


def missing(root: Path | None = None) -> list[Path]:
    """The category icons not there: no copy is written from them."""
    root = root or suites.suite()
    png = _png(root)
    return [icon_path(category_dir, size, png)
            for category_dir in sorted(p for p in (root / "icons").iterdir() if p.is_dir())
            for size in SIZES if not icon_path(category_dir, size, png).is_file()]


def convert(source: Path, category_dir: Path, sizes: tuple[int, ...] = SIZES, png: bool = False,
            ratio: int = 1) -> list[Path]:
    """Write the category's icons at the sizes from one image; the paths written. *png*: every size a PNG; *ratio*:
    the picture is that many times as wide as high (1: square), each size its width."""
    from PIL import Image   # imported here: the copies alone need no Pillow

    try:
        with Image.open(source) as image:
            image = image.convert("RGBA")
    except OSError as error:
        raise SystemExit(f"{source}: not an image Pillow reads ({error})") from None
    if image.width != image.height * ratio:
        shape = "square" if ratio == 1 else f"{ratio} times as wide as high"
        raise SystemExit(f"{source}: {image.width} x {image.height} px, an icon of {category_dir.name} must be {shape}")
    written = []
    for size in sizes:
        target = icon_path(category_dir, size, png)
        box = (size, size // ratio)
        scaled = image if image.size == box else image.resize(box, Image.Resampling.LANCZOS)
        if png or size == 128:
            scaled.save(target, "PNG", optimize=True)
        else:
            scaled.save(target, "WEBP", quality=WEBP_QUALITY, method=6)
        written.append(target)
    return written


def is_icon(path: Path, png: bool = False, ratio: int = 1) -> bool:
    """The file is a category icon as it should be: its name, format and size (*png*, *ratio* as convert())."""
    from PIL import Image

    match = re.fullmatch(rf"{re.escape(path.parent.name)}-(\d+)\.(webp|png)", path.name)
    if match is None or int(match[1]) not in SIZES or path != icon_path(path.parent, int(match[1]), png):
        return False
    with Image.open(path) as image:
        return image.format == match[2].upper() and image.size == (int(match[1]), int(match[1]) // ratio)


def dropped(root: Path | None = None) -> dict[Path, tuple[int, ...]]:
    """The images in icons/<category>/ still to convert, each with the sizes it becomes, the whole sets first."""
    root = root or suites.suite()
    png = _png(root)
    found: dict[Path, tuple[int, ...]] = {}
    for category_dir in sorted(p for p in (root / "icons").iterdir() if p.is_dir()):
        sets, singles = [], []
        for path in sorted(p for p in category_dir.iterdir() if p.is_file() and not p.name.startswith(".")):
            match = re.fullmatch(rf"{re.escape(category_dir.name)}-(\d+)\.[^.]+", path.name)
            if match and int(match[1]) in SIZES:
                if not is_icon(path, png, _ratio(root, category_dir.name)):
                    singles.append((path, (int(match[1]),)))
            else:
                sets.append((path, SIZES))
        if len(sets) > 1:
            raise SystemExit(f"icons/{category_dir.name}/: more than one image for all sizes: "
                             + ", ".join(path.name for path, _sizes in sets))
        found.update(sets + singles)
    return found


def convert_dropped(root: Path | None = None) -> list[Path]:
    """Convert every dropped image and remove it; the icons written."""
    root = root or suites.suite()
    written = []
    for source, sizes in dropped(root).items():
        targets = convert(source, source.parent, sizes, _png(root), _ratio(root, source.parent.name))
        if source not in targets:
            source.unlink()
        for target in targets:
            print(f"converted: {source.relative_to(root).as_posix()} -> {target.relative_to(root).as_posix()}")
        written += targets
    return written


def main(argv: list[str], root: Path | None = None) -> int:
    """*root*: the suite's folder; without one, --suite picks it (tools/suites.py)."""
    parser = argparse.ArgumentParser(description="Convert a suite's category icons and copy them to its apps.")
    parser.add_argument("--check", action="store_true", help="only list what is out of date; exit 1 when any is")
    suites.add_argument(parser)
    parser.add_argument("--root", type=Path, help=argparse.SUPPRESS)     # a suite folder anywhere (tools/new_app.py)
    parser.add_argument("--category", help="the category (a folder of icons/) --from writes")
    parser.add_argument("--from", dest="source", type=Path, help="an image to make the category's icons from")
    parser.add_argument("--size", type=int, action="append", choices=SIZES,
                        help="only this size from --from (again for more); all four without it")
    args = parser.parse_args(argv)
    if root is None and args.root is not None:
        root = args.root.resolve()
    if root is None:
        try:
            root = suites.suite(args.suite)
        except LookupError as error:
            parser.error(str(error))
    if not (root / "icons" / "categories.toml").is_file():
        parser.error(f"{root.name} has no icons/categories.toml: its apps take no category icons")
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
        for target in convert(args.source, category_dir, tuple(args.size or SIZES), _png(root),
                              _ratio(root, args.category)):
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
    if options(root).get("apps") == "portal":       # the copies are tools/make_icons.py's, from the portal's apps
        portal_out = stale_portal(root)
        if not args.check and portal_out:
            import make_icons
            make_icons.windows_portable_icons(root.parent)
        for copy in portal_out:
            print(("out of date: " if args.check else "updated: ") + copy.relative_to(root.parent).as_posix())
        out = out + portal_out
    if args.check and (out or pending):
        print("run python3 tools/sync_icons.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
