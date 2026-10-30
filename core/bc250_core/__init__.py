# SPDX-License-Identifier: GPL-3.0-or-later
"""Code shared by the BC250 Bazzite Suite apps: look (theme, widgets), bootstrap (app, settings), help shell and
the update-check mechanism. Each app passes its constants in as an AppInfo; nothing here imports an app."""

__version__ = "1.1.0"

from .appinfo import SUITE_MANUAL_URL, SUITE_REPO_URL, AppInfo
from .text import fill, fmt, plain_tooltip, window_title

__all__ = ["AppInfo", "SUITE_MANUAL_URL", "SUITE_REPO_URL", "fill", "fmt", "plain_tooltip",
           "window_title", "__version__"]
