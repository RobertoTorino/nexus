# SPDX-License-Identifier: GPL-2.0-only
"""Entry point: python -m netcat_gui [-u] [host port | -l port]"""

from __future__ import annotations

import argparse
import sys

from bc250_core import __version__ as CORE_VERSION, instance
from bc250_core.app import create_app, exec_app

from . import APP_ID, APP_NAME, INFO, __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_ID, description=f"{APP_NAME} {__version__}: a graphical netcat.",
        epilog="Without arguments the window opens with one empty Connect tab.")
    parser.add_argument("host", nargs="?", help="open a Connect tab to this host and connect")
    parser.add_argument("port", nargs="?", type=int, help="the port to connect to (with host)")
    parser.add_argument("-l", "--listen", metavar="PORT", type=int, help="open a Listen tab on this port and listen")
    parser.add_argument("-u", "--udp", action="store_true", help="use UDP instead of TCP for that tab")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    return parser


def own_arguments(args: argparse.Namespace) -> list[str]:
    """The tab the arguments ask for, as arguments again: what a second launch hands to the open window."""
    udp = ["-u"] if args.udp else []
    if args.listen is not None:
        return [*udp, "-l", str(args.listen)]
    if args.host:
        return [*udp, args.host, str(args.port)]
    return []


def open_tab(window, args: argparse.Namespace) -> None:
    """Open the tab the arguments ask for and start it; without arguments, one empty Connect tab."""
    from .session import Protocol
    protocol = Protocol.UDP if args.udp else Protocol.TCP
    if args.listen is not None:
        window.new_listen_tab(port=args.listen, protocol=protocol, start=True)
    elif args.host:
        window.new_connect_tab(host=args.host, port=args.port, protocol=protocol, start=True)
    else:
        window.new_connect_tab()


def main() -> int:
    parser = build_parser()
    args, qt_args = parser.parse_known_args()
    if args.host and args.port is None:
        parser.error("a port is needed with the host")
    if args.listen is not None and args.host:
        parser.error("--listen cannot be combined with a host")

    app = create_app(INFO, qt_args)
    # A second launch with a host or a port opens its tab in the open window.
    if instance.already_running(INFO.app_id, own_arguments(args)):
        return 0
    from .main_window import MainWindow
    window = MainWindow()
    open_tab(window, args)
    window.show()
    server = instance.serve(INFO.app_id, window,  # noqa: F841 (kept alive while the app runs)
                            on_args=lambda forwarded: open_tab(window, parser.parse_known_args(forwarded)[0]))
    # Logout or SIGTERM/SIGINT quit the app cleanly (sessions closed, settings saved) instead of killing it.
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
