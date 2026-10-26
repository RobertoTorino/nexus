# SPDX-License-Identifier: GPL-2.0-only
"""Bazzite NetcatGUI: a graphical netcat (nc) for Bazzite. Connect to a host or listen on a port, TCP or
UDP, one session per tab, type what to send and see what comes back. The Python + Qt port of the C++/Qt tool
NetcatGUI by Shinnok (Teodor Mircea Ionita), GPL-2.0."""

APP_NAME = "Bazzite NetcatGUI"
APP_ID = "bazzite-netcatgui"
__version__ = "0.12.0"

from pathlib import Path  # noqa: E402  (constants first, as the suite's apps do)

from bc250_core import AppInfo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"
ICONS_DIR = ROOT / "images" / "icons"     # the Silk icons the C++ tool used (CC-BY 2.5, Mark James)

# Settings in ~/.config/bazzite-netcatgui/bazzite-netcatgui.ini, as before the move to core.
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH,
               tag_prefix="ncgui-v", settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "ICONS_DIR", "INFO", "LOGO_PATH", "ROOT", "__version__"]
