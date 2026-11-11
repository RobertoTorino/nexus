# SPDX-License-Identifier: GPL-3.0-or-later
"""Sets the memory layout of the BC-250: the VRAM split in CMOS and the GTT limit (ttm.pages_limit) on the kernel
command line, and shows the GTT, the TTM limit and the swap layout that go with them. The board changes only when
you apply one, and only after a reboot."""

APP_NAME = "BC-250 Memory Manager"
APP_ID = "bc250-memory-manager"
__version__ = "2.0.3"

from pathlib import Path

from bc250_core import AppInfo

ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = ROOT / "images" / f"{APP_ID}.webp"

# Settings in ~/.config/bc250-memory-manager/bc250-memory-manager.ini
INFO = AppInfo(app_id=APP_ID, name=APP_NAME, version=__version__, logo=LOGO_PATH, tag_prefix="vram-v",
               settings_ini=True)

__all__ = ["APP_ID", "APP_NAME", "INFO", "LOGO_PATH", "ROOT", "__version__"]
