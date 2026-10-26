# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m bc250_portal [--manifest FILE] [--source auto|release|checkout]"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from PyQt6.QtWidgets import QMessageBox

from bc250_core import __version__ as CORE_VERSION, instance
from bc250_core.app import create_app, exec_app
from bc250_core.updates import repo_slug

from . import (APP_NAME, INFO, MANIFEST, __version__, find_checkout, installed_copy, remembered_checkout, state_dir,
               suite_checkout)
from . import portal_update
from .main_window import MainWindow
from .manifest import ManifestError, load, load_checkout
from .sources import Records, Sources, http_download


def _show_error(kind, value, tb) -> None:
    text = "".join(traceback.format_exception(kind, value, tb))
    print(text, file=sys.stderr)
    QMessageBox.critical(None, APP_NAME, f"Something went wrong in the portal:\n\n{value}\n\n{text[-1500:]}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="bc250_portal", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--manifest", default=str(MANIFEST), help="apps.toml to use (default: the bundled one)")
    parser.add_argument("--source", choices=("auto", "release", "checkout"), default="auto",
                        help="where apps install from: the pinned GitHub releases, or the local suite checkout "
                             "(auto: the checkout when the portal runs from one)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    args, qt_args = parser.parse_known_args()

    app = create_app(INFO, qt_args)
    # PyQt6 ends the whole app on an exception in a slot. The portal may be mid-install: show it and carry on.
    sys.excepthook = _show_error
    try:
        entries = load(Path(args.manifest))
        checkout_only = load_checkout(Path(args.manifest))
    except (OSError, ManifestError) as exc:
        QMessageBox.critical(None, APP_NAME, f"The app list could not be read:\n\n{exc}")
        return 1
    local_build = suite_checkout()
    checkout = local_build if args.source in ("auto", "checkout") else None
    if args.source == "checkout" and checkout is None:
        QMessageBox.critical(None, APP_NAME, "--source checkout: the portal is not running from a suite checkout.")
        return 1
    # The checkout-only apps run from a checkout: a portal without one of its own finds one on this machine (asking
    # only when there is none); the released apps still install from their pinned releases.
    shown = entries + checkout_only
    apps_checkout = None if checkout else local_build or remembered_checkout() or find_checkout()
    sources = Sources(state_dir() / "releases", checkout=checkout, download=http_download(INFO.user_agent),
                      apps_checkout=apps_checkout)
    # One instance: a second launch brings the running window to the front and exits.
    if instance.already_running(INFO.app_id):
        return 0

    # The newest portal release on GitHub, and which app releases it pins differently, checked once in the
    # background; offline it simply finds nothing.
    def portal_check():
        return portal_update.check(repo_slug(INFO.repo_url), INFO.tag_prefix, entries, INFO.user_agent)

    window = MainWindow(shown, sources, Records(state_dir() / "installed.json"), portal_check=portal_check,
                        local_build=local_build, installed=installed_copy())
    window.show()
    window.start_up()
    server = instance.serve(INFO.app_id, window)  # noqa: F841 (kept alive while the app runs)
    return exec_app(app)


if __name__ == "__main__":
    sys.exit(main())
