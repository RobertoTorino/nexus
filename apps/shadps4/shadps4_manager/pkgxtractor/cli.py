# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line extractor (port of ``tools/pkgxtractor/main.cpp``).

Usage::

    bc250-shadps4-pkg-cli <PKG_FILE> [OUTPUT_FOLDER] [--salvage] [--preview-only]

Files are written to ``<OUTPUT_FOLDER>/<TITLE_ID>/`` (the output folder
defaults to the folder containing the PKG), matching the GUI behavior.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .. import __version__
from .pkg import PKG, PKGError, is_pkg_file, sanitize_folder_name
from .psf import PSF, PSFError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bc250-shadps4-pkg-cli",
        description="Extract a package (.pkg) file into the shadPS4 folder layout.")
    parser.add_argument("pkg_file", type=Path, help="Path to the PKG file to extract")
    parser.add_argument("output_folder", type=Path, nargs="?", default=None,
                        help="Output directory (default: the PKG file's folder)")
    parser.add_argument("--salvage", action="store_true",
                        help="Skip entries with invalid metadata instead of aborting")
    parser.add_argument("--preview-only", action="store_true",
                        help="Only write sce_sys/ and filelist.txt, do not extract PFS files")
    parser.add_argument("--no-subfolder", action="store_true",
                        help="Extract directly into the output folder instead of <TITLE_ID>/")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def describe_package(pkg: PKG) -> list[str]:
    lines = [f"Content ID: {pkg.content_id}", f"Title ID:   {pkg.title_id}"]
    if pkg.pkg_flags:
        lines.append(f"Flags:      {pkg.pkg_flags}")
    if pkg.sfo:
        try:
            psf = PSF.from_bytes(pkg.sfo)
        except PSFError as exc:
            lines.append(f"Could not read SFO: {exc}")
        else:
            lines.append("Successfully read SFO.")
            content_type = psf.get_integer("CONTENT_TYPE")
            if content_type:
                lines.append("DLC detected.")
            else:
                lines.append("Game or Patch detected.")
            for key in ("CATEGORY", "TITLE", "TITLE_ID", "APP_VER", "VERSION"):
                value = psf.get_string(key)
                if value:
                    lines.append(f"{key}: {value}")
    else:
        lines.append("Could not read SFO.")
    return lines


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pkg_file: Path = args.pkg_file

    if not pkg_file.is_file() or not is_pkg_file(pkg_file):
        print(f"{pkg_file} is not a valid PKG file")
        return 1
    print(f"{pkg_file} is a valid PKG\n")

    output_root: Path = args.output_folder if args.output_folder is not None else pkg_file.parent

    pkg = PKG()
    try:
        try:
            pkg.open(pkg_file)
        except PKGError as exc:
            print(f"Cannot open PKG file : {exc}")
            return 1
        print("open PKG file success")
        for line in describe_package(pkg):
            print(line)

        if args.no_subfolder:
            output_folder = output_root
        else:
            output_folder = output_root / sanitize_folder_name(pkg.title_id or "unknown_title")
        print(f"\nGame/DLC folder will be extracted to: {output_folder}")
        output_folder.mkdir(parents=True, exist_ok=True)

        try:
            pkg.extract(pkg_file, output_folder)
        except PKGError as exc:
            print(f"Cannot extract PKG file : {exc}")
            return 1
        for warning in pkg.warnings:
            print(f"Warning: {warning}")

        files_count = pkg.num_files
        print(f"Total files to extract: {files_count}")
        pkg.export_file_list(output_folder / "filelist.txt")

        if args.preview_only:
            print("Preview complete (metadata extracted).")
            return 0

        failed = 0
        for index in range(files_count):
            ok, reason = pkg.can_extract_file(index)
            if not ok:
                failed += 1
                print(f"Preflight failed for file {index + 1} ({reason})")
                if args.salvage:
                    continue
                print("Aborting extraction (use --salvage to skip bad entries).")
                return 1
            try:
                pkg.extract_files(index)
            except (PKGError, OSError) as exc:
                failed += 1
                print(f"Error extracting file {index + 1}: {exc}")
            if (index + 1) % 100 == 0 or index + 1 == files_count:
                print(f"Extracted {index + 1}/{files_count}", file=sys.stderr)

        if failed:
            print(f"\nExtraction finished with {failed} file errors")
            return 2
        print("\nExtraction complete!\n")
        return 0
    finally:
        pkg.close()


if __name__ == "__main__":
    raise SystemExit(main())
