# SPDX-License-Identifier: GPL-3.0-or-later
"""AppInfo: the per-app constants that core code needs, passed in explicitly instead of imported from the app.

Each app builds one AppInfo from its own __init__ constants and hands it to run_app()/create_app(), which also
makes it the current one, so helpers such as window_title() can find the app name without an argument."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SUITE_REPO_URL = "https://github.com/RobertoTorino/nexus"
SUITE_MANUAL_URL = "https://robertotorino.github.io/nexus/bc250-bazzite-suite/"     # one chapter per app: apps/<key>/



@dataclass(frozen=True)
class AppInfo:
    app_id: str                         # "bc250-governor-manager": desktop file name, default settings names
    name: str                           # "BC-250 GPU Governor Manager"
    version: str
    logo: Path | None = None
    repo_url: str = SUITE_REPO_URL
    tag_prefix: str = ""                # "governor-v": this app's release tags in the suite repo
    settings_org: str = ""              # existing QSettings org/app, so no settings file moves (default: app_id)
    settings_app: str = ""
    settings_ini: bool = False          # bazzite-test keeps an .ini; the others Qt's native format (.conf)

    @property
    def display_name(self) -> str:
        return f"{self.name} {self.version}"

    @property
    def releases_url(self) -> str:
        return f"{self.repo_url}/releases"

    @property
    def user_agent(self) -> str:
        return f"{self.app_id}/{self.version}"

    @property
    def org(self) -> str:
        return self.settings_org or self.app_id

    @property
    def settings_name(self) -> str:
        return self.settings_app or self.app_id


_current: AppInfo | None = None


def set_current(info: AppInfo) -> None:
    global _current
    _current = info


def current() -> AppInfo | None:
    """The AppInfo of the running app (set by create_app), or None outside an app, e.g. in a bare test."""
    return _current
