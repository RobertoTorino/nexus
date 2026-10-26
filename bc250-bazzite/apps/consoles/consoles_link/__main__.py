# SPDX-License-Identifier: AGPL-3.0-or-later
"""Entry point: python -m consoles_link"""

from __future__ import annotations

import argparse
import sys

from bc250_core import __version__ as CORE_VERSION, instance
from bc250_core.app import create_app, exec_app
from bc250_core.platform import config_home

from . import APP_NAME, INFO, __version__


def main() -> int:
    parser = argparse.ArgumentParser(prog="consoles_link", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    parser.add_argument("--stream", metavar="CONSOLE",
                        help="stream from a registered console (its name, host id or address) full screen, without "
                             "the main window: what a Steam shortcut for Game Mode runs")
    # Not for users: the several-players experiment (stream.PlayerExperiment), with --stream, from a terminal.
    parser.add_argument("--player-experiment", metavar="MODE[:ID[:MARK]]", help=argparse.SUPPRESS)
    # Not for users: with --stream, drop this share (percent) of the video packets, to try the recovery from loss.
    parser.add_argument("--simulate-loss", metavar="PERCENT", type=float, default=0.0, help=argparse.SUPPRESS)
    args, qt_args = parser.parse_known_args()
    from .stream import PlayerExperiment
    players = PlayerExperiment()
    if args.player_experiment:
        try:
            players = PlayerExperiment.parse(args.player_experiment)
        except ValueError as error:
            parser.error(f"--player-experiment: {error}")

    from .consoles import migrate_old_config
    migrate_old_config(config_home(), INFO.app_id)      # before Qt opens the settings file
    app = create_app(INFO, qt_args)
    if args.stream:
        from . import direct
        return direct.run(args.stream, app, players=players, simulated_loss=max(0.0, min(args.simulate_loss, 100.0)))
    if instance.already_running(INFO.app_id):
        return 0
    from .main_window import MainWindow
    window = MainWindow()
    window.show()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
