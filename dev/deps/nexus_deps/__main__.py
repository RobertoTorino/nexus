# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m nexus_deps [--suite NAME] [--fix | --remind] (run.sh starts it with the checkout's dev venv).

--fix opens the window and offers Fix as soon as the check is done (the weekly notification's Fix… button).
--remind shows no window: it checks the suite's dependencies and reads Bazzite's update state and, when something
needs the user, says so in a desktop notification with buttons to open the app or fix what is missing. The weekly
systemd user timer that install.sh writes runs it."""

from __future__ import annotations

import argparse
import subprocess
import sys

from bc250_core import __version__ as CORE_VERSION, instance

from . import APP_ID, APP_NAME, DEFAULT_SUITE, INFO, LOGO_PATH, ROOT, __version__, catalog, suites
from .bazzite import read_state
from .dependencies import DependencyCatalogError, DependencyCheckError, check_all, load_apps, load_catalog, load_tools
from .fixes import notify, reminder_text


def remind(suite: str) -> int:
    """The weekly check: a notification when something needs the user; a click on a button opens the app."""
    path = catalog(suite)
    try:
        result = check_all(load_catalog(path), load_tools(path), load_apps(path), INFO.user_agent)
    except (DependencyCatalogError, DependencyCheckError, OSError) as exc:
        print(f"{APP_NAME}: the dependency check failed: {exc}", file=sys.stderr)
        result = None
    note = reminder_text(read_state(), result)
    if not note.text:
        return 0
    print(note.text)
    answer = notify(APP_NAME, note.text, str(LOGO_PATH), note.actions)
    if answer in ("fix", "open"):
        argv = [str(ROOT / "run.sh"), "--suite", suite, *(["--fix"] if answer == "fix" else [])]
        subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="nexus_deps", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    parser.add_argument("--suite", metavar="NAME", default=DEFAULT_SUITE, choices=suites(),
                        help=f"the suite whose apps to check (default {DEFAULT_SUITE})")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fix", action="store_true", help="offer Fix as soon as the check is done")
    mode.add_argument("--remind", action="store_true", help="no window: a desktop notification when something "
                                                            "needs you (the weekly timer runs this)")
    args, qt_args = parser.parse_known_args()
    if args.remind:
        return remind(args.suite)

    from bc250_core.app import create_app, exec_app
    from bc250_core.nexus import NEXUS
    from bc250_core.platform import data_home
    from PyQt6.QtWidgets import QMessageBox

    app = create_app(INFO, qt_args, theme=NEXUS)           # Nexus's design, not a suite's theme
    path = catalog(args.suite)
    try:
        apps = load_apps(path)
        dependencies = load_catalog(path)
        tools = load_tools(path)
    except DependencyCatalogError as exc:
        QMessageBox.critical(None, APP_NAME, f"The dependency catalog could not be read:\n\n{exc}")
        return 1
    # One instance: a second launch (a double-click on the Desktop icon) brings the running window to the front.
    if instance.already_running(INFO.app_id):
        return 0
    if not (data_home() / "applications" / f"{APP_ID}.desktop").is_file():
        app.setDesktopFileName("")              # no menu entry: no desktop file name for Qt to look up
    from .main_window import DependencyWindow
    window = DependencyWindow(dependencies, tools, apps, suite=args.suite, offer_fix=args.fix)
    window.show()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
