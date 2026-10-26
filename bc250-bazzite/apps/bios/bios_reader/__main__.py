# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m bios_reader [--dump FILE] [--build-table DUMP]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bc250_core import __version__ as CORE_VERSION, instance
from bc250_core.app import create_app, exec_app

from . import APP_NAME, INFO, __version__


def build_table(dump: Path, out_dir: Path | None) -> int:
    from . import bios, table
    name, data = bios.build_table(dump)
    folder = out_dir or table.TABLES_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    print(f"{folder / name}: {len(data)} bytes")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="bios_reader", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--dump", type=Path, metavar="FILE", help="open this BIOS image instead of the running board")
    parser.add_argument("--build-table", type=Path, metavar="DUMP",
                        help="make the built-in table of a stock BIOS release from a dump of it, and exit")
    parser.add_argument("--out", type=Path, metavar="DIR", help="folder for --build-table (default: the app's)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    args, qt_args = parser.parse_known_args()
    if args.build_table:
        return build_table(args.build_table, args.out)

    app = create_app(INFO, qt_args)
    if instance.already_running(INFO.app_id):
        return 0
    from .main_window import MainWindow
    window = MainWindow()
    if args.dump is None or not window.load_dump_file(args.dump):
        window.load_board()
    window.show()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
