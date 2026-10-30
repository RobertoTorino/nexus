# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: python -m portable_portal [--manifest FILE] [--windowed], or --xbox-menu (the installer's)"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtWidgets import QMessageBox

from bc250_core import __version__ as CORE_VERSION, applog, instance
from bc250_core.app import create_app, exec_app
from bc250_core.portable import PORTABLE
from bc250_core.updates import repo_slug

from . import APP_ID, APP_NAME, EXE_NAME, INFO, MANIFEST, __version__, portal_update, state_dir
from .manifest import ManifestError, load
from .sources import Records, Sources, http_download


def xbox_menu() -> int:
    """--xbox-menu, as install.ps1 runs it once the portal is installed (owner, 30-10-2026): the installed portal in
    the Xbox app's library, without a window; 0 when it is there now, 1 when it could not be added (said why)."""
    from bc250_core import xbox

    from .main_window import LOGO_PNG
    applog.setup(APP_ID, path=state_dir() / "portal.log", private=True)
    log = applog.logger(APP_ID)
    program = state_dir() / "app" / f"{EXE_NAME}.exe"
    if not xbox.installed():
        print("The Xbox app is not installed: there is no Xbox menu to add the suite to.")
        return 1
    try:
        added = xbox.add(program, APP_NAME, LOGO_PNG)
    except (xbox.FormatError, OSError) as exc:
        print(f"Not added to the Xbox menu: {exc}")
        log.error(f"Not added to the Xbox menu: {exc}")
        return 1
    print("Added to the Xbox menu." if added else "Already in the Xbox menu.")
    log.info("Added to the Xbox menu (the Xbox app's library)." if added else "Already in the Xbox menu.")
    return 0


def main() -> int:
    if "--xbox-menu" in sys.argv[1:]:
        return xbox_menu()
    parser = argparse.ArgumentParser(prog="portable_portal", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--manifest", default=str(MANIFEST), help="apps.toml to use (default: the bundled one)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (core {CORE_VERSION})")
    parser.add_argument("--windowed", action="store_true", help="a window instead of the full screen")
    args, qt_args = parser.parse_known_args()

    app = create_app(INFO, qt_args, theme=PORTABLE)
    if instance.already_running(INFO.app_id):
        return 0
    log_path = applog.setup(APP_ID, path=state_dir() / "portal.log", private=True)
    applog.logger(APP_ID).info(f"{APP_NAME} {__version__} started ({log_path}).")
    try:
        entries = load(Path(args.manifest))
    except (OSError, ManifestError) as exc:
        QMessageBox.critical(None, APP_NAME, f"The app list could not be read:\n\n{exc}")
        return 1
    sources = Sources(state_dir() / "releases", download=http_download(INFO.user_agent))

    # The newest portal release on GitHub, and which app releases it pins differently, checked once in the
    # background; offline it simply finds nothing.
    def portal_check():
        return portal_update.check(repo_slug(INFO.repo_url), INFO.tag_prefix, entries, INFO.user_agent)

    from .main_window import MainWindow
    exe = sys.executable if getattr(sys, "frozen", False) else ""     # the installed program, for a restart
    window = MainWindow(entries, sources, Records(state_dir() / "installed.json"), portal_check=portal_check,
                        exe=exe)
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
