# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m vita3k_manager [--windowed], or --play <Vita3K's arguments> (a game's Steam shortcut)"""

from __future__ import annotations

import argparse
import sys

from bc250_core import __version__ as CORE_VERSION, applog, instance, play
from bc250_core.app import create_app, exec_app
from bc250_core.platform import private
from bc250_core.portable import PORTABLE

from . import APP_ID, APP_NAME, INFO, SUITE, __version__


def play_game(args: list[str]) -> int:
    """The play mode: Vita3K with *args* (-r <title ID>) from its folder, closed on View, LB and RB held (core's
    play.run), without a window of the app's; Vita3K's exit code. Never the app's one window: it runs beside it."""
    applog.setup(APP_ID, suite=SUITE, private=True)
    log = applog.logger(APP_ID)
    from . import emulator, userdata
    program = emulator.program(emulator.emulator_home())
    game = userdata.vita_fs(emulator.emulator_home()) / "ux0" / "app" / args[-1] if args else None   # -r <title ID>
    if game is not None and play.missing(game):     # taken out of Vita3K after it was put in Steam
        log.error(f"Play: {private(game)} is no longer there; Vita3K was not started.")
        from bc250_core import gone
        return gone.show(INFO, APP_NAME, __version__, game)
    home = emulator.emulator_home()
    if not emulator.running(home):                  # its settings as the window sets them (its exit question off)
        try:
            if done := userdata.prepare(home):
                log.info(f"Vita3K set up: {', '.join(done)}.")
        except OSError as error:
            log.error(f"Vita3K's settings could not be written: {error}")
    try:
        # Its library window minimized beside the game (owner, 05-11-2026: with a TV it stayed on the Ally's screen)
        return play.run([str(program), *args], program.parent, log=log.info, windows=emulator.minimize_library)
    except OSError as error:
        log.error(f"Play: Vita3K could not start: {error}")
        return 1


def main() -> int:
    if play.FLAG in sys.argv[1:]:
        return play_game(sys.argv[sys.argv.index(play.FLAG) + 1:])
    parser = argparse.ArgumentParser(prog="vita3k_manager", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    parser.add_argument("--windowed", action="store_true", help="a window instead of the full screen")
    args, qt_args = parser.parse_known_args()

    app = create_app(INFO, qt_args, theme=PORTABLE)
    if instance.already_running(INFO.app_id):       # a second launch brings the open window to the front
        return 0
    log_path = applog.setup(APP_ID, suite=SUITE, private=True)   # no user name in a line
    applog.logger(APP_ID).info(f"{APP_NAME} {__version__} started.")
    from .main_window import MainWindow
    window = MainWindow(log_path=log_path)
    if args.windowed:
        window.resize(1280, 720)
        window.show()
    else:
        window.showFullScreen()
    window.start()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
